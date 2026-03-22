from django.db import models
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
import requests
import json
from rest_framework.views import APIView
from .models import PlatformAccount
from .serializers import PlatformAccountSerializer

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
