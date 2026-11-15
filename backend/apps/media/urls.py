from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import MediaAssetViewSet, MediaUploadView

app_name = "media"

router = DefaultRouter()
router.register("assets", MediaAssetViewSet, basename="media-asset")

urlpatterns = [
    path("uploads/", MediaUploadView.as_view(), name="upload"),
    path("", include(router.urls)),
]
