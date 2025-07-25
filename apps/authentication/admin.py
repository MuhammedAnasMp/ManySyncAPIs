# apps/authentication/admin.py
from django.contrib import admin
from apps.authentication.models import UserProfile,CustomSession


admin.site.register(UserProfile)
admin.site.register(CustomSession)