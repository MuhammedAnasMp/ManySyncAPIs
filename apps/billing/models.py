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

class Usage(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="usages")
    key = models.CharField(max_length=50)
    used = models.IntegerField(default=0)
    period_start = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'key')

    def __str__(self):
        return f"{self.user} - {self.key}: {self.used}"

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
