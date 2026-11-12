"""In-app notifications, newsletter signup and the contact inbox."""
from __future__ import annotations

from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.throttling import ScopedRateThrottle

from apps.core.pagination import StandardResultsSetPagination
from apps.core.permissions import RequiresPermission
from apps.core.views import BaseAPIView, client_ip
from apps.notifications.models import Enquiry
from apps.notifications.serializers import (
    EnquirySerializer, NewsletterSerializer, NotificationSerializer, StaffEnquirySerializer,
)
from apps.notifications.services import NotificationService


class NotificationListView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = request.user.notifications.all()
        if request.query_params.get("unread") in {"1", "true"}:
            queryset = queryset.filter(is_read=False)
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        response = paginator.get_paginated_response(NotificationSerializer(page, many=True).data)
        response.data["unread_count"] = request.user.notifications.filter(is_read=False).count()
        return response

    def post(self, request):
        """Marks one notification, or all of them, as read."""
        notification_id = request.data.get("id")
        if notification_id:
            updated = request.user.notifications.filter(pk=notification_id).update(
                is_read=True, read_at=__import__("django.utils.timezone", fromlist=["now"]).now()
            )
        else:
            updated = NotificationService.mark_all_read(request.user)
        return self.ok({"updated": updated}, message="Notifications updated.")


class NewsletterSubscribeView(BaseAPIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = NewsletterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        NotificationService.subscribe_newsletter(
            email=serializer.validated_data["email"],
            name=serializer.validated_data.get("name", ""),
            source="website",
        )
        return self.created(message="You are subscribed. Welcome aboard.")


class EnquiryCreateView(BaseAPIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = EnquirySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        NotificationService.record_enquiry(
            name=data["name"], email=data["email"], subject=data["subject"],
            message=data["message"], phone=data.get("phone", ""),
            order_number=data.get("order_number", ""),
            user=request.user if request.user.is_authenticated else None,
            source_ip=client_ip(request),
        )
        return self.created(message="Thank you. Our team will respond shortly.")


class StaffEnquiryListView(BaseAPIView):
    permission_classes = [RequiresPermission.of("notifications.change_enquiry")]

    def get(self, request):
        queryset = Enquiry.objects.order_by("-created_at")
        if request.query_params.get("status"):
            queryset = queryset.filter(status=request.query_params["status"])
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(StaffEnquirySerializer(page, many=True).data)
