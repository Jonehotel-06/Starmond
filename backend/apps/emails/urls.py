from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import StaffEmailLogViewSet

app_name = "emails"

router = DefaultRouter()
router.register("logs", StaffEmailLogViewSet, basename="email-log")

urlpatterns = [path("", include(router.urls))]
