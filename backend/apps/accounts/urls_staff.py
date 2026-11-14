from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views_staff

app_name = "accounts_staff"

router = DefaultRouter()
router.register("permissions", views_staff.PermissionViewSet, basename="admin-permission")
router.register("roles", views_staff.RoleViewSet, basename="admin-role")
router.register("staff", views_staff.StaffViewSet, basename="admin-staff")

urlpatterns = [
    path("", include(router.urls)),
]
