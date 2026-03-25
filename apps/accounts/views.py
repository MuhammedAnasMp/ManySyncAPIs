from rest_framework import status, views, response
from rest_framework_simplejwt.tokens import RefreshToken
from .authentication import verify_firebase_token
from .models import User
from apps.workspaces.models import Workspace
from apps.platforms.models import PlatformAccount
from django.shortcuts import redirect
from django.utils import timezone
from datetime import timedelta
from django.conf import settings
import requests
import json ,os 

class FirebaseLoginView(views.APIView):
    """
    View to authenticate users via Firebase ID Token.
    Returns a Django JWT (Access/Refresh).
    """
    authentication_classes = []  # No authentication needed for login endpoint
    permission_classes = []

    def post(self, request):
        id_token = request.data.get('id_token')
        if not id_token:
            return response.Response(
                {'error': 'Firebase ID token is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # 1. Verify Firebase Token
            decoded_token = verify_firebase_token(id_token)
            uid = decoded_token.get('uid')
            email = decoded_token.get('email')
            name = decoded_token.get('name', '')

            if not email:
                return response.Response(
                    {'error': 'Email not provided by Firebase'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 2. Get or Create Django User
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    'username': email,  # Use email as default username
                    'name': name,
                }
            )

            # 3. Create Default Workspace if it's a new user
            if created:
                Workspace.objects.create(
                    owner=user,
                    name="Default Workspace",
                    plan="free"
                )
                
                # Assign Free Plan
                try:
                    from apps.billing.models import Plan, Subscription
                    from django.utils import timezone
                    from datetime import timedelta
                    free_plan = Plan.objects.get(name="Free")
                    Subscription.objects.create(
                        user=user,
                        plan=free_plan,
                        is_active=True,
                        start_date=timezone.now(),
                        end_date=timezone.now() + timedelta(days=30)
                    )
                except Exception as e:
                    print("Could not assign free plan:", e)
                
                # Check for pending invitations
                from apps.workspaces.models import WorkspaceInvitation, WorkspaceMember
                pending_invitations = WorkspaceInvitation.objects.filter(email=email, status='pending')
                for invitation in pending_invitations:
                    WorkspaceMember.objects.create(
                        workspace=invitation.workspace,
                        user=user,
                        role=invitation.role
                    )
                    invitation.status = 'accepted'
                    invitation.save()

            # 4. Generate Django JWT
            refresh = RefreshToken.for_user(user)
            
            return response.Response({
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'user': {
                    'id': str(user.id),
                    'email': user.email,
                    'name': user.name,
                    'is_new': created
                }
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return response.Response(
                {'error': str(e)}, 
                status=status.HTTP_401_UNAUTHORIZED
            )

class UserProfileView(views.APIView):
    """
    View to retrieve the currently authenticated user's profile.
    Requires a valid Django JWT.
    """
    def get(self, request):
        user = request.user
        return response.Response({
            'id': str(user.id),
            'email': user.email,
            'name': user.name,
            'username': user.username,
        }, status=status.HTTP_200_OK)














REQUIRED_PERMISSIONS = [
    'instagram_business_basic',
    'instagram_business_manage_messages',
    'instagram_business_content_publish',
    'instagram_business_manage_insights',
    'instagram_business_manage_comments'
]




class InstagramCallbackView(views.APIView):
    """
    Handles Instagram OAuth callback, checks permissions, exchanges short-lived token
    for long-lived access token, and saves to PlatformAccount.
    """
    def get(self, request, workspace_id: str | None = None):
        code = request.GET.get("code")
        state = request.GET.get("state", workspace_id)

        # Default frontend redirect
        redirect_path = f"/workspaces/{state}" if state else "/workspaces"
        frontend_url = f"{os.getenv("FRONTEND_URL")}{redirect_path}"

        if not code:
            return redirect(f"{frontend_url}?error=NoCodeProvided")

        try:
            # 1. Exchange code for short-lived access token
            token_url = "https://api.instagram.com/oauth/access_token"
            payload = {
                "client_id": settings.INSTAGRAM_APP_ID,
                "client_secret": settings.INSTAGRAM_APP_SECRET,
                "grant_type": "authorization_code",
                "redirect_uri": f"https://{os.getenv("BACKEND_HOST")}/api/accounts/auth/instagram/callback/",
                "code": code
            }

            response = requests.post(token_url, data=payload)
            response.raise_for_status()
            data = response.json()

            # 2. Exchange for long-lived access token
            access_token = data.get("access_token")
            if not access_token:
                return redirect(f"{frontend_url}?error=NoAccessToken")

            exchange_url = "https://graph.instagram.com/access_token"
            params = {
                "grant_type": "ig_exchange_token",
                "client_secret": settings.INSTAGRAM_APP_SECRET,
                "access_token": access_token,
            }
            exchange_response = requests.get(exchange_url, params=params)
            exchange_data = exchange_response.json()
            long_lived_token = exchange_data.get("access_token")

            if not long_lived_token:
                return redirect(f"{frontend_url}?error=FailedExchange")

            # 3. Check Permissions
            perm_url = "https://graph.instagram.com/me/permissions"
            perm_res = requests.get(perm_url, params={"access_token": long_lived_token})
            if perm_res.status_code == 200:
                granted_perms = [p['permission'] for p in perm_res.json().get('data', []) if p['status'] == 'granted']
                missing_perms = [p for p in REQUIRED_PERMISSIONS if p not in granted_perms]
                
                if missing_perms:
                    missing_str = ", ".join(missing_perms)
                    return redirect(f"{frontend_url}?error=MissingPermissions&msg=Please grant: {missing_str}")
            else:
                # If permissions check fails, we might still proceed or fail. 
                # Given it's a new security measure, let's log and proceed or fail based on strictness.
                print(f"Permission check failed: {perm_res.text}")

            # 4. Get User Profile info
            profile_url = "https://graph.instagram.com/me"
            profile_params = {
                "fields": "id,username,name,account_type,media_count,user_id,followers_count,follows_count,profile_picture_url",
                "access_token": long_lived_token
            }
            profile_res = requests.get(profile_url, params=profile_params)
            profile_data = profile_res.json()
            print("profile_data",profile_data)
            # 4. Save to PlatformAccount
            if state:
                try:
                    workspace = Workspace.objects.get(id=state)
                    
                    # Check for existing account to handle relocation warning
                    existing_account = PlatformAccount.objects.filter(
                        platform='instagram',
                        platform_user_id=profile_data.get('user_id')
                    ).first()
                    
                    warning_msg = ""
                    if existing_account and existing_account.workspace != workspace:
                        warning_msg = f"&warning=Account relocated from workspace: {existing_account.workspace.name}"

                    PlatformAccount.objects.update_or_create(
                        platform='instagram',
                        platform_user_id=profile_data.get('user_id'),
                        defaults={
                            'workspace': workspace,
                            'username': profile_data.get('username'),
                            'display_name': profile_data.get('name', ''),
                            'followers_count': int(profile_data.get('followers_count', 0)),
                            'follows_count': int(profile_data.get('follows_count', 0)),
                            'media_count': int(profile_data.get('media_count', 0)),
                            'profile_picture_url': profile_data.get('profile_picture_url'),
                            'access_token_encrypted': long_lived_token, # TODO: actual encryption
                            'token_type': 'bearer',
                            'last_refreshed_at': timezone.now(),
                            'deleted_at': None,
                            'status': 'active'
                        }
                    )
                    return redirect(f"{frontend_url}?success=1&platform=instagram{warning_msg}")
                except Workspace.DoesNotExist:
                    return redirect(f"{frontend_url}?error=WorkspaceNotFound")

            return redirect(f"{frontend_url}?success=1&platform=instagram")

        except Exception as e:
            return redirect(f"{frontend_url}?error=TokenRequestFailed&msg={str(e)}")


class FacebookLoginView(views.APIView):
    """
    Handles Facebook Business Login token from frontend.
    Exchanges it for long-lived token, finds associated Instagram Business accounts,
    and saves them to PlatformAccount.
    """
    def post(self, request):
        access_token = request.data.get("access_token")
        workspace_id = request.data.get("workspace_id")

        if not access_token or not workspace_id:
            return response.Response(
                {"error": "Access token and workspace_id are required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            workspace = Workspace.objects.get(id=workspace_id)
        except Workspace.DoesNotExist:
            return response.Response(
                {"error": f"Workspace with id {workspace_id} not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        try:
            # 1. Exchange for long-lived token
            exchange_url = "https://graph.facebook.com/v21.0/oauth/access_token"
            params = {
                "grant_type": "fb_exchange_token",
                "client_id": settings.FACEBOOK_APP_ID,
                "client_secret": settings.FACEBOOK_APP_SECRET,
                "fb_exchange_token": access_token
            }
            exchange_res = requests.get(exchange_url, params=params)
            
            if exchange_res.status_code != 200:
                return response.Response(
                    {"error": "Failed to exchange token", "details": exchange_res.json()},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            long_lived_token = exchange_res.json().get("access_token")

       

            # 3. Fetch Facebook User ID and Name
            me_url = "https://graph.facebook.com/v21.0/me"
            me_params = {"fields": "id,name", "access_token": long_lived_token}
            me_res = requests.get(me_url, params=me_params)
            if me_res.status_code != 200:
                return response.Response(
                    {"error": "Failed to fetch Facebook user data", "details": me_res.json()},
                    status=status.HTTP_400_BAD_REQUEST
                )
            user_data = me_res.json()
            meta_user_id = user_data.get("id")
            meta_user_name = user_data.get("name")

            warnings = []

            # 3. Save/Update Facebook User Account (Root)
            fb_user_exists = PlatformAccount.objects.filter(platform='meta', platform_user_id=meta_user_id).first()
            if fb_user_exists and fb_user_exists.workspace != workspace:
                warnings.append(f"Facebook identity {meta_user_name} relocated from workspace: {fb_user_exists.workspace.name}")

            fb_user_account, _ = PlatformAccount.objects.update_or_create(
                platform='meta',
                platform_user_id=meta_user_id,
                defaults={
                    'workspace': workspace,
                    'account_type': 'facebook_user',
                    'username': meta_user_name,
                    'display_name': meta_user_name,
                    'meta_user_id': meta_user_id,
                    'access_token_encrypted': long_lived_token,
                    'token_type': 'bearer',
                    'token_expires_at': timezone.now() + timedelta(days=60),
                    'last_refreshed_at': timezone.now(),
                    'deleted_at': None,
                    'status': 'active'
                }
            )

            saved_accounts = [{
                "id": str(fb_user_account.id),
                "type": "facebook_user",
                "username": fb_user_account.username
            }]

            # 4. Fetch Pages and Instagram Accounts
            pages_url = "https://graph.facebook.com/v21.0/me/accounts"
            pages_params = {
                "fields": "instagram_business_account{id,username,name,profile_picture_url,followers_count,follows_count,media_count},access_token,name,id",
                "access_token": long_lived_token
            }
            pages_res = requests.get(pages_url, params=pages_params)
            
            if pages_res.status_code == 200:
                for page in pages_res.json().get("data", []):
                    page_id = page.get('id')
                    page_name = page.get('name')
                    page_token = page.get("access_token")
                    ig_account = page.get("instagram_business_account")

                    # Save Page as child of FB User
                    page_exists = PlatformAccount.objects.filter(platform='meta', platform_user_id=page_id).first()
                    if page_exists and page_exists.workspace != workspace:
                        warnings.append(f"Page {page_name} relocated from workspace: {page_exists.workspace.name}")

                    page_account, _ = PlatformAccount.objects.update_or_create(
                        platform='meta',
                        platform_user_id=page_id,
                        defaults={
                            'workspace': workspace,
                            'account_type': 'facebook_page',
                            'parent_account': fb_user_account,
                            'username': page_name,
                            'display_name': page_name,
                            'meta_user_id': meta_user_id,
                            'access_token_encrypted': page_token,
                            'token_type': 'bearer',
                            'token_expires_at': timezone.now() + timedelta(days=60),
                            'last_refreshed_at': timezone.now(),
                            'deleted_at': None,
                            'status': 'active'
                        }
                    )
                    saved_accounts.append({
                        "id": str(page_account.id),
                        "type": "facebook_page",
                        "username": page_account.username
                    })

                    # Save Instagram as child of Page
                    if ig_account:
                        ig_id = ig_account.get('id')
                        ig_name = ig_account.get('username')
                        ig_exists = PlatformAccount.objects.filter(platform='instagram', platform_user_id=ig_id).first()
                        if ig_exists and ig_exists.workspace != workspace:
                            warnings.append(f"Instagram @{ig_name} relocated from workspace: {ig_exists.workspace.name}")

                        ig_platform_account, _ = PlatformAccount.objects.update_or_create(
                            platform='instagram',
                            platform_user_id=ig_id,
                            defaults={
                                'workspace': workspace,
                                'account_type': 'instagram_business',
                                'parent_account': page_account,
                                'username': ig_name,
                                'display_name': ig_account.get('name', page_name),
                                'profile_picture_url': ig_account.get('profile_picture_url'),
                                'followers_count': int(ig_account.get('followers_count', 0)),
                                'follows_count': int(ig_account.get('follows_count', 0)),
                                'media_count': int(ig_account.get('media_count', 0)),
                                'external_parent_id': page_id,
                                'external_parent_name': page_name,
                                'meta_user_id': meta_user_id,
                                'access_token_encrypted': page_token,
                                'token_type': 'bearer',
                                'token_expires_at': timezone.now() + timedelta(days=60),
                                'last_refreshed_at': timezone.now(),
                                'deleted_at': None,
                                'status': 'active'
                            }
                        )
                        saved_accounts.append({
                            "id": str(ig_platform_account.id),
                            "type": "instagram_business",
                            "username": ig_platform_account.username
                        })

            # 5. Fetch WhatsApp Accounts via Business Managers
            biz_url = "https://graph.facebook.com/v21.0/me/businesses"
            biz_res = requests.get(biz_url, params={"access_token": long_lived_token})
            
            if biz_res.status_code == 200:
                for biz in biz_res.json().get("data", []):
                    biz_id = biz.get("id")
                    biz_name = biz.get("name")
                    
                    wa_url = f"https://graph.facebook.com/v21.0/{biz_id}/owned_whatsapp_business_accounts"
                    wa_res = requests.get(wa_url, params={"access_token": long_lived_token})
                    
                    if wa_res.status_code == 200:
                        for wa in wa_res.json().get("data", []):
                            wa_id = wa.get("id")
                            wa_name = wa.get("name", f"WhatsApp ({wa_id})")
                            
                            wa_exists = PlatformAccount.objects.filter(platform='meta', platform_user_id=wa_id).first()
                            if wa_exists and wa_exists.workspace != workspace:
                                warnings.append(f"WhatsApp {wa_name} relocated from workspace: {wa_exists.workspace.name}")

                            wa_platform_account, _ = PlatformAccount.objects.update_or_create(
                                platform='meta',
                                platform_user_id=wa_id,
                                defaults={
                                    'workspace': workspace,
                                    'account_type': 'whatsapp_business',
                                    'parent_account': fb_user_account,
                                    'username': wa_name,
                                    'display_name': wa_name,
                                    'meta_user_id': meta_user_id,
                                    'external_parent_id': biz_id,
                                    'external_parent_name': biz_name,
                                    'access_token_encrypted': long_lived_token,
                                    'token_type': 'bearer',
                                    'token_expires_at': timezone.now() + timedelta(days=60),
                                    'last_refreshed_at': timezone.now(),
                                    'deleted_at': None,
                                    'status': 'active'
                                }
                            )
                            saved_accounts.append({
                                "id": str(wa_platform_account.id),
                                "type": "whatsapp_business",
                                "username": wa_platform_account.username
                            })

            return response.Response({
                "success": True,
                "accounts": saved_accounts,
                "warnings": warnings if warnings else None
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return response.Response(
                {"error": f"Internal server error: {str(e)}"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class YoutubeCallbackView(views.APIView):
    """
    Handles YouTube OAuth callback and exchanges code for access & refresh tokens.
    Saves to PlatformAccount.
    """
    def get(self, request):
        code = request.GET.get("code")
        state = request.GET.get("state") # workspaceId

        # Default frontend redirect
        redirect_path = f"/workspaces/{state}" if state else "/workspaces"
        frontend_url = f"{os.getenv("FRONTEND_URL")}{redirect_path}"

        if not code:
            return redirect(f"{frontend_url}?error=NoCodeProvided")

        try:
            token_url = "https://oauth2.googleapis.com/token"
            data = {
                "code": code,
                "client_id": settings.YOUTUBE_CLIENT_ID,
                "client_secret": settings.YOUTUBE_CLIENT_SECRET,
                "redirect_uri": f"https://{os.getenv("BACKEND_HOST")}/api/accounts/auth/youtube/callback/",
                "grant_type": "authorization_code",
            }

            response = requests.post(token_url, data=data)
            response.raise_for_status()
            tokens = response.json()

            access_token = tokens.get("access_token")
            refresh_token = tokens.get("refresh_token")
            expires_in = tokens.get("expires_in")

            # Get channel info from YouTube API
            channel_url = "https://www.googleapis.com/youtube/v3/channels"
            channel_params = {
                "part": "snippet,statistics",
                "mine": "true",
                "access_token": access_token
            }
            channel_res = requests.get(channel_url, params=channel_params)
            channel_data = channel_res.json()
            
            item = channel_data.get('items', [{}])[0]
            snippet = item.get('snippet', {})
            stats = item.get('statistics', {})

            if state:
                try:
                    workspace = Workspace.objects.get(id=state)
                    
                    # Check for existing account to handle relocation warning
                    existing_account = PlatformAccount.objects.filter(
                        platform='youtube',
                        platform_user_id=item.get('id')
                    ).first()
                    
                    warning_msg = ""
                    if existing_account and existing_account.workspace != workspace:
                        warning_msg = f"&warning=YouTube channel relocated from workspace: {existing_account.workspace.name}"

                    PlatformAccount.objects.update_or_create(
                        platform='youtube',
                        platform_user_id=item.get('id'),
                        defaults={
                            'workspace': workspace,
                            'username': snippet.get('title'),
                            'display_name': snippet.get('title'),
                            'profile_picture_url': snippet.get('thumbnails', {}).get('default', {}).get('url'),
                            'access_token_encrypted': access_token,
                            'refresh_token_encrypted': refresh_token,
                            'token_type': 'Bearer',
                            'token_expires_at': timezone.now() + timedelta(seconds=expires_in) if expires_in else None,
                            'subscribers_count': int(stats.get('subscriberCount', 0)),
                            'total_views': int(stats.get('viewCount', 0)),
                            'media_count': int(stats.get('videoCount', 0)),
                            'last_refreshed_at': timezone.now(),
                            'deleted_at': None,
                            'status': 'active'
                        }
                    )
                    return redirect(f"{frontend_url}?success=1&platform=youtube{warning_msg}")
                except Workspace.DoesNotExist:
                    return redirect(f"{frontend_url}?error=WorkspaceNotFound")

            return redirect(f"{frontend_url}?success=1&platform=youtube")

        except Exception as e:
            return redirect(f"{frontend_url}?error=TokenRequestFailed&msg={str(e)}")
