from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

app_name = "customers"

router = DefaultRouter()
router.register("addresses", views.AddressViewSet, basename="address")
router.register("wishlist", views.WishlistViewSet, basename="wishlist")

urlpatterns = [
    path("profile/", views.ProfileView.as_view(), name="profile"),
    path("", include(router.urls)),
]
