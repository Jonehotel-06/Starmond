from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import (
    CustomerOrderDetailView,
    CustomerOrderListView,
    GuestOrderLookupView,
    StaffOrderViewSet,
)

app_name = "orders"

# SimpleRouter: a DefaultRouter API-root at "" would shadow the customer order list.
router = SimpleRouter()
router.register("admin", StaffOrderViewSet, basename="order-staff")

urlpatterns = [
    path("lookup/", GuestOrderLookupView.as_view(), name="guest-lookup"),
    path("", include(router.urls)),
    path("", CustomerOrderListView.as_view(), name="customer-orders"),
    path("<str:reference>/", CustomerOrderDetailView.as_view(), name="customer-order-detail"),
]
