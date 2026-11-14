from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ProductSearchView, PublicProductViewSet, StaffProductViewSet

app_name = "products"

router = DefaultRouter()
router.register("search", ProductSearchView, basename="product-search")
router.register("admin", StaffProductViewSet, basename="product-staff")
router.register("", PublicProductViewSet, basename="product-public")

urlpatterns = [path("", include(router.urls))]
