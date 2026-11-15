from django.urls import path

from .views import CheckoutPreviewView, CheckoutView

app_name = "checkout"

urlpatterns = [
    path("", CheckoutView.as_view(), name="checkout"),
    path("preview/", CheckoutPreviewView.as_view(), name="checkout-preview"),
]
