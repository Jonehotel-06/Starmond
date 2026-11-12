from django.urls import path

from apps.shipping import views

app_name = "shipping"

urlpatterns = [
    path("states/", views.ShippingStatesView.as_view(), name="states"),
    path("quote/", views.ShippingQuoteView.as_view(), name="quote"),
    path("track/<str:order_number>/", views.CustomerTrackingView.as_view(), name="track"),
    path("admin/shipments/<str:order_number>/", views.StaffShipmentCreateView.as_view(), name="create-shipment"),
    path("admin/shipments/<str:tracking_reference>/events/", views.StaffShipmentEventView.as_view(), name="shipment-event"),
]
