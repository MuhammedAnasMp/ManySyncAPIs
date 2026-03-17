from rest_framework import serializers
from .models import ScheduledPost, ScheduledPostTarget
from apps.platforms.serializers import PlatformAccountSerializer

class ScheduledPostTargetSerializer(serializers.ModelSerializer):
    platform_account_detail = PlatformAccountSerializer(source='platform_account', read_only=True)

    class Meta:
        model = ScheduledPostTarget
        fields = [
            'id', 'scheduled_post', 'platform_account', 'platform_account_detail',
            'custom_title', 'custom_caption', 'custom_thumbnail_url',
            'status', 'error_message', 'published_at',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['status', 'error_message', 'published_at', 'created_at', 'updated_at']

class ScheduledPostSerializer(serializers.ModelSerializer):
    targets = ScheduledPostTargetSerializer(many=True, read_only=True)
    targets_data = serializers.JSONField(write_only=True, required=False)

    class Meta:
        model = ScheduledPost
        fields = [
            'id', 'workspace', 'created_by',
            'media_storage_path', 'mime_type', 'file_size',
            'upload_status', 'processing_status',
            'title', 'caption', 'thumbnail_url',
            'scheduled_for', 'status',
            'targets', 'targets_data',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_by', 'upload_status', 'processing_status', 'created_at', 'updated_at']

    def create(self, validated_data):
        targets_data = validated_data.pop('targets_data', [])
        scheduled_post = ScheduledPost.objects.create(**validated_data)
        
        for target in targets_data:
            ScheduledPostTarget.objects.create(scheduled_post=scheduled_post, **target)
            
        return scheduled_post

    def update(self, instance, validated_data):
        targets_data = validated_data.pop('targets_data', None)
        
        # Update main post
        instance = super().update(instance, validated_data)
        
        if targets_data is not None:
            # Simple approach: replace targets
            instance.targets.all().delete()
            for target in targets_data:
                ScheduledPostTarget.objects.create(scheduled_post=instance, **target)
                
        return instance
