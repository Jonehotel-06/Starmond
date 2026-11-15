from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CustomerReviewCreateView, CustomerReviewListView, ProductReviewListView, RecentReviewsView, StaffReviewViewSet

app_name = "reviews"

router = DefaultRouter()
router.register("product/(?P<product_slug>[^/]+)", ProductReviewListView, basename="product-reviews")
router.register("admin", StaffReviewViewSet, basename="review-staff")

urlpatterns = [
    path("", CustomerReviewCreateView.as_view({"post": "create"}), name="review-create"),
    path("recent/", RecentReviewsView.as_view({"get": "list"}), name="review-recent"),
    path("mine/", CustomerReviewListView.as_view({"get": "list"}), name="review-mine"),
    path("", include(router.urls)),
]
