from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ScheduledPostViewSet, ScheduledPostTargetViewSet

router = DefaultRouter()
router.register(r'posts', ScheduledPostViewSet, basename='scheduled-post')
router.register(r'targets', ScheduledPostTargetViewSet, basename='scheduled-target')

urlpatterns = [
    path('', include(router.urls)),
]
