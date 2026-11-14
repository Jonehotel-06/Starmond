from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CustomerOrderDetailView,
    CustomerOrderListView,
    GuestOrderLookupView,
    StaffOrderViewSet,
)

app_name = "orders"

router = DefaultRouter()
router.register("admin", StaffOrderViewSet, basename="order-staff")

urlpatterns = [
    path("lookup/", GuestOrderLookupView.as_view(), name="guest-lookup"),
    path("", include(router.urls)),
    path("", CustomerOrderListView.as_view(), name="customer-orders"),
    path("<str:reference>/", CustomerOrderDetailView.as_view(), name="customer-order-detail"),
]
