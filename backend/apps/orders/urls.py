from django.urls import path

from apps.orders import admin_views, views

app_name = "orders"

urlpatterns = [
    path("checkout/preview/", views.CheckoutPreviewView.as_view(), name="checkout-preview"),
    path("checkout/cart/", views.CartCheckoutView.as_view(), name="checkout-cart"),
    path("checkout/buy-now/", views.BuyNowCheckoutView.as_view(), name="checkout-buy-now"),
    path("", views.CustomerOrderListView.as_view(), name="list"),
    path("guest/<str:order_number>/", views.GuestOrderDetailView.as_view(), name="guest-detail"),
    path("admin/", admin_views.StaffOrderListView.as_view(), name="admin-list"),
    path("admin/<str:order_number>/", admin_views.StaffOrderDetailView.as_view(), name="admin-detail"),
    path("admin/<str:order_number>/transition/", admin_views.StaffOrderTransitionView.as_view(), name="admin-transition"),
    path("<str:order_number>/", views.CustomerOrderDetailView.as_view(), name="detail"),
    path("<str:order_number>/cancel/", views.CustomerOrderCancelView.as_view(), name="cancel"),
    path("<str:order_number>/track/", views.CustomerOrderTrackView.as_view(), name="track"),
    path("<str:order_number>/receipt/", views.OrderReceiptView.as_view(), name="receipt"),
]
