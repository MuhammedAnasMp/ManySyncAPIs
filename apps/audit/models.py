from django.db import models
from apps.base import BaseModel
from django.conf import settings

class AuditLog(BaseModel):
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, related_name='audit_logs')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='audit_logs')
    action = models.CharField(max_length=255)
    entity_type = models.CharField(max_length=100) # e.g., 'Media', 'ScheduledPost'
    entity_id = models.UUIDField(null=True, blank=True)

    def __str__(self):
        return f"{self.user} performed {self.action} on {self.entity_type}"

# Create your models here.
