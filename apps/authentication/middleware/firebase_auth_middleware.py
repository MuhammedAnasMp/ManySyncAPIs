# yourapp/middleware/firebase_auth_middleware.py

import firebase_admin
from firebase_admin import auth as firebase_auth
from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin

User = get_user_model()


class FirebaseAuthMiddleware(MiddlewareMixin):
    def process_request(self, request):
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')

        print(auth_header)

        if not auth_header.startswith('Bearer '):
            return JsonResponse({'detail': 'Authentication credentials were not provided.'}, status=401)

        id_token = auth_header[len('Bearer '):].strip()

        try:
            decoded_token = firebase_auth.verify_id_token(id_token)
            print(decoded_token)
        except Exception as e:
            return JsonResponse({'detail': 'Invalid Firebase ID token.'}, status=401)

        uid = decoded_token.get('uid')
        if not uid:
            return JsonResponse({'detail': 'Invalid token payload.'}, status=401)

        # Get or create user
        user, created = User.objects.get_or_create(username=uid)
        
        # Optionally sync user info from decoded_token, e.g. email, name
        # user.email = decoded_token.get('email', '')
        # user.save()

        request.user = user
