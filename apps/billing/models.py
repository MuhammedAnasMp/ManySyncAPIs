from django.db import models
from django.conf import settings
from django.utils import timezone

User = settings.AUTH_USER_MODEL

class Plan(models.Model):
    name = models.CharField(max_length=50)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

class Feature(models.Model):
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.code

class PlanFeature(models.Model):
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name="features")
    feature = models.ForeignKey(Feature, on_delete=models.CASCADE, related_name="plans")
    enabled = models.BooleanField(default=False)

    class Meta:
        unique_together = ('plan', 'feature')

    def __str__(self):
        return f"{self.plan.name} - {self.feature.code}: {'Enabled' if self.enabled else 'Disabled'}"

    
class PlanKey(models.Model):
    name = models.CharField(max_length=50)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name

class PlanQuota(models.Model):
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name="quotas")
    key = models.ForeignKey(PlanKey, on_delete=models.CASCADE, related_name="plans")
    value = models.IntegerField()

    class Meta:
        unique_together = ('plan', 'key')

    def __str__(self):
        return f"{self.plan.name} - {self.key}: {self.value}"

class Subscription(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="subscription")
    plan = models.ForeignKey(Plan, on_delete=models.SET_NULL, null=True, related_name="subscriptions")
    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    credit = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.user} - {self.plan.name if self.plan else 'No Plan'}"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        old_plan = None
        if not is_new:
            try:
                old_plan = Subscription.objects.get(pk=self.pk).plan
            except Subscription.DoesNotExist:
                pass
            
        # If plan changed (e.g. downgrade/upgrade), calculate credits BEFORE saving
        if old_plan != self.plan and self.plan:
             PLAN_RANK = {'Free': 0, 'Starter': 1, 'Creator': 2, 'Pro': 3}
             old_rank = PLAN_RANK.get(old_plan.name, -1) if old_plan else -1
             new_rank = PLAN_RANK.get(self.plan.name, 0)
             
             if new_rank > old_rank:
                 from apps.billing.models import PlanQuota
                 pq = PlanQuota.objects.filter(plan=self.plan, key__name='posts_per_month').first()
                 if pq:
                     self.credit += pq.value

        super().save(*args, **kwargs)
        
        # If plan changed (e.g. downgrade/upgrade), or account_count might have changed
        if old_plan != self.plan:
            from apps.platforms.models import DeveloperAppAccount
            from apps.billing.utils import get_quota
            quota = get_quota(self.user, "account_count")
            
            # Current status
            active_accounts = DeveloperAppAccount.objects.filter(user=self.user, is_active=True).order_by('created_at')
            active_count = active_accounts.count()

            if active_count > quota:
                # Deactivate extra (Downgrade)
                for acc in active_accounts[quota:]:
                    acc.is_active = False
                    acc.save()
            elif active_count < quota:
                # Reactivate paused (Upgrade)
                paused_accounts = DeveloperAppAccount.objects.filter(user=self.user, is_active=False).order_by('created_at')
                available_slots = quota - active_count
                if paused_accounts.exists() and available_slots > 0:
                    for acc in paused_accounts[:available_slots]:
                        acc.is_active = True
                        acc.save()

class Usage(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="usages")
    key = models.CharField(max_length=50)
    used = models.IntegerField(default=0)
    period_start = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'key')

    def __str__(self):
        return f"{self.user} - {self.key}: {self.used}"

class UsageLog(models.Model):
    """Daily history log for tracking user activity over time."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="usage_logs")
    account = models.ForeignKey(
        'platforms.DeveloperAppAccount',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='usage_logs',
        help_text="The Instagram account that triggered this usage entry."
    )
    key = models.CharField(max_length=50)
    date = models.DateField()
    count = models.IntegerField(default=0)
    blocked_count = models.IntegerField(default=0)

    class Meta:
        unique_together = ('user', 'key', 'date', 'account')
        ordering = ['-date']

    def __str__(self):
        acc = f" [{self.account}]" if self.account_id else ""
        return f"{self.user}{acc} - {self.key}: {self.count} on {self.date}"


class Credit(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="credit")
    balance = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.user} - Credits: {self.balance}"

class Transaction(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="transactions")
    item_name = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default='INR')
    razorpay_order_id = models.CharField(max_length=255, blank=True, null=True)
    razorpay_payment_id = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=50, default='success')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user} - {self.item_name} - {self.amount}"
