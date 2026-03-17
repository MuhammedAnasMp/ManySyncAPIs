from django.db import models
from apps.base import BaseModel

class Media(BaseModel):
    platform_account = models.ForeignKey('platforms.PlatformAccount', on_delete=models.CASCADE, related_name='media')
    platform_media_id = models.CharField(max_length=255)
    type = models.CharField(max_length=50) # image, video, reel, etc.
    title = models.CharField(max_length=255, blank=True)
    caption = models.TextField(blank=True)
    thumbnail_url = models.URLField(max_length=500, null=True, blank=True)
    video_url = models.URLField(max_length=500, null=True, blank=True)
    duration_seconds = models.IntegerField(null=True, blank=True)
    
    # Aggregated metrics
    views = models.BigIntegerField(default=0)
    likes = models.BigIntegerField(default=0)
    comments_count = models.BigIntegerField(default=0)
    shares = models.BigIntegerField(default=0)
    reach = models.BigIntegerField(default=0)
    impressions = models.BigIntegerField(default=0)
    engagement_rate = models.FloatField(default=0.0)
    
    published_at = models.DateTimeField()

    def __str__(self):
        return self.title or f"Media {self.platform_media_id}"

class MediaPlatformCrosspost(BaseModel):
    master_media = models.ForeignKey(Media, on_delete=models.CASCADE, related_name='crossposts')
    platform_account = models.ForeignKey('platforms.PlatformAccount', on_delete=models.CASCADE, related_name='crossposts')
    platform_media_id = models.CharField(max_length=255, null=True, blank=True)
    status = models.CharField(max_length=50, default='pending')
    error_message = models.TextField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Crosspost of {self.master_media} to {self.platform_account}"

class MediaAnalyticsDaily(BaseModel):
    media = models.ForeignKey(Media, on_delete=models.CASCADE, related_name='daily_analytics')
    date = models.DateField()
    views = models.BigIntegerField(default=0)
    likes = models.BigIntegerField(default=0)
    comments = models.BigIntegerField(default=0)
    shares = models.BigIntegerField(default=0)
    reach = models.BigIntegerField(default=0)
    impressions = models.BigIntegerField(default=0)
    engagement_rate = models.FloatField(default=0.0)

    class Meta:
        unique_together = ('media', 'date')

class AccountAnalyticsDaily(BaseModel):
    platform_account = models.ForeignKey('platforms.PlatformAccount', on_delete=models.CASCADE, related_name='daily_analytics')
    date = models.DateField()
    followers = models.BigIntegerField(default=0)
    subscribers = models.BigIntegerField(default=0)
    total_views = models.BigIntegerField(default=0)
    total_reach = models.BigIntegerField(default=0)
    total_engagement = models.BigIntegerField(default=0)
    engagement_rate = models.FloatField(default=0.0)

    class Meta:
        unique_together = ('platform_account', 'date')

class Comment(BaseModel):
    platform_account = models.ForeignKey('platforms.PlatformAccount', on_delete=models.CASCADE, related_name='received_comments')
    media = models.ForeignKey(Media, on_delete=models.CASCADE, related_name='comments')
    platform_comment_id = models.CharField(max_length=255)
    username = models.CharField(max_length=255)
    comment_text = models.TextField()
    is_replied = models.BooleanField(default=False)

    def __str__(self):
        return f"Comment by {self.username} on {self.media}"

# Create your models here.
