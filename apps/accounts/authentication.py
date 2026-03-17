from firebase_admin import auth
from rest_framework import exceptions

def verify_firebase_token(id_token):
    """
    Verifies a Firebase ID token and returns the decoded token.
    Raises AuthenticationFailed if verification fails.
    """
    try:
        decoded_token = auth.verify_id_token(id_token)
        return decoded_token
    except Exception as e:
        raise exceptions.AuthenticationFailed(f"Invalid Firebase token: {str(e)}")
