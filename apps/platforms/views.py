from django.db import models
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
import requests,json,redis
from rest_framework.views import APIView
from .models import PlatformAccount, DeveloperApp, DeveloperAppAccount
from .serializers import PlatformAccountSerializer, DeveloperAppSerializer, DeveloperAppAccountSerializer
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from .utils import check_if_follows
from django.db import IntegrityError



class PlatformAccountViewSet(viewsets.ModelViewSet):
    serializer_class = PlatformAccountSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return PlatformAccount.objects.none()

        # Get accounts for workspaces where the user is either the owner or a member
        queryset = PlatformAccount.objects.filter(
            models.Q(workspace__owner=user) | 
            models.Q(workspace__members__user=user),
            deleted_at__isnull=True
        ).distinct()

        workspace_id = self.request.query_params.get('workspace')
        if workspace_id:
            queryset = queryset.filter(workspace_id=workspace_id)

        return queryset

    def destroy(self, request, *args, **kwargs):
        account = self.get_object()
        
        # If it's a Facebook user (root identity), try to revoke permissions on Meta side
        if account.account_type == 'facebook_user' and account.access_token_encrypted:
            try:
                # Meta allows revoking app access via DELETE /me/permissions
                revoke_url = "https://graph.facebook.com/v21.0/me/permissions"
                requests.delete(revoke_url, params={"access_token": account.access_token_encrypted})
            except Exception as e:
                # We log but don't fail the deletion if Meta revocation fails
                print(f"Failed to revoke Meta permissions: {str(e)}")

        # Perform hierarchical soft delete
        account.soft_delete()
        
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['get'])
    def media(self, request, pk=None):
        account = self.get_object()
        after_cursor = request.query_params.get('after')
        
        try:
            if account.platform == 'instagram':
                return self._get_instagram_media(account, after_cursor)
            elif account.platform == 'youtube':
                # Placeholder for YouTube media
                return Response([], status=status.HTTP_200_OK)
            else:
                return Response({'error': f'Media fetch not implemented for {account.platform}'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _get_instagram_media(self, account, after_cursor=None):
        """
        Fetches media from Instagram Graph API.
        """
        # Note: The user provided a specific graph URL and fields
        # https://graph.instagram.com/v25.0/{ig-user-id}/media?fields=id,caption,media_type,media_url,timestamp&access_token={token}
        
        # We'll use the platform_user_id (which is the IG User ID)
        url = f"https://graph.instagram.com/v25.0/{account.platform_user_id}/media"
        params = {
            "fields": "id,caption,media_type,media_url,timestamp,thumbnail_url",
            "access_token": account.access_token_encrypted # TODO: Actual Decryption
        }
        
        if after_cursor:
            params['after'] = after_cursor
        
        try:
            res = requests.get(url, params=params)
            if res.status_code != 200:
                return Response({'error': 'Failed to fetch Instagram media', 'details': res.json()}, status=res.status_code)
            
            data = res.json()
            # Return full data (data + paging)
            return Response(data, status=status.HTTP_200_OK)
        except requests.exceptions.RequestException as e:
            return Response({'error': f'Network error: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _refresh_youtube(self, account):
        channel_url = "https://www.googleapis.com/youtube/v3/channels"
        params = {
            "part": "snippet,statistics",
            "mine": "true",
            "access_token": account.access_token_encrypted # TODO: Decrypt
        }
        res = requests.get(channel_url, params=params)
        if res.status_code != 200:
            return Response({'error': 'Failed to fetch YouTube data', 'details': res.json()}, status=status.HTTP_400_BAD_REQUEST)
        
        data = res.json()
        items = data.get('items', [])
        if not items:
            return Response({'error': 'No YouTube channel found'}, status=status.HTTP_404_NOT_FOUND)
        
        snippet = items[0].get('snippet', {})
        stats = items[0].get('statistics', {})
        
        account.display_name = snippet.get('title', account.display_name)
        account.profile_picture_url = snippet.get('thumbnails', {}).get('high', {}).get('url', account.profile_picture_url)
        account.subscribers_count = stats.get('subscriberCount', 0)
        account.total_views = stats.get('viewCount', 0)
        account.last_refreshed_at = timezone.now()
        account.save()
        
        return Response(PlatformAccountSerializer(account).data)

    def _refresh_instagram(self, account):
        """
        Refreshes Instagram account data. 
        Note: Basic Display API is deprecated. This implementation attempts to use 
        available fields and provides fallback/error handling.
        """
        url = "https://graph.instagram.com/me"
        # Attempting to fetch as much as possible from Basic Display fields
        # Note: followers_count and profile_picture_url are officially for Professional accounts (Graph API)
        params = {
            "fields": "id,username,account_type,media_count",
            "access_token": account.access_token_encrypted # TODO: Actual Decryption
        }
        
        try:
            res = requests.get(url, params=params)
            
            # If Basic Display fails (due to deprecation), we try a fallback or return error
            if res.status_code != 200:
                error_data = res.json()
                # Check if it's a token expiry issue
                if res.status_code == 401:
                    account.status = 'expired'
                    account.save()
                    return Response({'error': 'Instagram token expired', 'details': error_data}, status=status.HTTP_401_UNAUTHORIZED)
                
                return Response({
                    'error': 'Failed to fetch Instagram data', 
                    'details': error_data,
                    'message': 'Instagram Basic Display API is deprecated. Please ensure you are using a Professional/Business account.'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            data = res.json()
            
            # Update account details
            account.username = data.get('username', account.username)
            # Map media_count to total_views as a proxy for engagement in the UI
            account.total_views = data.get('media_count', account.total_views)
            
            # Note: For professional accounts, we'd use graph.facebook.com/{ig-user-id}?fields=followers_count,profile_picture_url
            # For now, we update the last_refreshed_at and save
            account.last_refreshed_at = timezone.now()
            account.save()
            
            return Response(PlatformAccountSerializer(account).data)
            
        except requests.exceptions.RequestException as e:
            return Response({'error': f'Network error: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class WhatsAppWebhookView(APIView):
    """
    Webhook endpoint for WhatsApp Cloud API.
    Handles verification (GET) and incoming events (POST).
    """
    # Webhooks must be publicly accessible
    permission_classes = [permissions.AllowAny]

    def get(self, request, *args, **kwargs):
        """
        Handles webhook verification from WhatsApp
        """
        # In production, consider moving this to settings or env variables
        verify_token = "test_webhook_verify_token"
        
        mode = request.query_params.get('hub.mode')
        token = request.query_params.get('hub.verify_token')
        challenge = request.query_params.get('hub.challenge')
        
        if mode and token:
            if mode == 'subscribe' and token == verify_token:
                print("✅ WhatsApp Webhook Verified successfully!")
                return Response(int(challenge), status=status.HTTP_200_OK)
            else:
                return Response({'error': 'Invalid verification token'}, status=status.HTTP_403_FORBIDDEN)
                
        return Response({'error': 'Missing parameters'}, status=status.HTTP_400_BAD_REQUEST)

    def post(self, request, *args, **kwargs):
        """
        Handles incoming events from WhatsApp
        Includes mTLS Client Certificate Verification.
        """
        # --- mTLS Client Certificate Verification ---
        expected_cn = "client.webhooks.fbclientcerts.com"
        
        # For AWS ALB, it forwards the subject via "X-Amzn-Mtls-Clientcert-Subject"
        mtls_subject = request.META.get('HTTP_X_AMZN_MTLS_CLIENTCERT_SUBJECT')
        
        # If you are using Nginx/Apache, you might pass it manually e.g., "X-SSL-Client-S-DN"
        if not mtls_subject:
            mtls_subject = request.META.get('HTTP_X_SSL_CLIENT_S_DN')

        if mtls_subject:
            if expected_cn not in mtls_subject:
                print(f"❌ mTLS Error: Invalid Client Certificate Subject: {mtls_subject}")
                return Response({'error': 'mTLS Verification Failed'}, status=status.HTTP_403_FORBIDDEN)
            print("✅ mTLS Client Certificate Verified Successfully!")
        else:
            # Note: In production with mTLS strictly enforced at the App-level, 
            # you might want to return 403 here if the header is completely missing.
            print("⚠️ mTLS headers missing. Skipping application-level verification.")

        body = request.data
        
        # Check if this is a WhatsApp API event
        if body.get('object'):
            # Print the entire event to the terminal
            print("\n" + "="*50)
            print("🚀 NEW WHATSAPP EVENT RECEIVED")
            print("="*50)
            print(json.dumps(body, indent=4))
            print("="*50 + "\n")
            
            return Response("EVENT_RECEIVED", status=status.HTTP_200_OK)
            
        return Response(status=status.HTTP_404_NOT_FOUND)

class DeveloperAppViewSet(viewsets.ModelViewSet):
    serializer_class = DeveloperAppSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return DeveloperApp.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

class DeveloperAppAccountViewSet(viewsets.ModelViewSet):
    serializer_class = DeveloperAppAccountSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return DeveloperAppAccount.objects.filter(developer_app__user=self.request.user)

    def create(self, request, *args, **kwargs):
        access_token = request.data.get('access_token')
        developer_app_id = request.data.get('developer_app')
        account_name = "Unknown Account"
        account_id = ""
        profile_picture_url = ""
        
        if access_token:
            try:
                # Try Instagram Graph API first
                url = "https://graph.instagram.com/me"
                params = {"fields": "id,username,user_id,profile_picture_url", "access_token": access_token}
                res = requests.get(url, params=params)
                if res.status_code == 200:
                    data = res.json()
                    account_name = data.get('username', "Unknown Account")
                    account_id = data.get('user_id', "")
                    profile_picture_url = data.get('profile_picture_url', "")
                else:
                    # Fallback to Facebook Graph API
                    url_fb = "https://graph.facebook.com/me"
                    params_fb = {"fields": "id,name,picture", "access_token": access_token}
                    res_fb = requests.get(url_fb, params_fb)
                    if res_fb.status_code == 200:
                        data_fb = res_fb.json()
                        account_name = data_fb.get('name', "Unknown Account")
                        account_id = data_fb.get('id', "")
                        if "picture" in data_fb and "data" in data_fb["picture"]:
                            profile_picture_url = data_fb["picture"]["data"].get("url", "")
            except Exception as e:
                print("Error fetching account meta details:", e)
                account_name = "Unknown Account"
                account_id = ""
                profile_picture_url = ""

        # Only proceed if both account_id and developer_app_id exist
        if account_id and developer_app_id:
            # Check if this account already exists globally 
            existing = DeveloperAppAccount.objects.select_related('developer_app__user').filter(account_id=account_id).first()

            if existing:
                existing_user = getattr(existing.developer_app, 'user', None)  # safer access
                print(request.user)
                if existing_user == request.user:
                    # Already added by the same user
                    return Response(
                        {"detail": "This account is already added to one of your apps."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                else:
                    # Already added by another user
                    return Response(
                        {"detail": "This account is already linked to another user's app."},
                        status=status.HTTP_400_BAD_REQUEST
                    )

            # Try to create a new account entry
            try:
                obj = DeveloperAppAccount.objects.create(
                    developer_app_id=developer_app_id,
                    account_id=account_id,
                    account_name=account_name,
                    profile_picture_url=profile_picture_url,
                    access_token=access_token
                )
            except IntegrityError:
                # In case of a rare race condition
                return Response(
                    {"detail": "This account already exists."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            serializer = self.get_serializer(obj)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        # Fallback if account_id or developer_app_id is missing
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(
            account_name=account_name,
            account_id=account_id,
            profile_picture_url=profile_picture_url
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)





r = redis.Redis(host='localhost', port=6379, db=0)


class InstagramWebhookView(APIView):

    # 🔐 Webhook verification (Meta setup)
    def get(self, request):
        verify_token = "test_webhook_verify_token"

        mode = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge")

        if mode == "subscribe" and token == verify_token:
            return HttpResponse(challenge, status=200)

        return HttpResponse("Verification failed", status=403)

    # 📩 Handle incoming messages
    def post(self, request):
        try:
            payload = request.data
        
            if payload.get('object'):
                print("\n" + "="*50)
                print("🚀 New instagram Webhook")
                print("="*50)
                print(json.dumps(payload, indent=4))
                print("="*50 + "\n")

            if payload.get("object") != "instagram":
                return JsonResponse({"status": "ignored"}, status=200)

            for entry in payload.get("entry", []):
                for messaging in entry.get("messaging", []):

                    sender_id = messaging.get("sender", {}).get("id")
                    message = messaging.get("message", {})
                    text = message.get("text", "").strip()

                    if not sender_id or not text:
                        continue

                    # ✅ Check if message starts with "aoea"
                    if text.lower().startswith("aoea"):
                        print(f"✅ Flag detected from {sender_id}: {text}")
                        follows = check_if_follows(sender_id, "IGAAUN0phDYERBZAGE1NHBzRXRLWEFPT0EyTEkxVktMZAndRTW1NNzRFSGZARMEN1a3ZA2bHduam93cjYzY0J2SDBiRWhXcjdmWU91LWNTMmFBR25wZA2pkUUNFNi1SWnozVmhRRnh1S21CUjlKTkNZAUndwU1pn")
                        if follows:
                            self.handle_handshake(sender_id, text)
                        else:
                            self.send_message(
                                sender_id,
                                "👉 Follow us on Instagram:\nhttps://www.instagram.com/manysync/\n\n After following, please enter the code."
                            )
                        
                    else:
                        print(f"📩 Normal message from {sender_id}: {text}")
                        

            return JsonResponse({"status": "ok"}, status=200)

        except Exception as e:
            print("Webhook error:", str(e))
            return JsonResponse({"error": "server error"}, status=500)

    # 🔑 Handshake logic
    def handle_handshake(self, psid, text):
        key = f"handshake:{text}"
        data = r.get(key)

        if not data:
            self.handle_invalid_code(psid)
            return

        data = json.loads(data)
        account_id = data.get("account_id")

        try:
            account = DeveloperAppAccount.objects.get(id=account_id)

            # 🚨 Already linked to another PSID
            if account.psid and account.psid != psid:
                account.is_flagged = True
                account.save()

                self.send_message(psid, "⚠️ This account is already linked.")
                return

            # ✅ Success
            account.psid = psid
            account.is_verified = True
            account.is_flagged = False
            account.save()

            # 🧹 delete used code
            r.delete(key)

            self.send_message(psid, "✅ Account successfully connected!")

        except DeveloperAppAccount.DoesNotExist:
            self.handle_invalid_code(psid)

    # ❌ Invalid / expired code
    def handle_invalid_code(self, psid):
        self.send_message(psid, "❌ Invalid or expired code.")

        # track failures
        fail_key = f"fail:{psid}"
        r.incr(fail_key)
        r.expire(fail_key, 600)

        attempts = int(r.get(fail_key) or 0)

        if attempts >= 3:
            account = DeveloperAppAccount.objects.filter(psid=psid).first()
            if account:
                account.is_flagged = True
                account.save()

    # 💬 Send message back
    def send_message(self, psid, text):
        import requests

        url = "https://graph.instagram.com/v25.0/me/messages"

        payload = {
            "recipient": {"id": psid},
            "message": {"text": text}
        }

        params = {
            "access_token": "IGAAUN0phDYERBZAGE1NHBzRXRLWEFPT0EyTEkxVktMZAndRTW1NNzRFSGZARMEN1a3ZA2bHduam93cjYzY0J2SDBiRWhXcjdmWU91LWNTMmFBR25wZA2pkUUNFNi1SWnozVmhRRnh1S21CUjlKTkNZAUndwU1pn"
        }

        try:
            requests.post(url, json=payload, params=params)
        except Exception as e:
            print("Send message error:", str(e))