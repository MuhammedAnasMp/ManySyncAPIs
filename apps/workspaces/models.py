from django.db import models
from apps.base import BaseModel
from django.conf import settings

class Workspace(BaseModel):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='owned_workspaces')
    name = models.CharField(max_length=255)
    logo_url = models.URLField(max_length=500, null=True, blank=True)
    plan = models.CharField(max_length=50, default='free')
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

class Subscription(BaseModel):
    workspace = models.OneToOneField(Workspace, on_delete=models.CASCADE, related_name='subscription')
    plan = models.CharField(max_length=50)
    status = models.CharField(max_length=50)
    limits_json = models.JSONField(default=dict)
    current_period_start = models.DateTimeField()
    current_period_end = models.DateTimeField()

    def __str__(self):
        return f"{self.workspace.name} - {self.plan}"

class WorkspaceMember(BaseModel):
    ROLE_CHOICES = (
        ('owner', 'Owner'),
        ('member', 'Member'),
    )
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='workspace_memberships')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')

    class Meta:
        unique_together = ('workspace', 'user')

    def __str__(self):
        return f"{self.user.email} - {self.workspace.name} ({self.role})"

class WorkspaceInvitation(BaseModel):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('expired', 'Expired'),
    )
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name='invitations')
    email = models.EmailField()
    role = models.CharField(max_length=20, choices=WorkspaceMember.ROLE_CHOICES, default='member')
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_invitations')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    class Meta:
        unique_together = ('workspace', 'email')

    def __str__(self):
        return f"Invite to {self.email} for {self.workspace.name}"
