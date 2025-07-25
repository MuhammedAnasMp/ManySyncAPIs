from django.contrib.auth.models import AbstractUser
from django.db import models

class UserProfile(AbstractUser):
    firebase_uid = models.CharField(max_length=128, unique=True, blank=True, null=True)
    photo = models.URLField(max_length=500, blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)

    def __str__(self):
        return self.username



import uuid
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

User = get_user_model()

class CustomSession(models.Model):
    session_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    def is_valid(self):
        return timezone.now() < self.expires_at

    def __str__(self):
        return f"{self.user.email} - {self.session_token}"
