from django.urls import path
from .views import IgLoginClassView ,UserInstagramAccountsView,IgVerifyLoginView ,get_instagram_stats
urlpatterns = [
    path('post_ig_data', IgLoginClassView.as_view() ),
    path('post_ig_data/<int:pk>/', IgLoginClassView.as_view() ),
    path('varify_login', IgVerifyLoginView.as_view() ),
    path("accounts", UserInstagramAccountsView.as_view()),
    path('stats/<int:igAccountId>', get_instagram_stats, name='instagram_stats'),

]