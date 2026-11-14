import json
import logging

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import mixins, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import AuditService
from apps.core.constants import Perm
from apps.core.exceptions import ServiceError
from apps.core.permissions import IsStaffWithPermission
from apps.core.throttles import WebhookThrottle
from apps.orders.models import Order

from .models import Payment
from .paystack import PaystackService
from .serializers import (
    PaymentInitializeSerializer,
    PaymentSerializer,
    PaymentVerifySerializer,
)
from .services import PaymentService

logger = logging.getLogger("starmond.payments")


from drf_spectacular.utils import OpenApiTypes, extend_schema

@extend_schema(tags=["payments"], request=PaymentInitializeSerializer, responses=OpenApiTypes.OBJECT)
class PaystackInitializeView(APIView):
    """POST /api/payments/paystack/initialize/ — backend creates the Paystack
    transaction and returns the authorization URL. The secret key is never
    exposed to the client."""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PaymentInitializeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = Order.objects.filter(reference=serializer.validated_data["order_reference"].upper()).first()
        if not order:
            raise ServiceError("Order not found.", code="order_not_found", status_code=404)
        requester = request.user if request.user.is_authenticated else None
        payment = PaymentService.initialize_for_order(
            order, requester=requester, guest_token=serializer.validated_data.get("guest_token"))
        return Response({"status": "success", "data": {
            "payment_reference": payment.reference,
            "provider_reference": payment.provider_reference,
            "authorization_url": payment.authorization_url,
            "access_code": payment.access_code,
            "amount": str(payment.amount),
            "currency": payment.currency,
            "order_reference": order.reference,
        }})


@extend_schema(tags=["payments"], request=PaymentVerifySerializer, responses=OpenApiTypes.OBJECT)
class PaystackVerifyView(APIView):
    """POST /api/payments/paystack/verify/ — the backend independently asks
    Paystack for the transaction result. Redirects are NEVER trusted."""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PaymentVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        requester = request.user if request.user.is_authenticated else None
        payment = PaymentService.verify_and_finalize(
            serializer.validated_data["reference"],
            requester=requester, guest_token=serializer.validated_data.get("guest_token"))
        from services.notification_service import NotificationService
        if payment.status == Payment.Status.SUCCESSFUL:
            NotificationService.payment_successful(payment.order, payment)  # dedup inside
        elif payment.status == Payment.Status.FAILED:
            NotificationService.payment_failed(payment.order, payment)
        return Response({"status": "success", "data": {
            "payment_status": payment.status,
            "order_status": payment.order.status,
            "order_payment_status": payment.order.payment_status,
            "amount": str(payment.amount),
            "currency": payment.currency,
            "verified_at": payment.verified_at,
            "failure_reason": payment.failure_reason or None,
            "order_reference": payment.order.reference,
        }})


@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["payments"], request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT,
    description="Paystack webhook receiver. Signature verified with PAYSTACK_WEBHOOK_SECRET (HMAC SHA-512). Configure this URL in the Paystack dashboard.")
class PaystackWebhookView(APIView):
    """POST /api/payments/paystack/webhook/ — configured in the Paystack
    dashboard. Signature verified with PAYSTACK_WEBHOOK_SECRET (HMAC SHA-512).
    Always answers 200 quickly; events are stored and processed idempotently."""
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [WebhookThrottle]

    def post(self, request):
        raw_body = request.body
        signature = request.headers.get("x-paystack-signature", "")
        if not PaystackService.verify_webhook_signature(raw_body, signature):
            logger.warning("Paystack webhook rejected: invalid signature from %s",
                           request.META.get("REMOTE_ADDR"))
            return Response({"status": "error", "error": {"code": "invalid_signature",
                             "message": "Invalid webhook signature.", "fields": None}}, status=400)
        try:
            event_data = json.loads(raw_body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return Response({"status": "error", "error": {"code": "invalid_payload",
                             "message": "Malformed webhook body.", "fields": None}}, status=400)
        try:
            PaymentService.handle_webhook_event(event_data)
        except Exception:
            logger.exception("Webhook handling error (event stored for replay)")
        return Response({"status": "success", "message": "Event received."})


@extend_schema(tags=["payments"], responses=PaymentSerializer(many=True))
class CustomerPaymentListView(APIView):
    """Authenticated customers see ONLY their own payments."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Payment.objects.filter(order__customer=request.user).select_related("order").order_by("-created_at")
        from apps.core.pagination import StandardPagination
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(PaymentSerializer(page, many=True).data)


class StaffPaymentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsStaffWithPermission]
    permission_codename = Perm.FINANCE_VIEW
    serializer_class = PaymentSerializer
    queryset = Payment.objects.select_related("order").all()
    filterset_fields = ["status", "provider", "order"]
    search_fields = ["reference", "provider_reference", "order__reference"]
    ordering = ["-created_at"]
