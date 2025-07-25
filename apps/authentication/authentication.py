# apps/authentication/authentication.py

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from firebase_admin import auth as firebase_auth
from django.contrib.auth import get_user_model

User = get_user_model()

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

        uid = decoded_token.get('uid')
        if not uid:
            raise AuthenticationFailed('Invalid token payload')

        user, _ = User.objects.get_or_create(username=uid)
        return (user, None)
