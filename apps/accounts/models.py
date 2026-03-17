from django.db import models
from django.contrib.auth.models import AbstractUser
from apps.base import BaseModel

class User(AbstractUser, BaseModel):
    name = models.CharField(max_length=255, blank=True)
    role = models.CharField(max_length=50, blank=True)
    
    # Email is unique by default in many custom setups, merging with AbstractUser's email
    
    def __str__(self):
        return self.email or self.username

