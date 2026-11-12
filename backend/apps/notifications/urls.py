from django.urls import path

from apps.notifications import views

app_name = "notifications"

urlpatterns = [
    path("", views.NotificationListView.as_view(), name="list"),
    path("newsletter/", views.NewsletterSubscribeView.as_view(), name="newsletter"),
    path("enquiries/", views.EnquiryCreateView.as_view(), name="enquiry"),
    path("admin/enquiries/", views.StaffEnquiryListView.as_view(), name="staff-enquiries"),
]
