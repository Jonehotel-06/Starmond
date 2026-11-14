from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import PublicCategoryViewSet, StaffCategoryViewSet

app_name = "categories"

staff_router = SimpleRouter()
staff_router.register("admin", StaffCategoryViewSet, basename="category-staff")

public_router = SimpleRouter()
public_router.register("", PublicCategoryViewSet, basename="category-public")

urlpatterns = [
    path("", include(staff_router.urls)),
    path("", include(public_router.urls)),
]
