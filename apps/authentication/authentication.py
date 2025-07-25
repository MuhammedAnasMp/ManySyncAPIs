# apps/authentication/authentication.py

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from firebase_admin import auth as firebase_auth
from django.contrib.auth import get_user_model
from apps.authentication.models import UserProfile
User = get_user_model()
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
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from django.utils import timezone
from firebase_admin import auth as firebase_auth
from .models import *  
import uuid

class FirebaseAuthentication(BaseAuthentication):
    def authenticate(self, request):
        session_token = request.COOKIES.get('custom_session_token')
        if session_token:
            try:
                session = CustomSession.objects.get(session_token=session_token)
                if session.expires_at >= timezone.now() and session.is_valid():
                    print("Authenticated via session token")
                    return (session.user, None)
            except CustomSession.DoesNotExist:
                print("Session not found")
            except Exception as e:
                print("Invalid session:", str(e))

        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith('Bearer '):
            return None

        id_token = auth_header.split('Bearer ')[1]
        try:
            decoded_token = firebase_auth.verify_id_token(id_token)
        except Exception:
            raise AuthenticationFailed('Invalid Firebase ID token')

        uid = decoded_token.get('uid')
        email = decoded_token.get('email')

        if not uid or not email:
            raise AuthenticationFailed('Invalid token payload')

        print("Authenticated via Firebase")
        username = generate_unique_username(email)
        user, _ = User.objects.get_or_create(firebase_uid=uid)
        user.username = username
        user.save()

        expires = timezone.now() + timezone.timedelta(days=7)
        existing_session = CustomSession.objects.filter(user=user, expires_at__gt=timezone.now()).first()
        if not existing_session:
            CustomSession.objects.create(user=user, expires_at=expires)
            print("New session created")
        else:
            print("Existing valid session reused")

        return (user, None)
