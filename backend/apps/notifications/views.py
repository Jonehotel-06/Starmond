from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.audit.services import AuditService
from apps.core.constants import Perm
from apps.core.exceptions import ServiceError
from apps.core.permissions import IsStaffWithPermission
from apps.orders.models import Order

from .models import Enquiry, NewsletterSubscriber, Notification
from .serializers import (
    EnquiryCreateSerializer,
    EnquirySerializer,
    NewsletterSubscriberSerializer,
    NewsletterSubscribeSerializer,
    NotificationSerializer,
)


from drf_spectacular.utils import OpenApiTypes, extend_schema, extend_schema_view

@extend_schema_view(
    get=extend_schema(tags=["notifications"], responses=NotificationSerializer(many=True)),
    post=extend_schema(tags=["notifications"], request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT))
class MyNotificationsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        unread = request.query_params.get("unread")
        qs = Notification.objects.filter(user=request.user)
        if unread in ("1", "true"):
            qs = qs.filter(is_read=False)
        from apps.core.pagination import StandardPagination
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs[:200], request)
        return paginator.get_paginated_response(NotificationSerializer(page, many=True).data)

    def post(self, request):
        ids = request.data.get("ids")
        if ids == "all":
            Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        elif isinstance(ids, list):
            Notification.objects.filter(user=request.user, pk__in=ids).update(is_read=True)
        else:
            raise ServiceError('Provide {"ids": [...]} or {"ids": "all"}.', code="invalid_payload")
        return Response({"status": "success", "message": "Notifications marked read."})


@extend_schema(tags=["notifications"], request=NewsletterSubscribeSerializer, responses=OpenApiTypes.OBJECT)
class NewsletterView(APIView):
    """POST /api/notifications/newsletter/ {email} — public subscribe.
    POST with {"action":"unsubscribe"} removes consent."""
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_action"

    def post(self, request):
        serializer = NewsletterSubscribeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].lower()
        action_type = (request.data.get("action") or "subscribe").lower()
        if action_type == "unsubscribe":
            NewsletterSubscriber.objects.filter(email=email).update(is_active=False, unsubscribed_at=timezone.now())
            return Response({"status": "success", "message": "Unsubscribed."})
        sub, created = NewsletterSubscriber.objects.get_or_create(
            email=email, defaults={"is_active": True, "source": request.META.get("HTTP_ORIGIN", "")[:60]})
        if not created and not sub.is_active:
            sub.is_active, sub.unsubscribed_at = True, None
            sub.save(update_fields=["is_active", "unsubscribed_at"])
        from services.notification_service import NotificationService
        NotificationService.newsletter_welcome(email)
        return Response({"status": "success", "message": "Subscribed."}, status=status.HTTP_201_CREATED)


@extend_schema(tags=["notifications"], request=EnquiryCreateSerializer, responses={201: OpenApiTypes.OBJECT})
class EnquiryCreateView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_action"

    def post(self, request):
        serializer = EnquiryCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        order = None
        if data.get("order_reference"):
            order = Order.objects.filter(reference=data["order_reference"].upper()).first()
        enquiry = Enquiry.objects.create(
            full_name=data["full_name"][:150], email=data["email"].lower(), phone=data.get("phone", "")[:30],
            subject=data["subject"][:200], message=data["message"][:4000], related_order=order)
        from services.notification_service import NotificationService
        NotificationService.enquiry_ack(enquiry)
        return Response({"status": "success", "message": "Enquiry received. Our team will respond by email.",
                         "data": {"id": enquiry.pk}}, status=status.HTTP_201_CREATED)


class StaffEnquiryViewSet(viewsets.ModelViewSet):
    permission_classes = [IsStaffWithPermission]
    permission_codename = Perm.NOTIFICATIONS_MANAGE
    serializer_class = EnquirySerializer
    queryset = Enquiry.objects.select_related("handled_by", "related_order").all()
    filterset_fields = ["status"]
    search_fields = ["full_name", "email", "subject"]
    http_method_names = ["get", "patch", "delete"]

    def perform_update(self, serializer):
        enquiry = serializer.save(handled_by=self.request.user)
        AuditService.log(self.request.user, "enquiry.update", "Enquiry", enquiry.pk, {"status": enquiry.status}, request=self.request)


class StaffNewsletterViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsStaffWithPermission]
    permission_codename = Perm.NOTIFICATIONS_MANAGE
    serializer_class = NewsletterSubscriberSerializer
    queryset = NewsletterSubscriber.objects.all()
    filterset_fields = ["is_active"]
    search_fields = ["email"]
