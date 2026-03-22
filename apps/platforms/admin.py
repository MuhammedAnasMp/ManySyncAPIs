from django.contrib import admin
from .models import PlatformAccount, ApiUsageLog, Webhook, DeveloperApp, DeveloperAppAccount

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


@admin.register(DeveloperApp)
class DeveloperAppAdmin(admin.ModelAdmin):
    list_display = ('app_name', 'platform', 'user', 'created_at')
    list_filter = ('platform', 'user')
    search_fields = ('app_name', 'user__username')

@admin.register(DeveloperAppAccount)
class DeveloperAppAccountAdmin(admin.ModelAdmin):
    list_display = ('account_name', 'developer_app', 'is_active', 'created_at')
    list_filter = ('developer_app', 'is_active')
    search_fields = ('account_name', 'developer_app__app_name')