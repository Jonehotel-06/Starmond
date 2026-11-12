from django.urls import path

from apps.reports import views

app_name = "reports"

urlpatterns = [
    path("summary/", views.SalesSummaryView.as_view(), name="summary"),
    path("full/", views.FullReportView.as_view(), name="full"),
    path("export/<str:fmt>/", views.ReportExportView.as_view(), name="export"),
]
