from django.urls import path

from apps.dashboard import views

app_name = "dashboard"

urlpatterns = [
    path("overview/", views.DashboardOverviewView.as_view(), name="overview"),
    path("low-stock/", views.DashboardLowStockView.as_view(), name="low-stock"),
    path("customers/", views.StaffCustomerListView.as_view(), name="customers"),
]
