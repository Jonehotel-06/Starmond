from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import PromotionValidateView, StaffPromotionViewSet

app_name = "promotions"

router = DefaultRouter()
router.register("validate", PromotionValidateView, basename="promotion-validate")
router.register("", StaffPromotionViewSet, basename="promotion-staff")

urlpatterns = [path("", include(router.urls))]
