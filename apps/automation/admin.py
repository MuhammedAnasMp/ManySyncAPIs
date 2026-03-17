from django.contrib import admin
from .models import AutomationRule, AutomationLog

@admin.register(AutomationRule)
class AutomationRuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'workspace', 'trigger_type', 'is_active', 'execution_count')
    list_filter = ('trigger_type', 'is_active', 'workspace')
    search_fields = ('name', 'workspace__name')

@admin.register(AutomationLog)
class AutomationLogAdmin(admin.ModelAdmin):
    list_display = ('automation_rule', 'status', 'triggered_at')
    list_filter = ('status', 'triggered_at')
