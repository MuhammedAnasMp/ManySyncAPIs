from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PlatformAccountViewSet, WhatsAppWebhookView, DeveloperAppAccountViewSet, InstagramWebhookView, TemplateViewSet, AccountTemplateViewSet, AccountTemplateConfigurationViewSet, NotificationViewSet

router = DefaultRouter()
router.register(r'accounts', PlatformAccountViewSet, basename='platform-account')
router.register(r'developer-app-accounts', DeveloperAppAccountViewSet, basename='developer-app-accounts')
router.register(r'templates', TemplateViewSet, basename='templates')
router.register(r'account-templates', AccountTemplateViewSet, basename='account-templates')
router.register(r'account-template-configs', AccountTemplateConfigurationViewSet, basename='account-template-configs')
router.register(r'notifications', NotificationViewSet, basename='notifications')

urlpatterns = [
    path('webhook/whatsapp', WhatsAppWebhookView.as_view(), name='whatsapp-webhook-noslash'),
    path('webhook/whatsapp/', WhatsAppWebhookView.as_view(), name='whatsapp-webhook'),


    path('webhook/instagram', InstagramWebhookView.as_view(), name='instagram-webhook-noslash'),
    path('', include(router.urls)),
]
