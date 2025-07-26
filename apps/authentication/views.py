from django.http import HttpResponse ,JsonResponse
from django.views.decorators.csrf import csrf_exempt
from apps.authentication.models import UserProfile
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from firebase_admin import auth
from cloudinary.uploader import upload
import logging
from django.middleware.csrf import get_token
logger = logging.getLogger(__name__)
import os
import subprocess
from django.http import JsonResponse, HttpResponseForbidden
from django.conf import settings
import hmac
import hashlib
from .authentication import FirebaseAuthentication
import json

def index(request):
    return HttpResponse("Hello, world! Welcome to the Blog app.")

def generate_unique_username(email):
    """
    Generate a unique username based on the email address.
    If the username already exists, append a number to make it unique.
    """
    base_username = email.split('@')[0]  # Use the part before the '@' in the email
    username = base_username
    counter = 1

    # Check if the username already exists
    while UserProfile.objects.filter(username=username).exists():
        username = f"{base_username}_{counter}"
        counter += 1

    return username
from datetime import timedelta
from django.utils import timezone
from .models import CustomSession

DEBUG = os.getenv("DEBUG", "").lower() in ["true", "1"]
class VerifyFirebaseTokenView(APIView):
    def post(self, request, *args, **kwargs):
        try:
            user = request.user  # Ensure this is populated from your Firebase middleware

            # Create custom session
            expires = timezone.now() + timedelta(days=7)  # 7-day session
            custom_session = CustomSession.objects.create(user=user, expires_at=expires)

            response = JsonResponse({
                'status': 'success',
                'message': 'Session created',
                'user_id': user.id,
                'username': user.username,
                'email': user.email,
            })

            response.set_cookie(
            key='custom_session_token',
            value=str(custom_session.session_token),
            max_age=7 * 24 * 60 * 60,  # 7 days
            httponly=True,
            samesite='Lax' if DEBUG else 'None',
            secure=not DEBUG 
        )
            
            print('same site','Lax' if DEBUG else 'None')
            print("secure",not DEBUG )

            return response

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
class ProtectedView(APIView):
    def post(self, request):
        return Response({'message': 'You are authenticated!', 'user': request.user.username})

from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.utils.timezone import now

@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def logout_view(request):
    response = Response({"message": "Logged out"})

    # Expire the cookie by setting it in the past
    response.set_cookie(
        key='custom_session_token',
        value='',
        expires=now() - timedelta(days=1),  # past date to expire
        httponly=True,
        samesite='Lax' if settings.DEBUG else 'None',
        secure=not settings.DEBUG
    )

    return response


GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")
@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny]) 
def git_pull(request):
    if request.method == "POST":
        # Step 1: Verify the GitHub webhook secret
        header_signature = request.META.get('HTTP_X_HUB_SIGNATURE_256')
        if header_signature is None:
            logger.warning("Missing X-Hub-Signature-256 header")
            return HttpResponseForbidden("Permission denied")

        # Compute the HMAC signature
        signature = hmac.new(
            GITHUB_WEBHOOK_SECRET.encode(),
            request.body,
            hashlib.sha256
        ).hexdigest()
        expected_signature = f"sha256={signature}"

        # Compare the signatures securely
        if not hmac.compare_digest(header_signature, expected_signature):
            logger.warning("Invalid webhook signature")
            return HttpResponseForbidden("Invalid signature")

        # Step 2: Perform git pull and migrations
        try:
            repo_path = settings.BASE_DIR

            # Pull changes
            pull_output = subprocess.check_output(['git', 'pull'], cwd=repo_path, text=True)
            logger.info(pull_output)

            # Make migrations
            makemigrations_output = subprocess.check_output(
                ['python', 'manage.py', 'makemigrations'], cwd=repo_path, text=True
            )
            logger.info(makemigrations_output)

            # Migrate
            migrate_output = subprocess.check_output(
                ['python', 'manage.py', 'migrate'], cwd=repo_path, text=True
            )
            logger.info(migrate_output)

            return JsonResponse({"status": "success"})
        except subprocess.CalledProcessError as e:
            logger.error(f"Error during update: {e.output}")
            return JsonResponse({"status": "failed", "error": e.output})
    return JsonResponse({"status": "invalid method"})