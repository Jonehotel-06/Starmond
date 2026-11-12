from django.urls import path

from apps.refunds import views

app_name = "refunds"

urlpatterns = [
    path("", views.CustomerRefundRequestView.as_view(), name="request"),
    path("mine/", views.CustomerRefundListView.as_view(), name="mine"),
    path("eligibility/<str:order_number>/", views.RefundEligibilityView.as_view(), name="eligibility"),
    path("admin/", views.StaffRefundQueueView.as_view(), name="staff-queue"),
    path("admin/<uuid:refund_id>/<str:action>/", views.StaffRefundActionView.as_view(), name="staff-action"),
]
