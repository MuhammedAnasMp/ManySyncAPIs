from django.db import models
from apps.base import BaseModel
from django.utils import timezone
from django.conf import settings

User = settings.AUTH_USER_MODEL
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

class DeveloperAppAccount(models.Model):
    user = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='connected_accounts',
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    account_name = models.CharField(max_length=255)
    account_id = models.CharField(max_length=255, null=True, blank=True ,unique=True)
    profile_picture_url = models.URLField(max_length=1000, null=True, blank=True)
    access_token = models.TextField(null=True, blank=True)
    psid = models.CharField(max_length=255, null=True, blank=True, unique=True)
    is_verified = models.BooleanField(default=False)
    is_flagged = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    followers_count = models.BigIntegerField(default=0)
    follows_count = models.BigIntegerField(default=0)
    media_count = models.BigIntegerField(default=0)

    def __str__(self):
        return self.account_name



TEMPLATE_CHOICES = [
        ('image', 'Image'),
        ('reel', 'Reel'),
        ('story', 'Story'),
        ('video', 'Video'),
    ]
class Template(models.Model):
    name = models.CharField(max_length=255)
    template_type = models.CharField(max_length=10, choices=TEMPLATE_CHOICES)
    template_json = models.JSONField()  # Stores full template design
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="templates")
    is_public = models.BooleanField(default=False)
    parent_template = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL
    )

    def __str__(self):
        return f"{self.template_type} template {self.id}"

class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    account = models.ForeignKey('DeveloperAppAccount', on_delete=models.SET_NULL, null=True, blank=True, related_name="notifications")
    title = models.CharField(max_length=255)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    TYPE_CHOICES = [
        ('success', 'Success'),
        ('warning', 'Warning'),
        ('error', 'Error'),
        ('info', 'Info'),
    ]
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='info')

    def __str__(self):
        return f"{self.user.username if self.user else 'System'} - {self.title}"

    class Meta:
        ordering = ['-created_at']
    

class AccountTemplate(models.Model):
    account = models.ForeignKey(
        DeveloperAppAccount,
        on_delete=models.CASCADE,
        related_name='account_templates'
    )
    template = models.ForeignKey(
        Template,
        on_delete=models.SET_NULL,  # 👈 important
        null=True,
        blank=True
    )
    template_type = models.CharField(max_length=10, choices=TEMPLATE_CHOICES)

    class Meta:
        unique_together = ('account', 'template_type')


class AccountTemplateConfiguration(models.Model):
    account = models.ForeignKey(
        DeveloperAppAccount,
        on_delete=models.CASCADE,
        related_name='template_configurations'
    )

    template_type = models.CharField(max_length=10, choices=TEMPLATE_CHOICES)

    configuration = models.JSONField(default=dict)
    # Example:
    # {
    #   "default_caption": "Hello world",
    #   "default_hashtags": ["#fun", "#ai"]
    # }

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('account', 'template_type')