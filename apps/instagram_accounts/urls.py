from django.urls import path
from .views import *
urlpatterns = [
    path('login', IgLoginClassView.as_view() ),
    path('delete/<int:pk>/', IgDeleteeClassView.as_view() ),
    path("accounts", UserInstagramAccountsView.as_view()),
    path('dashboard-data/<int:igAccountId>', DashboardData.as_view(), name='instagram_stats'),

]