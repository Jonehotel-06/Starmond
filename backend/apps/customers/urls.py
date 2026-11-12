from django.urls import path

from apps.customers import views

app_name = "customers"

urlpatterns = [
    path("addresses/", views.AddressListCreateView.as_view(), name="addresses"),
    path("addresses/<uuid:address_id>/", views.AddressDetailView.as_view(), name="address-detail"),
    path("wishlist/", views.WishlistView.as_view(), name="wishlist"),
]
