from django.urls import path

from apps.inventory import views

app_name = "inventory"

urlpatterns = [
    path("", views.InventoryListView.as_view(), name="list"),
    path("movements/", views.MovementHistoryView.as_view(), name="movements"),
    path("ensure/", views.InventoryEnsureView.as_view(), name="ensure"),
    path("receive/", views.StockReceiveView.as_view(), name="receive"),
    path("adjust/", views.StockAdjustView.as_view(), name="adjust"),
    path("write-off/", views.StockWriteOffView.as_view(), name="write-off"),
    path("<uuid:inventory_id>/", views.InventoryDetailView.as_view(), name="detail"),
]
