from django.contrib import admin
from .models import (
    Media, MediaPlatformCrosspost, MediaAnalyticsDaily, 
    AccountAnalyticsDaily, Comment
)

@admin.register(Media)
class MediaAdmin(admin.ModelAdmin):
    list_display = ('title', 'platform_account', 'type', 'published_at')
    list_filter = ('type', 'published_at', 'platform_account__platform')
    search_fields = ('title', 'caption', 'platform_media_id')

@admin.register(MediaPlatformCrosspost)
class MediaPlatformCrosspostAdmin(admin.ModelAdmin):
    list_display = ('master_media', 'platform_account', 'status', 'published_at')
    list_filter = ('status', 'platform_account__platform')

@admin.register(MediaAnalyticsDaily)
class MediaAnalyticsDailyAdmin(admin.ModelAdmin):
    list_display = ('media', 'date', 'views', 'likes', 'engagement_rate')
    list_filter = ('date',)

@admin.register(AccountAnalyticsDaily)
class AccountAnalyticsDailyAdmin(admin.ModelAdmin):
    list_display = ('platform_account', 'date', 'followers', 'engagement_rate')
    list_filter = ('date', 'platform_account__platform')

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('username', 'media', 'is_replied', 'created_at')
    list_filter = ('is_replied', 'created_at')
    search_fields = ('username', 'comment_text')
