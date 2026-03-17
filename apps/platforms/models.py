from django.db import models
from apps.base import BaseModel
from django.utils import timezone
class PlatformAccount(BaseModel):
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, related_name='platform_accounts')
    platform = models.CharField(max_length=50) # e.g., 'meta', 'youtube'
    
    account_type = models.CharField(
        max_length=50,
        choices=[
            ("facebook_user", "Facebook User"),
            ("instagram_business", "Instagram Business"),
            ("facebook_page", "Facebook Page"),
            ("whatsapp_business", "WhatsApp Business"),
        ],
        null=True,
        blank=True,
    )
    parent_account = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='child_accounts'
    )
    
    meta_user_id = models.CharField(max_length=255, null=True, blank=True)
    external_parent_id = models.CharField(max_length=255, null=True, blank=True)
    external_parent_name = models.CharField(max_length=255, null=True, blank=True)
    
    platform_user_id = models.CharField(max_length=255)
    username = models.CharField(max_length=255)
    display_name = models.CharField(max_length=255, blank=True)
    profile_picture_url = models.URLField(max_length=500, null=True, blank=True)
    
    # Encrypted tokens (using text for now as placeholders for actual encryption logic)
    access_token_encrypted = models.TextField()
    refresh_token_encrypted = models.TextField(null=True, blank=True)
    token_type = models.CharField(max_length=50, blank=True)
    scope = models.TextField(blank=True)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    refresh_token_expires_at = models.DateTimeField(null=True, blank=True)
    last_refreshed_at = models.DateTimeField(null=True, blank=True)
    
    followers_count = models.BigIntegerField(default=0)
    follows_count = models.BigIntegerField(default=0)
    media_count = models.BigIntegerField(default=0)
    subscribers_count = models.BigIntegerField(default=0)
    total_views = models.BigIntegerField(default=0)
    
    status = models.CharField(max_length=50, default='active')

    def soft_delete(self):
        """
        Recursively soft deletes this account and all its children.
        """
        self.deleted_at = timezone.now()
        self.status = 'deleted'
        self.save()
        
        # Soft delete children
        for child in self.child_accounts.all():
            child.soft_delete()

    def __str__(self):
        return f"{self.platform} - {self.username}"
    # platform_user_id must unique
    class Meta:
        unique_together = ('platform_user_id', 'platform')

class ApiUsageLog(BaseModel):
    platform_account = models.ForeignKey(PlatformAccount, on_delete=models.CASCADE, related_name='api_usage_logs')
    endpoint = models.CharField(max_length=255)
    request_count = models.IntegerField(default=1)
    usage_date = models.DateField(auto_now_add=True)

    def __str__(self):
        return f"{self.platform_account} - {self.endpoint} on {self.usage_date}"

class Webhook(BaseModel):
    platform_account = models.ForeignKey(PlatformAccount, on_delete=models.CASCADE, related_name='webhooks', null=True, blank=True)
    platform = models.CharField(max_length=50)
    event_type = models.CharField(max_length=255)
    event_id = models.CharField(max_length=255, unique=True)
    payload_json = models.JSONField()
    processed = models.BooleanField(default=False)
    received_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Webhook {self.event_id} from {self.platform}"

# Create your models here.
