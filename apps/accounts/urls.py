from django.urls import path
from .views import FirebaseLoginView, UserProfileView, InstagramCallbackView, YoutubeCallbackView, FacebookLoginView
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    path('auth/firebase/', FirebaseLoginView.as_view(), name='firebase-login'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('me/', UserProfileView.as_view(), name='user-profile'),
    path('auth/instagram/callback/', InstagramCallbackView.as_view(), name='instagram-callback'),
    path('auth/facebook/login/', FacebookLoginView.as_view(), name='facebook-login'),
    path('auth/youtube/callback/', YoutubeCallbackView.as_view(), name='youtube-callback'),
]
