from django.urls import path

from .views_staff import StaffCustomerListView

app_name = "customers_staff"

urlpatterns = [
    path("", StaffCustomerListView.as_view(), name="customer-list"),
]
