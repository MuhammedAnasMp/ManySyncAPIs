from django.contrib import admin
from .models import Workspace, Subscription, WorkspaceMember, WorkspaceInvitation

@admin.register(Workspace)
class WorkspaceAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'plan', 'is_active', 'created_at')
    list_filter = ('plan', 'is_active')
    search_fields = ('name', 'owner__email')
    ordering = ('-created_at',)

@admin.register(WorkspaceMember)
class WorkspaceMemberAdmin(admin.ModelAdmin):
    list_display = ('user', 'workspace', 'role', 'created_at')
    list_filter = ('role', 'workspace')
    search_fields = ('user__email', 'workspace__name')

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('workspace', 'plan', 'status', 'current_period_end')
    list_filter = ('plan', 'status')
    search_fields = ('workspace__name',)
