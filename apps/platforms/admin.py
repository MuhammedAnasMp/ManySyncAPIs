from django.contrib import admin
from .models import PlatformAccount, ApiUsageLog, Webhook

@admin.register(PlatformAccount)
class PlatformAccountAdmin(admin.ModelAdmin):
    list_display = ('username', 'platform', 'workspace', 'status', 'created_at')
    list_filter = ('platform', 'status', 'workspace')
    search_fields = ('username', 'display_name', 'workspace__name')

@admin.register(ApiUsageLog)
class ApiUsageLogAdmin(admin.ModelAdmin):
    list_display = ('platform_account', 'endpoint', 'request_count', 'usage_date')
    list_filter = ('usage_date', 'platform_account__platform')

@admin.register(Webhook)
class WebhookAdmin(admin.ModelAdmin):
    list_display = ('event_id', 'platform', 'event_type', 'processed', 'received_at')
    list_filter = ('platform', 'processed', 'received_at')
    readonly_fields = ('received_at',)
