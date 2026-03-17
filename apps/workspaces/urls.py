from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import WorkspaceListCreateView, WorkspaceDetailView, WorkspaceMemberViewSet, WorkspaceInvitationViewSet

router = DefaultRouter()
router.register(r'members', WorkspaceMemberViewSet, basename='workspace-member')
router.register(r'invitations', WorkspaceInvitationViewSet, basename='workspace-invitation')

urlpatterns = [
    path('', WorkspaceListCreateView.as_view(), name='workspace-list-create'),
    path('<uuid:pk>/', WorkspaceDetailView.as_view(), name='workspace-detail'),
    path('', include(router.urls)),
]
