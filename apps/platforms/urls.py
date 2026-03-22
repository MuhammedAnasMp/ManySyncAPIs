from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PlatformAccountViewSet, WhatsAppWebhookView

router = DefaultRouter()
router.register(r'accounts', PlatformAccountViewSet, basename='platform-account')

urlpatterns = [
    path('webhook/whatsapp', WhatsAppWebhookView.as_view(), name='whatsapp-webhook-noslash'),
    path('webhook/whatsapp/', WhatsAppWebhookView.as_view(), name='whatsapp-webhook'),
    path('', include(router.urls)),
]
