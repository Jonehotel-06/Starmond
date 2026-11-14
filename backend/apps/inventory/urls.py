from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import InventoryMovementViewSet, InventoryViewSet

app_name = "inventory"

router = DefaultRouter()
router.register("movements", InventoryMovementViewSet, basename="inventory-movement")
router.register("", InventoryViewSet, basename="inventory")

urlpatterns = [path("", include(router.urls))]
