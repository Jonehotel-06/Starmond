from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ShippingMethodViewSet, ShippingQuoteView, ShippingZoneViewSet

app_name = "shipping"

router = DefaultRouter()
router.register("options", ShippingQuoteView, basename="shipping-options")
router.register("zones", ShippingZoneViewSet, basename="shipping-zone")
router.register("methods", ShippingMethodViewSet, basename="shipping-method")

urlpatterns = [path("", include(router.urls))]
