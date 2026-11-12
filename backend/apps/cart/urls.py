from django.urls import path

from apps.cart import views

app_name = "cart"

urlpatterns = [
    path("", views.CartView.as_view(), name="detail"),
    path("items/", views.CartItemView.as_view(), name="add-item"),
    path("items/<uuid:item_id>/", views.CartItemView.as_view(), name="item"),
    path("promotions/", views.CartPromotionView.as_view(), name="apply-code"),
    path("promotions/<str:code>/", views.CartPromotionView.as_view(), name="remove-code"),
    path("merge/", views.CartMergeView.as_view(), name="merge"),
]
