from django.urls import path

from .views import CartItemDetailView, CartMergeView, CartView

app_name = "cart"

urlpatterns = [
    path("", CartView.as_view(), name="cart"),
    path("merge/", CartMergeView.as_view(), name="cart-merge"),
    path("items/<int:item_id>/", CartItemDetailView.as_view(), name="cart-item"),
]
