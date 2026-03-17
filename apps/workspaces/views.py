from rest_framework import generics, permissions, viewsets, status
from rest_framework.response import Response
from django.db.models import Q
from .models import Workspace, WorkspaceMember, WorkspaceInvitation
from .serializers import WorkspaceSerializer, WorkspaceMemberSerializer, WorkspaceInvitationSerializer

class WorkspaceInvitationViewSet(viewsets.ModelViewSet):
    serializer_class = WorkspaceInvitationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Only show invitations for workspaces the user owns
        return WorkspaceInvitation.objects.filter(workspace__owner=self.request.user)

    def destroy(self, request, *args, **kwargs):
        # Only owner can cancel invitations
        instance = self.get_object()
        if instance.workspace.owner != request.user:
            return Response({"error": "Only the workspace owner can cancel invitations."}, status=status.HTTP_403_FORBIDDEN)
        return super().destroy(request, *args, **kwargs)

class WorkspaceListCreateView(generics.ListCreateAPIView):
    serializer_class = WorkspaceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Return workspaces where the user is an owner OR a member
        return Workspace.objects.filter(
            Q(owner=self.request.user) | Q(members__user=self.request.user)
        ).distinct()

    def perform_create(self, serializer):
        serializer.save()

class WorkspaceDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = WorkspaceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Workspace.objects.filter(
            Q(owner=self.request.user) | Q(members__user=self.request.user)
        ).distinct()

class WorkspaceMemberViewSet(viewsets.ModelViewSet):
    serializer_class = WorkspaceMemberSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Only show members of workspaces the user has access to
        return WorkspaceMember.objects.filter(
            Q(workspace__owner=self.request.user) | 
            Q(workspace__members__user=self.request.user)
        ).distinct()

    def create(self, request, *args, **kwargs):
        # Only owner can add members
        workspace_id = request.data.get('workspace')
        email = request.data.get('user_email')
        
        try:
            workspace = Workspace.objects.get(id=workspace_id, owner=request.user)
        except Workspace.DoesNotExist:
            return Response({"error": "Only the workspace owner can invite members."}, status=status.HTTP_403_FORBIDDEN)
        
        if not email:
            return Response({"error": "Email is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Check if user exists
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.filter(email=email).first()

        if user:
            # Add existing user as member
            return super().create(request, *args, **kwargs)
        else:
            # Create invitation for non-existent user
            from .models import WorkspaceInvitation
            from .serializers import WorkspaceInvitationSerializer
            from .utils import send_invitation_email
            
            # Use get_or_create to avoid duplicates if invited again
            invitation, created = WorkspaceInvitation.objects.get_or_create(
                workspace=workspace,
                email=email,
                defaults={
                    'invited_by': request.user,
                    'role': request.data.get('role', 'member')
                }
            )
            
            # Send invitation mail using Firebase
            send_invitation_email(email, workspace.name, request.user.name or request.user.username)
            
            serializer = WorkspaceInvitationSerializer(invitation)
            return Response({
                "message": "Invitation sent successfully. The user will be added once they sign up.",
                "invitation": serializer.data
            }, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        # Only owner can remove members
        instance = self.get_object()
        if instance.workspace.owner != request.user:
            return Response({"error": "Only the workspace owner can remove members."}, status=status.HTTP_403_FORBIDDEN)
        
        if instance.user == instance.workspace.owner:
            return Response({"error": "The owner cannot be removed from the workspace."}, status=status.HTTP_400_BAD_REQUEST)
            
        return super().destroy(request, *args, **kwargs)
