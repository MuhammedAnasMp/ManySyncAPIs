from django.db import models
from apps.authentication.models import UserProfile
from cloudinary.uploader import destroy
from urllib.parse import urlparse


class InstagramAccount(models.Model):
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name="instagram_accounts")
    ig_user_id = models.IntegerField(blank=True, null=True ,unique=True)  
    
    username = models.CharField(max_length=255, unique=False)
    full_name = models.CharField(max_length=255, blank=True, null=True)
    profile_pic_url = models.URLField(blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    biography = models.TextField(blank=True, null=True)
    external_url = models.URLField(blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    gender = models.IntegerField(blank=True, null=True)  # Instagram returns gender as an int (1, 2, 3)
    is_business = models.BooleanField(default=False)
    birthday = models.DateField(blank=True, null=True)
    auth_data = models.JSONField()  # Stores Instagrapi's load.json content
    added_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    is_loggin_required = models.BooleanField(default=False)
    
    
    def delete(self, *args, **kwargs):
        """Delete the profile picture from Cloudinary before deleting the instance"""
        if self.profile_pic_url:
            public_id = self.get_cloudinary_public_id()
            if public_id:
                destroy(public_id)  # Delete image from Cloudinary
        super().delete(*args, **kwargs)

    def get_cloudinary_public_id(self):
        """Extract Cloudinary public ID from the stored URL"""
        if self.profile_pic_url:
            path = urlparse(self.profile_pic_url).path  # Extract the path from URL
            return path.strip("/").split("/")[-1].split(".")[0]  # Get public ID
        return None


class UploadOption(models.TextChoices):
    FULL_MOVIE = "full_movie", "Full Movie (as parts)"
    CLONE_ACCOUNT = "clone_account", "Clone an Instagram Account"
    AUTOMATED_UPLOAD = "automated_upload", "Automated Upload (tag, location, category)"
    DAILY_REUPLOAD = "daily_reupload", "Upload the Same Reel Daily"


class ScheduleType(models.TextChoices):
    TIME_BASED = "time_based", "Scheduled Time/Day"
    MANUAL = "manual", "Manual Publish"


class ReelUploadTask(models.Model):
    account = models.ForeignKey(InstagramAccount, on_delete=models.CASCADE, related_name="upload_tasks")
    upload_option = models.CharField(max_length=50, choices=UploadOption.choices)
    schedule_type = models.CharField(max_length=50, choices=ScheduleType.choices)
    scheduled_time = models.DateTimeField(blank=True, null=True)  # Only for time-based scheduling
    video_file = models.FileField(upload_to="reels/", blank=True, null=True)  # Only for file uploads
    caption = models.TextField(blank=True, null=True)  # Used in all options except cloning
    tags = models.JSONField(blank=True, null=True)  # Only for automated uploads
    location = models.CharField(max_length=255, blank=True, null=True)  # Only for automated uploads
    category = models.CharField(max_length=255, blank=True, null=True)  # Only for automated uploads
    clone_target = models.CharField(max_length=255, blank=True, null=True)  # Only for cloning an account
    split_into_parts = models.BooleanField(default=False)  # Only for full movie uploads
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=20, choices=[("pending", "Pending"), ("uploaded", "Uploaded"), ("failed", "Failed")], default="pending"
    )

    def __str__(self):
        return f"{self.account.username} - {self.upload_option} - {self.status}"