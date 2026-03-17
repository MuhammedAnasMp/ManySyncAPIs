from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from .models import ScheduledPost, ScheduledPostTarget
from .serializers import ScheduledPostSerializer, ScheduledPostTargetSerializer

class ScheduledPostViewSet(viewsets.ModelViewSet):
    serializer_class = ScheduledPostSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        workspace_id = self.request.query_params.get('workspace')
        queryset = ScheduledPost.objects.filter(created_by=self.request.user)
        if workspace_id:
            queryset = queryset.filter(workspace_id=workspace_id)
        return queryset.order_by('-scheduled_for')

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

class ScheduledPostTargetViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ScheduledPostTargetSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ScheduledPostTarget.objects.filter(scheduled_post__created_by=self.request.user)
