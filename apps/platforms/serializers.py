from rest_framework import serializers
from .models import PlatformAccount, DeveloperApp, DeveloperAppAccount

class PlatformAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlatformAccount
        fields = [
            'id', 'platform', 'account_type', 'meta_user_id', 
            'parent_account', 'external_parent_id', 'external_parent_name',
            'username', 'display_name', 'profile_picture_url', 'status', 
            'followers_count', 'follows_count', 'media_count',
            'subscribers_count', 'total_views', 
            'token_expires_at', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

class DeveloperAppAccountSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(required=False, allow_blank=True)
    account_id = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = DeveloperAppAccount
        fields = ['id', 'developer_app', 'account_name', 'account_id', 'profile_picture_url', 'access_token', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']

class DeveloperAppSerializer(serializers.ModelSerializer):
    associated_accounts = DeveloperAppAccountSerializer(many=True, read_only=True)

    class Meta:
        model = DeveloperApp
        fields = ['id', 'user', 'app_name', 'platform', 'app_id', 'app_secret', 'associated_accounts', 'created_at']
        read_only_fields = ['id', 'user', 'created_at']
