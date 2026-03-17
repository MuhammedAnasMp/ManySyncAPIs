from django.contrib import admin
from .models import ScheduledPost, ScheduledPostTarget, JobQueue

@admin.register(ScheduledPost)
class ScheduledPostAdmin(admin.ModelAdmin):
    list_display = ('workspace', 'created_by', 'scheduled_for', 'status')
    list_filter = ('status', 'scheduled_for', 'workspace')
    search_fields = ('title', 'caption', 'workspace__name')

@admin.register(ScheduledPostTarget)
class ScheduledPostTargetAdmin(admin.ModelAdmin):
    list_display = ('scheduled_post', 'platform_account', 'status', 'published_at')
    list_filter = ('status', 'platform_account__platform')

@admin.register(JobQueue)
class JobQueueAdmin(admin.ModelAdmin):
    list_display = ('type', 'status', 'scheduled_for', 'retries')
    list_filter = ('type', 'status', 'scheduled_for')
