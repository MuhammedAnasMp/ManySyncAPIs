from django.db import models
from apps.base import BaseModel

class AutomationRule(BaseModel):
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, related_name='automation_rules')
    name = models.CharField(max_length=255)
    trigger_type = models.CharField(max_length=100) # e.g., 'on_comment', 'on_follower_milestone'
    conditions_json = models.JSONField(default=dict)
    actions_json = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)
    version = models.IntegerField(default=1)
    last_executed_at = models.DateTimeField(null=True, blank=True)
    execution_count = models.IntegerField(default=0)

    def __str__(self):
        return self.name

class AutomationLog(BaseModel):
    automation_rule = models.ForeignKey(AutomationRule, on_delete=models.CASCADE, related_name='logs')
    triggered_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=50) # success, failure
    log_data = models.JSONField(default=dict)

    def __str__(self):
        return f"Log for {self.automation_rule.name} at {self.triggered_at}"

# Create your models here.
