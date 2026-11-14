from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CustomerReviewCreateView, ProductReviewListView, StaffReviewViewSet

app_name = "reviews"

router = DefaultRouter()
router.register("product/(?P<product_slug>[^/]+)", ProductReviewListView, basename="product-reviews")
router.register("admin", StaffReviewViewSet, basename="review-staff")

urlpatterns = [
    path("", CustomerReviewCreateView.as_view({"post": "create"}), name="review-create"),
    path("", include(router.urls)),
]
