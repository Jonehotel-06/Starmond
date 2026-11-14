"""PaymentService — order-aware payment orchestration.

Guarantees:
* amounts/currency are ALWAYS re-checked against the order (never trusted
  from the client, the redirect, or the webhook body alone);
* a payment is marked successful at most once (row locks + unique provider
  reference + deduplicated webhook events);
* returning from the redirect URL is NOT proof of payment — success requires
  server-side verification with Paystack.
"""
import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import ServiceError
from apps.core.money import kobo_to_naira, naira_to_kobo, to_decimal
from apps.orders.models import Order
from apps.orders.services import OrderService

from .models import Payment, PaymentWebhookEvent
from .paystack import PaystackError, PaystackService

logger = logging.getLogger("starmond.payments")


class PaymentService:
    # ------------------------------------------------------------ initialize
    @classmethod
    @transaction.atomic
    def initialize_for_order(cls, order, *, requester=None, guest_token=None):
        cls._assert_order_access(order, requester, guest_token)
        order = Order.objects.select_for_update().get(pk=order.pk)
        if order.payment_status == Order.PaymentStatus.PAID:
            successful = order.payments.filter(status=Payment.Status.SUCCESSFUL).first()
            raise ServiceError("This order is already paid.", code="order_already_paid", status_code=409)
        if order.status in (Order.Status.CANCELLED, Order.Status.EXPIRED):
            raise ServiceError("This order can no longer be paid for.", code="order_closed", status_code=409)
        if order.expires_at and order.expires_at < timezone.now():
            OrderService.expire_stale_pending_orders()
            raise ServiceError("This order's payment window has expired. Please check out again.",
                               code="order_expired", status_code=409)
        # Reuse an in-flight pending payment when possible (prevents duplicate
        # initialization spam), otherwise create a fresh attempt.
        pending = order.payments.filter(status=Payment.Status.PENDING,
                                        authorization_url__gt="").order_by("-created_at").first()
        if pending and pending.initialized_at and (timezone.now() - pending.initialized_at).total_seconds() < 3600:
            return pending
        if order.status == Order.Status.PAYMENT_FAILED:
            OrderService.transition(order, Order.Status.PENDING_PAYMENT, note="New payment attempt")
        payment = Payment.objects.create(
            order=order,
            provider_reference=f"{order.reference}-A{order.payments.count() + 1}",
            amount=order.total_amount, currency=order.currency,
            status=Payment.Status.PENDING,
        )
        try:
            result = PaystackService.initialize(
                email=order.contact_email,
                amount_kobo=naira_to_kobo(order.total_amount),
                reference=payment.provider_reference,
                callback_url=f"{settings.FRONTEND_BASE_URL.rstrip('/')}/payment/callback",
                metadata={"order_reference": order.reference, "payment_reference": payment.reference},
            )
        except PaystackError:
            payment.status = Payment.Status.FAILED
            payment.failure_reason = "Initialization failed at provider"
            payment.save(update_fields=["status", "failure_reason", "updated_at"])
            raise
        payment.authorization_url = result["authorization_url"][:500]
        payment.access_code = result["access_code"][:60]
        payment.initialized_at = timezone.now()
        payment.save(update_fields=["authorization_url", "access_code", "initialized_at", "updated_at"])
        return payment

    # --------------------------------------------------------------- verify
    @classmethod
    def verify_and_finalize(cls, provider_reference, *, requester=None, guest_token=None):
        """Server-side verification with Paystack. Idempotent."""
        payment = Payment.objects.select_related("order").filter(provider_reference=provider_reference).first()
        if payment is None:
            raise ServiceError("Unknown payment reference.", code="payment_not_found", status_code=404)
        cls._assert_order_access(payment.order, requester, guest_token)
        if payment.status == Payment.Status.SUCCESSFUL:
            return payment  # already finalized — idempotent
        try:
            data = PaystackService.verify(payment.provider_reference)
        except PaystackError:
            payment.status = Payment.Status.FAILED
            payment.failure_reason = "Verification call failed"
            payment.save(update_fields=["status", "failure_reason", "updated_at"])
            raise
        return cls._apply_provider_result(payment, data)

    @classmethod
    @transaction.atomic
    def _apply_provider_result(cls, payment, data):
        payment = Payment.objects.select_for_update().get(pk=payment.pk)
        if payment.status == Payment.Status.SUCCESSFUL:
            return payment
        order = Order.objects.select_for_update().get(pk=payment.order_id)
        status = (data.get("status") or "").lower()
        amount_kobo = data.get("amount")
        currency = (data.get("currency") or "").upper()
        reference = data.get("reference")

        payment.last_verification_payload = {k: data.get(k) for k in
                                             ("status", "amount", "currency", "reference", "channel",
                                              "gateway_response", "id", "paid_at")}
        if reference and reference != payment.provider_reference:
            payment.status = Payment.Status.FAILED
            payment.failure_reason = "Provider reference mismatch"
            payment.save()
            logger.warning("Reference mismatch: expected %s got %s", payment.provider_reference, reference)
            raise ServiceError("Payment reference mismatch.", code="reference_mismatch", status_code=409)
        if status != "success":
            payment.status = Payment.Status.FAILED
            payment.failure_reason = (data.get("gateway_response") or f"Provider status: {status}")[:255]
            payment.channel = (data.get("channel") or "")[:30]
            payment.save()
            if order.status == Order.Status.PENDING_PAYMENT:
                OrderService.transition(order, Order.Status.PAYMENT_FAILED,
                                        note=f"Payment failed: {payment.failure_reason}")
            return payment
        # --- success path: validate amount and currency against OUR records
        if amount_kobo is None or kobo_to_naira(amount_kobo) != to_decimal(payment.amount):
            payment.status = Payment.Status.FAILED
            payment.failure_reason = f"Amount mismatch (provider: {amount_kobo} kobo)"
            payment.save()
            logger.error("Amount mismatch on payment %s: provider=%s expected=%s",
                         payment.reference, amount_kobo, naira_to_kobo(payment.amount))
            raise ServiceError("Paid amount does not match the order total.", code="amount_mismatch", status_code=409)
        if currency and currency != payment.currency:
            payment.status = Payment.Status.FAILED
            payment.failure_reason = f"Currency mismatch ({currency})"
            payment.save()
            raise ServiceError("Payment currency mismatch.", code="currency_mismatch", status_code=409)

        payment.status = Payment.Status.SUCCESSFUL
        payment.channel = (data.get("channel") or "")[:30]
        payment.provider_transaction_id = data.get("id")
        payment.verified_at = timezone.now()
        payment.failure_reason = ""
        payment.save()
        already_paid = order.payment_status == Order.PaymentStatus.PAID
        OrderService.confirm_paid(order, payment)
        if not already_paid:
            from services.notification_service import NotificationService
            transaction.on_commit(lambda: NotificationService.payment_successful(order, payment))
        return payment

    # --------------------------------------------------------------- webhook
    @classmethod
    def handle_webhook_event(cls, event_data):
        """Idempotent webhook processing. The event is stored FIRST (unique
        provider id), then processed exactly once."""
        event_id = str((event_data.get("data") or {}).get("id") or event_data.get("id") or "")
        event_type = event_data.get("event") or ""
        if not event_id:
            raise ServiceError("Webhook event has no id.", code="invalid_webhook")
        event, created = PaymentWebhookEvent.objects.get_or_create(
            provider_event_id=event_id,
            defaults={"event_type": event_type, "payload": event_data, "signature_valid": True})
        if not created:
            event.payload = event_data
            event.save(update_fields=["payload"])
            return event  # duplicate delivery — already handled (or being handled)
        try:
            cls._route_event(event)
        except Exception as exc:  # keep the event for audit; do not crash the webhook
            logger.exception("Webhook processing failed for %s", event_id)
            event.error = str(exc)[:500]
            event.save(update_fields=["error", "processed_at"])
        return event

    @classmethod
    def _route_event(cls, event):
        data = event.payload.get("data") or {}
        reference = data.get("reference")
        if event.event_type in ("charge.success",):
            payment = Payment.objects.filter(provider_reference=reference).first()
            if not payment:
                event.outcome = "payment_not_found"
                event.processed = True
                event.processed_at = timezone.now()
                event.save()
                return
            event.payment = payment
            # Verify independently with the API (never trust the webhook body
            # alone for money movement).
            try:
                verify_data = PaystackService.verify(reference)
            except PaystackError:
                verify_data = data
            cls._apply_provider_result(payment, verify_data)
        elif event.event_type in ("refund.processed", "refund.failed"):
            cls._handle_refund_event(event, data)
        elif event.event_type in ("charge.success.processed",):
            pass  # informational
        else:
            logger.info("Ignoring Paystack event type %s", event.event_type)
        event.processed = True
        event.processed_at = timezone.now()
        event.save(update_fields=["processed", "processed_at", "payment", "outcome"])

    @classmethod
    def _handle_refund_event(cls, event, data):
        """Finalize refunds from provider webhook outcomes (verified states)."""
        from apps.refunds.models import Refund
        from apps.refunds.services import RefundService
        transaction_ref = ((data.get("transaction") or {}).get("reference")) or data.get("reference") or ""
        payment = Payment.objects.filter(provider_reference=transaction_ref).first()
        if not payment:
            event.outcome = "payment_not_found"
            event.processed = True
            event.processed_at = timezone.now()
            event.save()
            return
        event.payment = payment
        refund_id = str(data.get("id") or "")
        refund = Refund.objects.filter(payment=payment, status=Refund.Status.PROCESSING).first()
        if refund_id:
            refund = Refund.objects.filter(provider_refund_id=refund_id).first() or refund
        if not refund:
            event.outcome = "refund_not_found"
            event.processed = True
            event.processed_at = timezone.now()
            event.save()
            return
        refund.provider_response = data
        if event.event_type == "refund.processed" and str(data.get("status", "")).lower() in ("processed", "success", "paid"):
            RefundService._finalize_success(refund)
            event.outcome = "refund_finalized"
        elif event.event_type == "refund.failed":
            refund.status = Refund.Status.FAILED
            refund.save(update_fields=["status", "provider_response", "updated_at"])
            event.outcome = "refund_failed"
        event.processed = True
        event.processed_at = timezone.now()
        event.save(update_fields=["processed", "processed_at", "payment", "outcome", "error"])

    # ---------------------------------------------------------------- access
    @staticmethod
    def _assert_order_access(order, requester, guest_token):
        from services.checkout_service import CheckoutService
        if requester is not None and getattr(requester, "is_authenticated", False):
            if order.customer_id == requester.pk:
                return
            from apps.core.permissions import user_has_permission
            from apps.core.constants import Perm
            if user_has_permission(requester, Perm.ORDERS_VIEW):
                return
        if order.customer_id is None and guest_token and order.guest_access_token \
                and CheckoutService.verify_guest_token(order, guest_token):
            return
        raise ServiceError("You do not have access to this order's payments.", code="forbidden", status_code=403)
