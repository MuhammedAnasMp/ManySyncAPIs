from .models import PlanFeature, PlanQuota, Usage

def has_feature(user, feature_code):
    """Check if a user's plan has a specific feature enabled."""
    if not hasattr(user, 'subscription') or not user.subscription.plan:
        return False
        
    return PlanFeature.objects.filter(
        plan=user.subscription.plan,
        feature__code=feature_code,
        enabled=True
    ).exists()

def get_quota(user, key):
    """Get the numeric quota limit for a specific key based on user's plan."""
    if not hasattr(user, 'subscription') or not user.subscription.plan:
        return 0
        
    quota = PlanQuota.objects.filter(
        plan=user.subscription.plan,
        key=key
    ).first()
    
    return quota.value if quota else 0

def can_post(user):
    """Check if the user has enough quota to post."""
    quota = get_quota(user, "posts_per_month")
    usage, created = Usage.objects.get_or_create(user=user, key="posts_per_month")
    
    return usage.used < quota

def consume_post(user):
    """Consume a post action, deducting from quota first, fallback to credits."""
    usage, created = Usage.objects.get_or_create(user=user, key="posts_per_month")
    
    if can_post(user):
        # use quota first
        usage.used += 1
        usage.save()
        return True
    else:
        # fallback to credits
        if hasattr(user, 'credit') and user.credit.balance > 0:
            user.credit.balance -= 1
            user.credit.save()
            return True
        else:
            raise Exception("Limit exceeded: Not enough quota or credits to perform this action.")
