from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('email', 'username', 'name', 'role', 'is_staff', 'created_at')
    search_fields = ('email', 'username', 'name')
    ordering = ('-created_at',)
    
    fieldsets = UserAdmin.fieldsets + (
        ('Extra Fields', {'fields': ('name', 'role', 'deleted_at')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Extra Fields', {'fields': ('name', 'role')}),
    )
