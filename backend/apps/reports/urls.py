from django.urls import path

from .views import (
    CategoryReportView,
    OrdersReportView,
    PaymentsReportView,
    ProductReportView,
    RefundsReportView,
    SalesReportView,
)

app_name = "reports"

urlpatterns = [
    path("sales/", SalesReportView.as_view(), name="sales"),
    path("categories/", CategoryReportView.as_view(), name="categories"),
    path("products/", ProductReportView.as_view(), name="products"),
    path("payments/", PaymentsReportView.as_view(), name="payments"),
    path("refunds/", RefundsReportView.as_view(), name="refunds"),
    path("orders/", OrdersReportView.as_view(), name="orders"),
]
