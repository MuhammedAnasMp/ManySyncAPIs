from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PlatformAccountViewSet

router = DefaultRouter()
router.register(r'accounts', PlatformAccountViewSet, basename='platform-account')

urlpatterns = [
    path('', include(router.urls)),
]
