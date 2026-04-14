from django.contrib import admin 
from .models import PlatformAccount, ApiUsageLog, Webhook, DeveloperAppAccount ,Template ,AccountTemplateConfiguration ,AccountTemplate

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




@admin.register(DeveloperAppAccount)
class DeveloperAppAccountAdmin(admin.ModelAdmin):
    list_display = ('account_name', 'account_id', 'is_active', 'is_verified', 'is_flagged', 'psid')
    list_filter = ('is_active',)
    search_fields = ('account_name', 'account_id')


@admin.register(Template)
class TemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_by', 'created_at', 'template_type')

@admin.register(AccountTemplateConfiguration)
class AccountTemplateConfigurationAdmin(admin.ModelAdmin):
    list_display = ('account', 'template_type', 'created_at', 'updated_at')

@admin.register(AccountTemplate)
class AccountTemplateAdmin(admin.ModelAdmin):
    list_display = ('account', 'template_type', 'template')
