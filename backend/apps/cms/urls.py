from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    HomepageView,
    PublicPageViewSet,
    PublicSettingsView,
    StaffBannerViewSet,
    StaffHomepageSectionViewSet,
    StaffPageViewSet,
    StaffSettingsView,
)

app_name = "cms"

router = DefaultRouter()
router.register("pages", PublicPageViewSet, basename="page-public")
router.register("admin/pages", StaffPageViewSet, basename="page-staff")
router.register("admin/sections", StaffHomepageSectionViewSet, basename="section-staff")
router.register("admin/banners", StaffBannerViewSet, basename="banner-staff")

urlpatterns = [
    path("settings/", PublicSettingsView.as_view(), name="public-settings"),
    path("admin/settings/", StaffSettingsView.as_view(), name="staff-settings"),
    path("homepage/", HomepageView.as_view(), name="homepage"),
    path("", include(router.urls)),
]
