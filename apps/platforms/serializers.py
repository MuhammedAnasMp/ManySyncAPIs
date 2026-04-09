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
        fields = ['id', 'developer_app', 'account_name', 'account_id', 'profile_picture_url', 'access_token', 'is_active', 'is_verified', 'is_flagged', 'followers_count', 'follows_count', 'media_count', 'created_at']
        read_only_fields = ['id', 'created_at']

class DeveloperAppSerializer(serializers.ModelSerializer):
    associated_accounts = DeveloperAppAccountSerializer(many=True, read_only=True)

    class Meta:
        model = DeveloperApp
        fields = ['id', 'user', 'app_name', 'platform', 'app_id', 'app_secret', 'associated_accounts', 'created_at']
        read_only_fields = ['id', 'user', 'created_at']

from .models import Template, AccountTemplate, AccountTemplateConfiguration

class TemplateSerializer(serializers.ModelSerializer):
    used_by_accounts = serializers.SerializerMethodField()

    class Meta:
        model = Template
        fields = '__all__'
        read_only_fields = ['created_by']

    def get_used_by_accounts(self, obj):
        return list(obj.accounttemplate_set.values_list('account__account_name', flat=True))

class AccountTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccountTemplate
        fields = '__all__'

class AccountTemplateConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccountTemplateConfiguration
        fields = '__all__'
