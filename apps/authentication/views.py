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

class VerifyFirebaseTokenView(APIView):

    def post(self, request, *args, **kwargs):
        print(request.user)
        
        
            # uid = request.get('uid')
            # email = decoded_token.get('email')
            # photo_url = decoded_token.get('picture', '')
            # phone_number = decoded_token.get('phone_number', '')

           
            # unique_username = generate_unique_username(request.email)

            # # Get or create a Django user
            # user, created = UserProfile.objects.get_or_create(
            #     firebase_uid=request.uid,
            #     defaults={
            #         'username': unique_username,  # Use the generated unique username
            #         'email': request.email,
            #         'photo': request.photo_url,
            #         'phone_number': request.phone_number,
            #     }
            # )
        try:
    
            # Return a success response
            return JsonResponse({
                'status': 'success',
                # 'uid': request.user.uid,
                'email': request.user.email,
                'user_id': request.user.id,
                'photo': request.user.photo,
                'username': request.user.username,  # Include the username in the response
            })

        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)
        except auth.InvalidIdTokenError:
            return JsonResponse({'status': 'error', 'message': 'Invalid Firebase token'}, status=400)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

class ProtectedView(APIView):
    def post(self, request):
        return Response({'message': 'You are authenticated!', 'user': request.user.username})







GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")
@csrf_exempt
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