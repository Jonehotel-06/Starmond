from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CustomerPaymentListView,
    PaystackInitializeView,
    PaystackVerifyView,
    PaystackWebhookView,
    StaffPaymentViewSet,
)

app_name = "payments"

router = DefaultRouter()
router.register("admin", StaffPaymentViewSet, basename="payment-staff")

urlpatterns = [
    path("paystack/initialize/", PaystackInitializeView.as_view(), name="paystack-initialize"),
    path("paystack/verify/", PaystackVerifyView.as_view(), name="paystack-verify"),
    path("paystack/webhook/", PaystackWebhookView.as_view(), name="paystack-webhook"),
    path("mine/", CustomerPaymentListView.as_view(), name="customer-payments"),
    path("", include(router.urls)),
]
