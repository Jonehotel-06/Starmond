from django.urls import path

from apps.payments import views

app_name = "payments"

urlpatterns = [
    path("initialize/", views.PaymentInitializeView.as_view(), name="initialize"),
    path("verify/", views.PaymentVerifyView.as_view(), name="verify"),
    path("config/", views.PaymentConfigView.as_view(), name="config"),
    path("webhook/paystack/", views.PaystackWebhookView.as_view(), name="paystack-webhook"),
]
