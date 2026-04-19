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
    # 1. Credits check (Primary allowance)
    has_sub_credit = hasattr(user, 'subscription') and user.subscription.credit > 0
    has_extra_credit = hasattr(user, 'credit') and user.credit.balance > 0
    
    if not (has_sub_credit or has_extra_credit):
        return False

    # 2. Daily check
    daily_quota = get_quota(user, "posts_per_day")
    if daily_quota > 0 and account:
        today = timezone.now().date()
        # Check usage for this specific account
        today_usage = UsageLog.objects.filter(
            user=user, 
            account=account,
            date=today
        ).aggregate(total=Sum('count'))['total'] or 0
        
        if today_usage >= daily_quota:
            return False
            
    return True


def consume_post(user, account=None, post_type="post"):
    """
    Consume a post action, updating daily UsageLog.
    post_type can be: 'reel', 'image', 'video', 'story', etc.
    """
    today = timezone.now().date()
    
    # 1. Check for Credit Exhaustion
    has_sub_credit = hasattr(user, 'subscription') and user.subscription.credit > 0
    has_extra_credit = hasattr(user, 'credit') and user.credit.balance > 0
    
    if not (has_sub_credit or has_extra_credit):
        error_msg = "You have run out of credits. Please renew your subscription or purchase more credits."
        _log_blocked_attempt(user, account, post_type, today, error_msg, "Quota Exceeded")
        raise Exception(error_msg)

    # 2. Check for Daily Limit
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

    # 3. Successful Consumption Logic
    if hasattr(user, 'subscription') and user.subscription.credit > 0:
        user.subscription.credit -= 1
        user.subscription.save()
    else:
        # We already checked that at least one must be > 0
        user.credit.balance -= 1
        user.credit.save()

    # 4. Update Daily UsageLog
    log, _ = UsageLog.objects.get_or_create(
        user=user,
        account=account,
        key=post_type,
        date=today
    )
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
