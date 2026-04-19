from django.urls import path
from .views import PlanListView, CreateOrderView, VerifyPaymentView, UserSubscriptionView, TransactionListView, UsageLogListView

urlpatterns = [
    path('plans/', PlanListView.as_view(), name='plan-list'),
    path('create-order/', CreateOrderView.as_view(), name='create-order'),
    path('verify-payment/', VerifyPaymentView.as_view(), name='verify-payment'),
    path('status/', UserSubscriptionView.as_view(), name='subscription-status'),
    path('history/', TransactionListView.as_view(), name='transaction-history'),
    path('usage/', UsageLogListView.as_view(), name='usage-history'),
]
