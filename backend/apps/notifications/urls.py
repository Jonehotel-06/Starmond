from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    EnquiryCreateView,
    MyNotificationsView,
    NewsletterView,
    StaffEnquiryViewSet,
    StaffNewsletterViewSet,
)

app_name = "notifications"

router = DefaultRouter()
router.register("enquiries/admin", StaffEnquiryViewSet, basename="enquiry-staff")
router.register("newsletter/admin", StaffNewsletterViewSet, basename="newsletter-staff")

urlpatterns = [
    path("mine/", MyNotificationsView.as_view(), name="my-notifications"),
    path("newsletter/", NewsletterView.as_view(), name="newsletter"),
    path("enquiries/", EnquiryCreateView.as_view(), name="enquiry-create"),
    path("", include(router.urls)),
]
