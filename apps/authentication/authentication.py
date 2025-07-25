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
class FirebaseAuthentication(BaseAuthentication):
    def authenticate(self, request):
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith('Bearer '):
            return None

        id_token = auth_header.split('Bearer ')[1]

        try:
            decoded_token = firebase_auth.verify_id_token(id_token)
        except Exception:
            raise AuthenticationFailed('Invalid Firebase ID token')
        
        print("decoded_token" ,decoded_token)

        uid = decoded_token.get('uid')
        
        if not uid:
            raise AuthenticationFailed('Invalid token payload')

        email= decoded_token.get('email')
        username = generate_unique_username(email)
        user, _ = User.objects.get_or_create(username=username , firebase_uid = uid , )
        return (user, None)
