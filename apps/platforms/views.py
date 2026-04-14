from django.db import models
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
import requests,json,redis
from rest_framework.views import APIView
from .models import PlatformAccount, DeveloperAppAccount
from .serializers import PlatformAccountSerializer, DeveloperAppAccountSerializer
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from .utils import check_if_follows
from django.db import IntegrityError
from django.core.cache import cache
import time
from datetime import datetime
from .utils import upload_reel
from django.db.models import Q
import requests

from threading import Thread
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

    def _refresh_instagram(self,  account):
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



class DeveloperAppAccountViewSet(viewsets.ModelViewSet):
    serializer_class = DeveloperAppAccountSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return DeveloperAppAccount.objects.filter(user=self.request.user)

    @action(detail=True, methods=['post'])
    def generate_handshake(self, request, pk=None):
        import uuid
        import json
        account = self.get_object()
        
        # Verify the user owns this account
        is_owner = (account.user == request.user)
        if not is_owner:
            return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)
            
        # Generate a short unique code starting with aoea
        code = f"aoea{str(uuid.uuid4())[:8].replace('-', '')}"
        
        # Save to cache with a 10 min TTL
        key = f"handshake:{code}"
        data = {"account_id": account.pk}
        cache.set(key, json.dumps(data), timeout=600)
        
        return Response({"code": code}, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        from apps.billing.utils import get_quota
        account_quota = get_quota(request.user, "account_count")
        active_accounts_used = DeveloperAppAccount.objects.filter(user=request.user, is_active=True).count()
        # We allow creating accounts even if at limit, but they will be inactive
        # unless specifically allowed. But for now, let's keep the block for new connections
        # if the total accounts (regardless of active status) exceeds some large buffer,
        # or just allow it and set is_active based on quota.
        
        # Recommendation: Set is_active=True only if active_accounts_used < account_quota
        is_active_initial = active_accounts_used < account_quota

        access_token = request.data.get('access_token')
        account_name = "Unknown Account"
        account_id = ""
        profile_picture_url = ""
        followers_count = 0
        follows_count = 0
        media_count = 0
        
        if access_token:
            try:
                # Try Instagram Graph API first
                url = "https://graph.instagram.com/me"
                params = {"fields": "id,username,user_id,profile_picture_url,followers_count,follows_count,media_count", "access_token": access_token}
                res = requests.get(url, params=params)
                if res.status_code == 200:
                    data = res.json()
                    account_name = data.get('username', "Unknown Account")
                    account_id = data.get('user_id', "")
                    profile_picture_url = data.get('profile_picture_url', "")
                    followers_count = data.get('followers_count', 0)
                    follows_count = data.get('follows_count', 0)
                    media_count = data.get('media_count', 0)
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
                followers_count = 0
                follows_count = 0
                media_count = 0

        # Only proceed if account_id exists
        if account_id:
            # Check if this account already exists globally 
            existing = DeveloperAppAccount.objects.filter(account_id=account_id).first()

            if existing:
                existing_user = existing.user
                if existing_user == request.user:
                    # Already added by the same user
                    return Response(
                        {"detail": "This account is already added to one of your apps."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                else:
                    # Already added by another user
                    return Response(
                        {"detail": "This account is already linked  "},
                        status=status.HTTP_400_BAD_REQUEST
                    )

            # Try to create a new account entry
            try:
                obj = DeveloperAppAccount.objects.create(
                    user=request.user,
                    account_id=account_id,
                    account_name=account_name,
                    profile_picture_url=profile_picture_url,
                    access_token=access_token,
                    followers_count=followers_count,
                    follows_count=follows_count,
                    media_count=media_count,
                    is_active=is_active_initial
                )
            except IntegrityError:
                # In case of a rare race condition
                return Response(
                    {"detail": "This account already exists."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            serializer = self.get_serializer(obj)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        from apps.billing.utils import get_quota
        from rest_framework.exceptions import PermissionDenied
        
        is_active = self.request.data.get('is_active')
        if is_active is True and not serializer.instance.is_active:
            # User is trying to activate an account
            quota = get_quota(self.request.user, "account_count")
            active_count = DeveloperAppAccount.objects.filter(user=self.request.user, is_active=True).count()
            if active_count >= quota:
                raise PermissionDenied("Plan account limit reached. Deactivate another account first.")
        
        serializer.save()




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

                    if not sender_id or not message:
                        continue

                    # 🔹 1. Handle TEXT messages
                    code = message.get("text", "").strip()

                    if code:
                        if code.lower().startswith("aoea"):
                            print(f"✅ Flag detected from {sender_id}: {code}")
                            username, follows = check_if_follows(sender_id)

                            if follows:
                                self.handle_handshake(sender_id, code, username)
                            else:
                                self.send_message(
                                    sender_id,
                                    "👉 Follow us on Instagram:\nhttps://www.instagram.com/manysync/\n\n After following, please enter the code."
                                )
                        else:
                            print(f"📩 Normal text message {sender_id}: {code}")

                    # 🔹 2. Handle ATTACHMENTS (Reels, media, etc.)
                    attachments = message.get("attachments", [])

                    for attachment in attachments:
                        att_type = attachment.get("type")

                        # 🎬 Handle Instagram Reel
                        if   att_type == "ig_reel":

                            # sample instagram webhook payload
                            # {
                            #     "object": "instagram",
                            #     "entry": [
                            #         {
                            #             "time": 1775748900067,
                            #             "id": "17841441535053704",
                            #             "messaging": [
                            #                 {
                            #                     "sender": {
                            #                         "id": "943608128068235"
                            #                     },
                            #                     "recipient": {
                            #                         "id": "17841441535053704"
                            #                     },
                            #                     "timestamp": 1775748899372,
                            #                     "message": {
                            #                         "mid": "aWdfZAG1faXRlbToxOklHTWVzc2FnZAUlEOjE3ODQxNDQxNTM1MDUzNzA0OjM0MDI4MjM2Njg0MTcxMDMwMTI0NDI3NjI2MTYwMjE4NzI4MjYxNTozMjc1Njc4NTQ4NTg5Njg2NDA3OTMwMDIzNzk0ODA5MjQxNgZDZD",
                            #                         "attachments": [
                            #                             {
                            #                                 "type": "ig_reel",
                            #                                 "payload": {
                            #                                     "reel_video_id": "18087782618022081",
                            #                                     "title": "\u201c\u0d35\u0d34\u0d3f \u0d24\u0d1f\u0d1e\u0d4d\u0d1e\u0d3e\u0d7d\u2026 \u0d28\u0d2e\u0d4d\u0d2e\u0d7e \u0d35\u0d34\u0d3f\u0d2f\u0d41\u0d23\u0d4d\u0d1f\u0d3e\u0d15\u0d4d\u0d15\u0d41\u0d02 \u201c \ud83d\udea7\u27a1\ufe0f\ud83d\udca5\n\nNO TOLL \u274c\u270a\ud83c\udffb\n.\n.\n.\n#notoll #kozhikode #time #justice #respond #react #justiceforall #reels #trending #reelsinstagram #fyp #highways",        
                            #                                     "url": "https://lookaside.fbsbx.com/ig_messaging_cdn/?asset_id=18087782618022081&signature=Ab0jZotmhcjby9PwASLnVpN7GD5JFZQWoCJbrVIuScz3hpNvkiJTz9cGrRcZbTwKZnf3iR-KJ99LGg3GU_UuLF-Ammju9fsUdewmBElsLa0ezt_gP5TKSuVKxM593kpahBU3q593DPBf8cFTNmblrcUyz0YnXR6r8OSUUWJD3aNujRmvHNrhHa32BZXwgHYRGvQ1-yXmy-9idzboVAD9qAA1DByvGKFr"
                            #                                 }
                            #                             }
                            #                         ]
                            #                     }
                            #                 }
                            #             ]
                            #         }
                            #     ]
                            # }

                            
                            reel_payload = attachment.get("payload", {})
                            reel_id = reel_payload.get("reel_video_id")
                            reel_title = reel_payload.get("title")
                            reel_url = reel_payload.get("url")

                            print(f"🎬 Reel received from {sender_id}")
                            print(f"   Reel ID: {reel_id}")
                            print(f"   Title: {reel_title}")
                            print(f"   URL: {reel_url}")

                            try:
                                account = DeveloperAppAccount.objects.get(psid=sender_id)
                                
                                # Fetch template
                                account_template = AccountTemplate.objects.filter(
                                    account=account, 
                                    template_type='reel'
                                ).select_related('template').first()
                                
                                template_json = None
                                if account_template and account_template.template:
                                    template_json = account_template.template.template_json
                                
                                # Fetch configuration
                                config_obj = AccountTemplateConfiguration.objects.filter(
                                    account=account, 
                                    template_type='reel'
                                ).first()
                                
                                configuration = config_obj.configuration if config_obj else {}

                                # Start processing in background
                                Thread(target=upload_reel, args=(
                                    reel_url, 
                                    reel_title, 
                                    account.access_token, 
                                    account.account_id,
                                    template_json,
                                    configuration
                                )).start()

                            except DeveloperAppAccount.DoesNotExist:
                                print(f"⚠️ Account not found for PSID: {sender_id}")
                        elif att_type == "ig_post":
                            post_payload = attachment.get("payload", {})
                            image_url = post_payload.get("url")
                            post_title = post_payload.get("title")

                            print(f"📸 Image Post received from {sender_id}")
                            print(f"   URL: {image_url}")
                            print(f"   Title: {post_title}")

                            try:
                                account = DeveloperAppAccount.objects.get(psid=sender_id)
                                
                                # Fetch template
                                account_template = AccountTemplate.objects.filter(
                                    account=account, 
                                    template_type='image'
                                ).select_related('template').first()
                                
                                template_json = None
                                if account_template and account_template.template:
                                    template_json = account_template.template.template_json
                                
                                # Fetch configuration
                                config_obj = AccountTemplateConfiguration.objects.filter(
                                    account=account, 
                                    template_type='image'
                                ).first()
                                
                                configuration = config_obj.configuration if config_obj else {}

                                # Start processing in background
                                from .utils import upload_post
                                Thread(target=upload_post, args=(
                                    image_url, 
                                    post_title, 
                                    account.access_token, 
                                    account.account_id,
                                    template_json,
                                    configuration
                                )).start()

                            except DeveloperAppAccount.DoesNotExist:
                                print(f"⚠️ Account not found for PSID: {sender_id}")
                        

                        # (Optional) Handle other attachment types
                        else:
                            print(f"📎 Other attachment type: {att_type}")

            return JsonResponse({"status": "ok"}, status=200)

        except Exception as e:
            print("Webhook error:", str(e))
            return JsonResponse({"error": "server error"}, status=500)

        # 🔑 Handshake logic
    def handle_handshake(self, psid, code, account_name):
        print(f"account_name {account_name} and psid {psid} and code {code}")
        key = f"handshake:{code}"
        data = cache.get(key)
        if not data:
            self.handle_invalid_code(psid)
            return

        data = json.loads(data)
        account_id = data.get("account_id")
        try:
            account = DeveloperAppAccount.objects.get(id=account_id)
            print("account", account.psid)
            print("account.psid", account.psid)
            print("token owner", account.account_name)
            print("unknown user", account_name)
            if account.psid and account.account_name == account_name:
                account.is_flagged = True
                account.save()
                self.send_message(psid, "⚠️ This account is already linked.")
                return
            elif  account.account_name != account_name :
                account.is_flagged = True
                account.save()
                self.handle_invalid_code(psid, "⚠️ This token is not for this account. Only @" + account.account_name + " can use this token.")  
                # self.send_message(psid, "⚠️ This token is not for this account. Only @" + account.account_name + " can use this token.")

                return

            # ✅ Success
            account.psid = psid
            account.is_verified = True
            account.is_flagged = False
            account.save()

            # 🧹 delete used code

            cache.delete(key)

            self.send_message(psid, "✅ Account connected!")

        except DeveloperAppAccount.DoesNotExist:
            print("Account does not exist")
            self.handle_invalid_code(psid)

    # ❌ Invalid / expired code
    def handle_invalid_code(self, psid, message=None):

        block_key = f"blocked:{psid}"
        fail_key = f"fail:{psid}"
        
        if cache.get(block_key):
            print("Blocked Key >>>>>>>>>>>>>>>>>>>>>>>", block_key)
            print("Fail Key >>>>>>>>>>>>>>>>>>>>>>>", fail_key)
            # print the time 
            print("next try after time : ", datetime.fromtimestamp(time.time() + cache.ttl(block_key)))# show time 
            return

        # ❌ Invalid attempt
        try:
            attempts = cache.incr(fail_key)
        except ValueError:
            cache.set(fail_key, 1, timeout=600*6)  # 1 hour window
            attempts = 1

        print("Attempts:", attempts)

        # 🚫 If reached limit → block + send message ONCE
        if attempts >= 2:
            print("Account flagged & blocked >>>>>>>>>>>>>>>>>>>>>>>")

            # Set block for 1 hour
            cache.set(block_key, True, timeout=3600)

            # Reset counter
            cache.delete(fail_key)

            # Flag in DB
            account = DeveloperAppAccount.objects.filter(psid=psid).first()
            if account and not account.is_flagged:
                account.is_flagged = True
                account.save()

            # ✅ Send block message ONLY here
            self.send_message(psid, "🚫 Too many failed attempts. You are blocked for 1 hour.")
            return

        # ❌ Only send invalid message if NOT blocked yet
        if message:
            self.send_message(psid, message)
        else:
            self.send_message(psid, "❌ Invalid or expired code.")

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

from rest_framework import viewsets
from .models import Template, AccountTemplate, AccountTemplateConfiguration
from .serializers import TemplateSerializer, AccountTemplateSerializer, AccountTemplateConfigurationSerializer

class TemplateViewSet(viewsets.ModelViewSet):
    serializer_class = TemplateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        from apps.billing.utils import get_quota
        from rest_framework.exceptions import PermissionDenied
        template_quota = get_quota(self.request.user, "template_count")
        templates_used = Template.objects.filter(created_by=self.request.user).count()
        if templates_used >= template_quota:
            raise PermissionDenied("You have reached the maximum number of templates allowed on your current plan.")
            
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        user = self.request.user
        qs = Template.objects.all()

        market_place = self.request.query_params.get('market_place')
        my_template = self.request.query_params.get('my_template')

        if market_place == 'true':
            qs = qs.filter(is_public=True)
        elif my_template == 'true':
            qs = qs.filter(created_by=user)
        else:
            qs = qs.filter(models.Q(is_public=True) | models.Q(created_by=user))
            
        return qs

class AccountTemplateViewSet(viewsets.ModelViewSet):
    serializer_class = AccountTemplateSerializer
    def get_queryset(self):
        qs = AccountTemplate.objects.all()
        account = self.request.query_params.get('account')
        if account:
            qs = qs.filter(account_id=account)
        return qs

class AccountTemplateConfigurationViewSet(viewsets.ModelViewSet):
    serializer_class = AccountTemplateConfigurationSerializer
    def get_queryset(self):
        qs = AccountTemplateConfiguration.objects.all()
        account = self.request.query_params.get('account')
        if account:
            qs = qs.filter(account_id=account)
        return qs
