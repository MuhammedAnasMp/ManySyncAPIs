from django.db import models
from apps.base import BaseModel
from django.conf import settings

class ScheduledPost(BaseModel):
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, related_name='scheduled_posts')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_posts')
    
    media_storage_path = models.CharField(max_length=500)
    mime_type = models.CharField(max_length=100)
    file_size = models.BigIntegerField()
    upload_status = models.CharField(max_length=50, default='pending')
    processing_status = models.CharField(max_length=50, default='pending')
    
    title = models.CharField(max_length=255, blank=True)
    caption = models.TextField(blank=True)
    thumbnail_url = models.URLField(max_length=500, null=True, blank=True)
    
    scheduled_for = models.DateTimeField()
    status = models.CharField(max_length=50, default='scheduled') # scheduled, publishing, published, failed, cancelled

    def __str__(self):
        return f"Post for {self.workspace.name} at {self.scheduled_for}"

class ScheduledPostTarget(BaseModel):
    scheduled_post = models.ForeignKey(ScheduledPost, on_delete=models.CASCADE, related_name='targets')
    platform_account = models.ForeignKey('platforms.PlatformAccount', on_delete=models.CASCADE, related_name='scheduled_targets')
    
    custom_title = models.CharField(max_length=255, null=True, blank=True)
    custom_caption = models.TextField(null=True, blank=True)
    custom_thumbnail_url = models.URLField(max_length=500, null=True, blank=True)
    
    status = models.CharField(max_length=50, default='pending')
    error_message = models.TextField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Target {self.platform_account} for {self.scheduled_post}"

class JobQueue(BaseModel):
    type = models.CharField(max_length=100) # e.g., 'publish_post', 'refresh_analytics'
    payload_json = models.JSONField()
    status = models.CharField(max_length=50, default='pending') # pending, running, completed, failed
    retries = models.IntegerField(default=0)
    last_error = models.TextField(null=True, blank=True)
    scheduled_for = models.DateTimeField()

    def __str__(self):
        return f"Job {self.type} ({self.status})"

# Create your models here.
