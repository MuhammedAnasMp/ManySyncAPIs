from django.urls import path
from . import views

urlpatterns = [
    path('delete/', views.delete_media_view, name='delete-media'),
]
