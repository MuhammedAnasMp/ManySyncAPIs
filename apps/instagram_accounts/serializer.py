from rest_framework import serializers
from .models import InstagramAccount

class InstagramAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = InstagramAccount
        fields = [
            "id","username", "full_name", "profile_pic_url", "is_verified",
            "biography", "external_url", "email", "phone_number",
            "gender", "is_business", "birthday", "added_at", "updated_at" ,"is_loggin_required"
        ]
