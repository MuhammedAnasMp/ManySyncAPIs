from django.contrib import admin
from .models import AuditLog

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('action', 'user', 'workspace', 'entity_type', 'created_at')
    list_filter = ('action', 'entity_type', 'workspace')
    search_fields = ('action', 'user__email', 'workspace__name')
    readonly_fields = ('created_at',)
