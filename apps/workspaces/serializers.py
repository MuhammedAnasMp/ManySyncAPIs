from rest_framework import serializers
from .models import Workspace, WorkspaceMember, WorkspaceInvitation
from django.contrib.auth import get_user_model

User = get_user_model()

class UserMinimalSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'name']

class WorkspaceMemberSerializer(serializers.ModelSerializer):
    user_details = UserMinimalSerializer(source='user', read_only=True)
    user_email = serializers.EmailField(write_only=True)

    class Meta:
        model = WorkspaceMember
        fields = ['id', 'workspace', 'user', 'user_email', 'user_details', 'role', 'created_at']
        read_only_fields = ['id', 'user', 'created_at'] # Removed 'workspace' from here

    def create(self, validated_data):
        email = validated_data.pop('user_email')
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError({"user_email": "User with this email does not exist."})
        
        validated_data['user'] = user
        return super().create(validated_data)

class WorkspaceInvitationSerializer(serializers.ModelSerializer):
    invited_by_details = UserMinimalSerializer(source='invited_by', read_only=True)

    class Meta:
        model = WorkspaceInvitation
        fields = ['id', 'workspace', 'email', 'role', 'status', 'invited_by', 'invited_by_details', 'created_at']
        read_only_fields = ['id', 'status', 'invited_by', 'created_at']

class WorkspaceSerializer(serializers.ModelSerializer):
    members = WorkspaceMemberSerializer(many=True, read_only=True)
    invitations = serializers.SerializerMethodField()
    is_owner = serializers.SerializerMethodField()

    class Meta:
        model = Workspace
        fields = ['id', 'name', 'logo_url', 'plan', 'is_active', 'created_at', 'members', 'invitations', 'is_owner']
        read_only_fields = ['id', 'created_at']

    def get_invitations(self, obj):
        # Only return pending invitations
        pending_invites = obj.invitations.filter(status='pending')
        return WorkspaceInvitationSerializer(pending_invites, many=True).data

    def get_is_owner(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.owner == request.user
        return False

    def create(self, validated_data):
        user = self.context['request'].user
        workspace = Workspace.objects.create(owner=user, **validated_data)
        # Auto-create owner member entry
        WorkspaceMember.objects.create(workspace=workspace, user=user, role='owner')
        return workspace
