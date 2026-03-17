from rest_framework import serializers
from .models import PlatformAccount

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
