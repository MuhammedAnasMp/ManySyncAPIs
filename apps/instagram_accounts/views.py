import json
from celery import shared_task
from datetime import datetime
from cloudinary.uploader import upload
from django.db import IntegrityError
from django.http import JsonResponse
from .models import ReelUploadTask
from instagrapi import Client  # or your choice of library
from rest_framework.views import APIView
from rest_framework import status
from apps.authentication.authentication import FirebaseAuthentication
from instagrapi.exceptions import UnknownError, PleaseWaitFewMinutes, BadCredentials, ChallengeRequired
from instagrapi import Client
cl=Client()
@shared_task
def upload_reel_task(reel_upload_id):
    reel_upload = ReelUploadTask.objects.get(id=reel_upload_id)
    
    # Logic for uploading the reel (using Instagrapi or your method)
    client = Client()
    client.login(reel_upload.account.username, reel_upload.account.password)  # Use proper login

    # Handle uploading video from URL
    video_url = reel_upload.video_url
    # Add logic to fetch and upload video from URL, including caption, language, etc.

    # Update task status
    reel_upload.status = 'uploaded'
    reel_upload.save()



from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from django.http import JsonResponse
import json
from instagrapi import Client
from instagrapi.exceptions import (
    UnknownError, PleaseWaitFewMinutes, BadCredentials, ChallengeRequired
)
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from .models import InstagramAccount, UserProfile
from .serializer import InstagramAccountSerializer
from rest_framework.generics import ListAPIView
class UserInstagramAccountsView(ListAPIView):
    serializer_class = InstagramAccountSerializer
    authentication_classes = [FirebaseAuthentication]

    def get_queryset(self):
        return InstagramAccount.objects.filter(user=self.request.user)
class IgLoginClassView(APIView):
    authentication_classes = [FirebaseAuthentication]

    def post(self, request):
        try:
            body = json.loads(request.body.decode("utf-8"))
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON format"}, status=400)

        username = body.get("username")
        password = body.get("password")
        verification_code = body.get("verification_code")  # Added for step 2

        if not username or not password:
            return JsonResponse({"error": "Username and password are required"}, status=400)

        user = request.user
        if not isinstance(user, UserProfile):
            return JsonResponse({"error": "User authentication failed"}, status=401)

        cl = Client()

        try:
            cl.login(username, password)
            user_info = cl.account_info()
            session_data = cl.get_settings()
            cloudinary_response = upload(str(user_info.profile_pic_url))
            cloudinary_url = cloudinary_response.get("secure_url")

            instagram_account, created = InstagramAccount.objects.update_or_create(
                user=user,
                ig_user_id=user_info.pk,
                defaults={
                    "username":user_info.username,
                    "full_name": user_info.full_name,
                    "profile_pic_url": cloudinary_url,
                    "is_verified": user_info.is_verified,
                    "biography": user_info.biography,
                    "external_url": user_info.external_url,
                    "email": user_info.email,
                    "phone_number": user_info.phone_number,
                    "gender": user_info.gender,
                    "is_business": user_info.is_business,
                    "birthday": user_info.birthday,
                    "auth_data": session_data,
                },
            )

            return JsonResponse(
                {
                    "message": "Login successful",
                    "username": user_info.username,
                    "full_name": user_info.full_name,
                    "profile_pic_url": str(user_info.profile_pic_url),
                    "account_status": "Created" if created else "Updated",
                },
                status=200,
            )

        except ChallengeRequired:
            # Request a security code (this is triggered if IG detects suspicious login)
            challenge_info = cl.challenge_resolve()

            if challenge_info.get("step_name") in ["select_method", "close"]:
                return JsonResponse(
                    {"error": "Verification required. Check Instagram for verification."}, status=403
                )

            # If a verification code is needed, send response to the frontend
            return JsonResponse(
                {
                    "error": "Verification required",
                    "verification_type": challenge_info.get("step_name"),
                    "message": "Please enter the 6-digit code sent to your email/SMS.",
                    "username": username,  # Send username so frontend can resend code if needed
                },
                status=403,
            )

        except BadCredentials:
            return JsonResponse({"error": "Invalid username or password"}, status=401)
        except PleaseWaitFewMinutes:
            return JsonResponse(
                {"error": "Please wait a few minutes before trying again"}, status=429
            )
        except UnknownError:
            return JsonResponse(
                {"error": f"We can't find an account with {username}"}, status=400 
            )
        except IntegrityError:
            return JsonResponse({"error": f"The Instagram account '{username}' is already linked to another user. You cannot add it to IGgram."}, status=400)

        except Exception as e:
            print(e)
            return JsonResponse({"error": f"Invalid password. Varify you're password and try again later"}, status=500)
        
    def delete(self, request, *args, **kwargs):
        """Delete an Instagram account and its Cloudinary profile picture"""
        account_id = kwargs.get("pk")  # Get the account ID from URL
        
        instagram_account = get_object_or_404(InstagramAccount, id=account_id, user=request.user)


  
        instagram_account.delete()  # Delete the account instance
        
        return Response({"message": "Account removed successfully"}, status=status.HTTP_200_OK)
        
class IgVerifyLoginView(APIView):
    authentication_classes = [FirebaseAuthentication]

    def post(self, request):
        try:
            body = json.loads(request.body.decode("utf-8"))
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON format"}, status=400)

        username = body.get("username")
        verification_code = body.get("verification_code")

        if not username or not verification_code:
            return JsonResponse({"error": "Username and verification code are required"}, status=400)

        user = request.user
        if not isinstance(user, UserProfile):
            return JsonResponse({"error": "User authentication failed"}, status=401)

        cl = Client()
        
        try:
            # Submit the verification code to Instagram
            cl.challenge_code_submit(verification_code)
            user_info = cl.account_info()
            session_data = cl.get_settings()

            instagram_account, created = InstagramAccount.objects.update_or_create(
                user=user,
                username=user_info.username,
                defaults={
                    "full_name": user_info.full_name,
                    "profile_pic_url": str(user_info.profile_pic_url),
                    "is_verified": user_info.is_verified,
                    "biography": user_info.biography,
                    "external_url": user_info.external_url,
                    "email": user_info.email,
                    "phone_number": user_info.phone_number,
                    "gender": user_info.gender,
                    "is_business": user_info.is_business,
                    "birthday": user_info.birthday,
                    "auth_data": session_data,
                },
            )

            return JsonResponse(
                {
                    "message": "Verification successful, login complete",
                    "username": user_info.username,
                    "full_name": user_info.full_name,
                    "profile_pic_url": str(user_info.profile_pic_url),
                    "account_status": "Created" if created else "Updated",
                },
                status=200,
            )

        except Exception as e:
            return JsonResponse({"error": f"Verification failed: {str(e)}"}, status=500)






from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from instagrapi import Client
from .models import InstagramAccount
from instagrapi.exceptions import ClientNotFoundError, UserNotFound
def get_instagram_stats(request, igAccountId):
    """
    Fetch Instagram stats for the given igAccountId.
    """
    # Get the Instagram account from the database
    instagram_account = get_object_or_404(InstagramAccount, id=igAccountId)

    # Initialize Instagrapi Client
    client = Client()

    print("str(instagram_account.ig_user_id):", str(instagram_account.ig_user_id))

    # Ensure ig_user_id is valid
    if not instagram_account.ig_user_id:
        return JsonResponse({"error": "Instagram user ID not found"}, status=400)

    # Load session from auth_data (stored as JSONField)
    client.set_settings(instagram_account.auth_data)

    # Attempt to login
    try:
        user_info = client.account_info()
        print(f"Logged in as: {user_info.username}")
    except Exception as e:
        print("Login verification failed:", e)
        instagram_account.is_loggin_required = True
        instagram_account.save()
        return JsonResponse({"error": "Login required"}, status=401)

    # Fetch user info safely
    try:
        user_info = client.user_info_v1(str(instagram_account.ig_user_id))
        
        if not user_info:
            return JsonResponse({"error": "User info not found"}, status=404)

        # Prepare the response data
        data = {
            "username": user_info.username,
            "profile_pic_url": str(user_info.profile_pic_url_hd),  # High-resolution profile pic
            "followers_count": user_info.follower_count,
            "following_count": user_info.following_count,
            "total_posts": user_info.media_count,
            "biography": user_info.biography,
            "is_verified": user_info.is_verified,
            "is_private": user_info.is_private,
            "external_url": user_info.external_url,  # Website if available
        }

        return JsonResponse(data, safe=False)

    except UserNotFound:
        return JsonResponse({"error": "User not found or private account"}, status=404)

    except ClientNotFoundError as e:
        return JsonResponse({"error": "Invalid user or API request failed"}, status=400)

    except Exception as e:
        print("Unexpected error fetching Instagram stats:", e)
        return JsonResponse({"error": "An unexpected error occurred"}, status=500)
