"""Payment endpoints: initialise, verify, and the signed Paystack webhook."""
from __future__ import annotations

import logging

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from rest_framework import serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.throttling import ScopedRateThrottle

from apps.core.exceptions import NotFound, PermissionDeniedError, ValidationError
from apps.core.views import BaseAPIView, client_ip
from apps.orders.models import Order
from apps.orders.services import OrderService
from apps.payments.models import PaymentWebhookEvent
from apps.payments.paystack import PaystackService
from apps.payments.services import PaymentService

logger = logging.getLogger("payments.views")

MAX_WEBHOOK_BYTES = 256 * 1024


class InitializeSerializer(serializers.Serializer):
    order_number = serializers.CharField(max_length=32)
    guest_token = serializers.CharField(required=False, allow_blank=True)
    channel_hint = serializers.CharField(required=False, allow_blank=True, max_length=40)


class VerifySerializer(serializers.Serializer):
    reference = serializers.CharField(max_length=100)


class PaymentInitializeView(BaseAPIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "checkout"

    def post(self, request):
        serializer = InitializeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        order = Order.objects.filter(order_number=data["order_number"]).first()
        if order is None:
            raise NotFound("Order not found.")

        # Ownership: the signed-in customer, or a guest holding the order token.
        if order.customer_id:
            if not request.user.is_authenticated or request.user.pk != order.customer_id:
                raise PermissionDeniedError("You cannot pay for this order.")
        else:
            token = data.get("guest_token") or request.META.get("HTTP_X_ORDER_TOKEN", "")
            if not order.verify_guest_token(token):
                raise PermissionDeniedError("You cannot pay for this order.")

        payload = PaymentService.initialize_order_payment(
            order, actor=request.user if request.user.is_authenticated else None,
            ip=client_ip(request), channel_hint=data.get("channel_hint", ""),
        )
        return self.ok(payload, message="Payment initialised.")


class PaymentVerifyView(BaseAPIView):
    """Client return handler. Verification still happens server-side at Paystack."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "checkout"

    def get(self, request):
        reference = request.query_params.get("reference", "")
        if not reference:
            raise ValidationError("A payment reference is required.")
        payment = PaymentService.verify_payment(
            reference, actor=request.user if request.user.is_authenticated else None,
            source="client_return",
        )
        return self.ok(PaymentService.public_payment_status(payment.order), message="Payment verified.")

    def post(self, request):
        serializer = VerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = PaymentService.verify_payment(
            serializer.validated_data["reference"],
            actor=request.user if request.user.is_authenticated else None,
            source="client_return",
        )
        return self.ok(PaymentService.public_payment_status(payment.order), message="Payment verified.")


class PaymentConfigView(BaseAPIView):
    """The only Paystack information the browser is allowed to receive."""

    permission_classes = [AllowAny]

    def get(self, request):
        return self.ok(PaystackService.public_config())


@method_decorator(csrf_exempt, name="dispatch")
class PaystackWebhookView(View):
    """
    Paystack webhook receiver.

    Order of operations is deliberate:
    1. read the raw body,
    2. verify the HMAC signature,
    3. store the event once (unique event key),
    4. re-verify the transaction with Paystack before any money is recognised.

    Always answers 200 for accepted/rejected events so Paystack stops retrying
    for reasons that will never change (bad signature), while genuine processing
    failures return 200 too and are recorded for reconciliation.
    """

    def post(self, request, *args, **kwargs):
        raw_body = request.body or b""
        if len(raw_body) > MAX_WEBHOOK_BYTES:
            logger.warning("Oversized webhook body rejected (%s bytes)", len(raw_body))
            return JsonResponse({"status": "rejected", "reason": "payload_too_large"}, status=413)

        signature = request.META.get("HTTP_X_PAYSTACK_SIGNATURE", "")
        valid = PaystackService.verify_webhook_signature(raw_body, signature)

        try:
            payload = PaystackService.parse_webhook(raw_body)
        except ValidationError:
            logger.warning("Unparseable webhook body")
            return JsonResponse({"status": "rejected", "reason": "invalid_payload"}, status=400)

        if not valid:
            event = PaymentService.record_webhook(
                payload=payload, signature=signature, valid_signature=False,
                source_ip=client_ip(request),
            )
            event.mark(PaymentWebhookEvent.ProcessingStatus.REJECTED, "Invalid signature.")
            logger.warning("Webhook rejected: invalid signature (event=%s)", payload.get("event"))
            return JsonResponse({"status": "rejected", "reason": "invalid_signature"}, status=401)

        event = PaymentService.record_webhook(
            payload=payload, signature=signature, valid_signature=True,
            source_ip=client_ip(request),
        )
        if event.processing_status == PaymentWebhookEvent.ProcessingStatus.DUPLICATE:
            return JsonResponse({"status": "duplicate", "event_key": event.event_key})

        result = PaymentService.process_webhook_event(event)
        return JsonResponse({"status": "ok", **result})
