from django.urls import path
from . import views
from .views import *
urlpatterns = [
    path('', views.index, name='index'),



    path('api/verify-firebase-token/', views.VerifyFirebaseTokenView.as_view(), name='verify_firebase_token'),

    path('api/protected/', ProtectedView.as_view(), name='protected'),  
    path('api/logout/', logout_view, name='protected'),  
    
    path('git-pull', views.git_pull, name='git_pull')
    
]
