from django.utils import timezone
from django.db.models import Sum
from .models import PlanFeature, PlanQuota, Usage, UsageLog
from datetime import timedelta



def get_quota(user, key):
    """Get the numeric quota limit for a specific PlanKey object."""
    if not hasattr(user, 'subscription') or not user.subscription.plan:
        return 0


    quota = PlanQuota.objects.filter(
        plan=user.subscription.plan,
        key__name=key  # Pass the PlanKey instance
    ).first()
    
    val = quota.value if quota else 0
    
    return val



def can_post(user, account=None):
    """Check if the user has enough quota and credits to post."""
    today = timezone.now().date()
    
    # 0. Account active check
    if account and not account.is_active:
        return False

    # 1. Primary Credits check 
    has_sub_credit = hasattr(user, 'subscription') and user.subscription.credit > 0
    has_extra_credit = hasattr(user, 'credit') and user.credit.balance > 0
    
    # 2. Daily Free Credit check (Fallback)
    has_free_credit = False
    if not (has_sub_credit or has_extra_credit):
        free_limit = get_quota(user, "plan_free_credit")
        if free_limit > 0:
            # Sum free usage today across ALL content types and accounts for this user
            total_free_used = UsageLog.objects.filter(
                user=user,
                date=today
            ).aggregate(total=Sum('credit_from_free'))['total'] or 0
            
            if total_free_used < free_limit:
                has_free_credit = True

    if not (has_sub_credit or has_extra_credit or has_free_credit):
        return False

    # 3. Daily Account-level check (posts_per_day)
    daily_limit = get_quota(user, "posts_per_day")
    if daily_limit > 0 and account:
        today_usage = UsageLog.objects.filter(
            user=user, 
            account=account,
            date=today
        ).aggregate(total=Sum('count'))['total'] or 0
        
        if today_usage >= daily_limit:
            return False
            
    return True


def consume_post(user, account=None, post_type="post"):
    """
    Consume a post action, updating daily UsageLog.
    post_type can be: 'reel', 'image', 'video', 'story', etc.
    """
    today = timezone.now().date()
    
    # 0. Account active check
    if account and not account.is_active:
        error_msg = f"Your account '{account.account_name}' is currently inactive. Please activate it to continue posting."
        _log_blocked_attempt(user, account, post_type, today, error_msg, "Account Inactive")
        raise Exception(error_msg)

    # 1. Determine Credit Source
    has_sub_credit = hasattr(user, 'subscription') and user.subscription.credit > 0
    has_extra_credit = hasattr(user, 'credit') and user.credit.balance > 0
    
    is_using_free_credit = False
    
    if not (has_sub_credit or has_extra_credit):
        # Fallback to daily plan_free_credit
        free_limit = get_quota(user, "plan_free_credit")
        total_free_used = UsageLog.objects.filter(
            user=user,
            date=today
        ).aggregate(total=Sum('credit_from_free'))['total'] or 0
        
        if free_limit > 0 and total_free_used < free_limit:
            is_using_free_credit = True
        else:
            error_msg = "You have run out of credits. Please renew your subscription or purchase more credits."
            _log_blocked_attempt(user, account, post_type, today, error_msg, "Quota Exceeded")
            raise Exception(error_msg)

    # 2. Check for Daily Account Limit
    daily_quota = get_quota(user, "posts_per_day")
    if daily_quota > 0:
        today_usage = UsageLog.objects.filter(
            user=user, 
            account=account,
            date=today
        ).aggregate(total=Sum('count'))['total'] or 0
        
        if today_usage >= daily_quota:
            reset_time = get_reset_time(user, account=account)
            time_str = reset_time.strftime("%Y-%m-%d %H:%M") if reset_time else "the next cycle"
            error_msg = f"Daily posting limit reached for this account. You can resume uploading after {time_str}."
            _log_blocked_attempt(user, account, post_type, today, error_msg, "Daily Limit Reached")
            raise Exception(error_msg)

    # 3. Create or Update Usage Log
    log, _ = UsageLog.objects.get_or_create(
        user=user,
        account=account,
        key=post_type,
        date=today
    )

    # 4. Consumption and Tracking
    if is_using_free_credit:
        # If this is the first free credit used today, notify the user
        if total_free_used == 0:
            try:
                from apps.platforms.utils import create_notification
                create_notification(
                    user, 
                    "Plan Credits Exhausted", 
                    "credits is over curretly uploading useind free crdit", 
                    account=account, 
                    type='info'
                )
            except Exception as e:
                print(f"Failed to create notification: {e}")
        
        log.credit_from_free += 1
    elif hasattr(user, 'subscription') and user.subscription.credit > 0:
        user.subscription.credit -= 1
        user.subscription.save()
        log.credit_from_plan += 1
    else:
        user.credit.balance -= 1
        user.credit.save()
        log.credit_from_plan += 1

    # 5. Finalize Log
    log.count += 1
    log.last_success_at = timezone.now()
    log.save()
    
    return True


def _log_blocked_attempt(user, account, post_type, date, msg, title):
    """Helper to log blocked attempts and create notifications."""
    log, _ = UsageLog.objects.get_or_create(
        user=user,
        account=account,
        key=post_type,
        date=date
    )
    log.blocked_count += 1
    log.save()
    
    try:
        from apps.platforms.utils import create_notification
        create_notification(
            user, 
            title, 
            msg, 
            account=account, 
            type='warning'
        )
    except Exception as e:
        print(f"Failed to create notification: {e}")


def get_reset_time(user, account=None):
    """Calculates the next time a user can perform an action on a specific account."""
    now = timezone.now()
    today = now.date()
    
    # 1. Check Daily Limit
    daily_quota = get_quota(user, "posts_per_day")
    if daily_quota > 0 and account:
        # Check usage for this specific account today
        today_usage = UsageLog.objects.filter(
            user=user, 
            account=account,
            date=today
        ).aggregate(total=Sum('count'))['total'] or 0
        
        if today_usage >= daily_quota:
            # Find the MOST RECENT successful upload for THIS account
            last_log = UsageLog.objects.filter(
                user=user, 
                account=account,
                last_success_at__isnull=False
            ).order_by('-last_success_at').first()
            
            if last_log and last_log.last_success_at:
                # Next resume time is exactly 24 hours after the last successful post on this account
                return last_log.last_success_at + timedelta(hours=24)
            
            # Fallback to midnight if no log found
            tomorrow = today + timedelta(days=1)
            return timezone.make_aware(timezone.datetime.combine(tomorrow, timezone.datetime.min.time()))
            
    return None
