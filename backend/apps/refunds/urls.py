from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CustomerRefundViewSet, StaffRefundViewSet

app_name = "refunds"

router = DefaultRouter()
router.register("requests", CustomerRefundViewSet, basename="refund-customer")
router.register("admin", StaffRefundViewSet, basename="refund-staff")

urlpatterns = [path("", include(router.urls))]
