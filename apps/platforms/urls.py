from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PlatformAccountViewSet, WhatsAppWebhookView, DeveloperAppViewSet, DeveloperAppAccountViewSet

router = DefaultRouter()
router.register(r'accounts', PlatformAccountViewSet, basename='platform-account')
router.register(r'developer-apps', DeveloperAppViewSet, basename='developer-apps')
router.register(r'developer-app-accounts', DeveloperAppAccountViewSet, basename='developer-app-accounts')

urlpatterns = [
    path('webhook/whatsapp', WhatsAppWebhookView.as_view(), name='whatsapp-webhook-noslash'),
    path('webhook/whatsapp/', WhatsAppWebhookView.as_view(), name='whatsapp-webhook'),
    path('', include(router.urls)),
]
