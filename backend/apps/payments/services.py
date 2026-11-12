"""
PaymentService — order payment lifecycle.

The one non-negotiable rule: an order becomes paid **only** after
``PaystackService.verify_transaction`` returns a successful, amount-matching,
currency-matching transaction for that exact order.
"""
from __future__ import annotations

import logging
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.audit.services import AuditService
from apps.core.exceptions import (
    ConflictError,
    NotFound,
    PaymentError,
    ValidationError,
)
from apps.core.utils import money
from apps.orders.models import Order
from apps.payments.models import Payment, PaymentWebhookEvent
from apps.payments.paystack import PaystackResponse, PaystackService

logger = logging.getLogger("payments")

SUCCESSFUL_EVENTS = {"charge.success", "transaction.success"}
FAILED_EVENTS = {"charge.failed", "transaction.failed"}
REFUND_EVENTS = {"refund.processed", "refund.pending", "refund.failed", "refund.needs-attention"}


class PaymentService:
    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------
    @staticmethod
    def generate_reference(order: Order) -> str:
        return f"STM-{order.order_number}-{uuid.uuid4().hex[:8].upper()}"

    @staticmethod
    @transaction.atomic
    def initialize_order_payment(
        order: Order, *, actor=None, ip: str | None = None, channel_hint: str = ""
    ) -> dict:
        """
        Creates a payment attempt and returns Paystack's authorization URL.

        Guards: the order must be payable, unpaid, unexpired and priced above
        zero. A paid order can never be paid again.
        """
        locked = Order.objects.select_for_update().get(pk=order.pk)

        if locked.payment_status == Order.PaymentStatus.PAID:
            raise ConflictError("This order has already been paid.")
        if locked.payment_status == Order.PaymentStatus.PENDING:
            # A previous attempt is still open; reuse it rather than stacking rows.
            existing = locked.payments.filter(
                status__in=[Payment.Status.INITIALIZED, Payment.Status.PENDING]
            ).order_by("-created_at").first()
            if existing is not None and existing.access_code:
                return PaymentService._authorization_payload(existing, reused=True)
        if locked.status in {Order.Status.CANCELLED, Order.Status.EXPIRED}:
            raise ConflictError("This order is no longer payable.")
        if locked.grand_total <= 0:
            raise ValidationError("This order has no payable amount.")

        email = locked.customer_email
        if not email:
            raise ValidationError("An email address is required to pay for this order.")

        reference = PaymentService.generate_reference(locked)
        amount = money(locked.grand_total)

        payment = Payment.objects.create(
            order=locked,
            reference=reference,
            amount=amount,
            amount_kobo=int(amount * 100),
            currency=locked.currency,
            status=Payment.Status.INITIALIZED,
            initiated_by=actor if getattr(actor, "pk", None) else None,
            initiator_ip=ip,
        )

        response: PaystackResponse = PaystackService.initialize_transaction(
            email=email,
            amount=amount,
            reference=reference,
            currency=locked.currency,
            metadata={
                "order_number": locked.order_number,
                "order_id": str(locked.pk),
                "customer_id": str(locked.customer_id) if locked.customer_id else None,
                "payment_id": str(payment.pk),
                "channel_hint": channel_hint,
            },
        )

        payment.provider_reference = response.reference or reference
        payment.access_code = str(response.data.get("access_code", ""))
        payment.status = Payment.Status.PENDING
        payment.raw_initialize_response = response.raw
        payment.save(
            update_fields=[
                "provider_reference", "access_code", "status", "raw_initialize_response", "updated_at",
            ]
        )

        locked.payment_status = Order.PaymentStatus.PENDING
        locked.save(update_fields=["payment_status", "updated_at"])

        from apps.orders.services import OrderService

        OrderService.add_activity(
            locked,
            event="payment_initiated",
            message="Payment initialised with Paystack.",
            actor=actor,
            metadata={"reference": reference},
        )
        AuditService.record(
            action="payment_initiated",
            entity_type="payment",
            entity_id=payment.pk,
            actor=actor,
            summary=f"Payment {reference} initialised for order {locked.order_number}",
            after={"amount": str(amount), "currency": locked.currency},
        )

        return PaymentService._authorization_payload(payment, reused=False)

    @staticmethod
    def _authorization_payload(payment: Payment, *, reused: bool) -> dict:
        data = payment.raw_initialize_response.get("data", {}) if payment.raw_initialize_response else {}
        return {
            "payment_id": str(payment.pk),
            "reference": payment.reference,
            "authorization_url": data.get("authorization_url"),
            "access_code": payment.access_code,
            "amount": str(money(payment.amount)),
            "currency": payment.currency,
            "reused_existing_attempt": reused,
            "public_key": settings.PAYSTACK_PUBLIC_KEY,
            "mode": settings.PAYSTACK_MODE,
        }

    # ------------------------------------------------------------------
    # Verification & settlement
    # ------------------------------------------------------------------
    @staticmethod
    def verify_payment(reference: str, *, actor=None, source: str = "verify") -> Payment:
        """
        Verifies a transaction directly with Paystack and settles it if valid.

        Used by both the client return-redirect endpoint and the webhook path, so
        the two can never disagree.
        """
        payment = Payment.objects.select_related("order").filter(reference=reference).first()
        if payment is None:
            raise NotFound("That payment reference is unknown.")

        if payment.is_successful:
            return payment  # idempotent

        response = PaystackService.verify_transaction(reference or payment.provider_reference)
        if not response.ok or not response.data:
            PaymentService.record_failure(payment.pk, response.message or "Verification failed.")
            raise PaymentError(
                "We could not verify this payment. If you were debited, contact support with your reference.",
                code="payment_verification_failed",
            )
        try:
            return PaymentService.settle_from_verification(
                payment, response, actor=actor, source=source
            )
        except PaymentError as exc:
            # The settlement transaction rolled back, so the failure record must
            # be written separately or it would be rolled back with it.
            PaymentService.record_failure(payment.pk, exc.message)
            raise

    @staticmethod
    def record_failure(payment_id, reason: str) -> None:
        """Persists a failed payment attempt outside any caller transaction."""
        payment = Payment.objects.filter(pk=payment_id).first()
        if payment is None or payment.is_successful:
            return
        PaymentService._mark_failed(payment, reason)

    @staticmethod
    @transaction.atomic
    def settle_from_verification(
        payment: Payment, response: PaystackResponse, *, actor=None, source: str = "verify"
    ) -> Payment:
        """
        Applies a verified Paystack transaction to our records.

        Every validation below is mandatory — a single mismatch means no money
        is recognised.
        """
        locked = Payment.objects.select_for_update().select_related("order").get(pk=payment.pk)
        order = Order.objects.select_for_update().get(pk=locked.order_id)
        data = response.data

        # --- reference ------------------------------------------------------
        returned_reference = str(data.get("reference", "")).strip()
        if returned_reference and returned_reference != locked.reference and returned_reference != locked.provider_reference:
            raise PaymentError(
                "The verified transaction does not match this payment reference.",
                code="payment_reference_mismatch",
            )

        # --- outcome --------------------------------------------------------
        if not response.paid:
            PaymentService._mark_failed(
                locked, str(data.get("gateway_response", "") or "Transaction was not successful.")
            )
            raise PaymentError(
                "This payment was not successful. No money has been taken.",
                code="payment_not_successful",
            )

        # --- currency -------------------------------------------------------
        returned_currency = str(data.get("currency", locked.currency)).upper()
        if returned_currency != order.currency.upper():
            PaymentService._mark_failed(locked, f"Currency mismatch: {returned_currency}")
            raise PaymentError(
                "The payment currency does not match the order.", code="payment_currency_mismatch"
            )

        # --- amount ---------------------------------------------------------
        paid_amount = money(Decimal(str(data.get("amount", 0))) / 100)
        if paid_amount < money(locked.amount):
            PaymentService._mark_failed(
                locked, f"Underpayment: paid {paid_amount} of {locked.amount}"
            )
            raise PaymentError(
                "The amount paid does not match the order total. Please contact support.",
                code="payment_amount_mismatch",
                details={"expected": str(locked.amount), "received": str(paid_amount)},
            )

        # --- already settled? (double-payment / replay protection) ----------
        if locked.is_successful:
            return locked

        locked.status = Payment.Status.SUCCESS
        locked.is_verified = True
        locked.amount_verified = paid_amount
        locked.channel = str(data.get("channel", ""))[:40]
        locked.gateway_response = str(data.get("gateway_response", ""))[:255]
        locked.authorization = {
            k: v for k, v in (data.get("authorization") or {}).items()
            if k in {"authorization_code", "bin", "last4", "exp_month", "exp_year", "card_type", "bank", "channel", "brand", "signature", "reusable"}
        }
        customer = data.get("customer") or {}
        locked.customer_payload = {
            "email": customer.get("email"),
            "customer_code": customer.get("customer_code"),
            "phone": customer.get("phone"),
        }
        locked.provider_reference = str(data.get("reference") or locked.provider_reference)[:120]
        locked.paid_at = _parse_paystack_time(data.get("paid_at")) or timezone.now()
        locked.verified_at = timezone.now()
        locked.raw_verify_response = response.raw
        locked.save()

        # --- settle the order ----------------------------------------------
        from apps.orders.services import OrderService

        OrderService.mark_paid(order, payment=locked, actor=actor, source=source)

        AuditService.record(
            action="payment_verified",
            entity_type="payment",
            entity_id=locked.pk,
            actor=actor,
            summary=f"Payment {locked.reference} verified for {order.order_number}",
            after={
                "amount": str(paid_amount),
                "currency": returned_currency,
                "channel": locked.channel,
                "source": source,
            },
        )
        logger.info(
            "Payment settled: order=%s reference=%s amount=%s source=%s",
            order.order_number, locked.reference, paid_amount, source,
        )
        return locked

    @staticmethod
    def _mark_failed(payment: Payment, reason: str) -> Payment:
        if payment.is_successful:
            return payment  # never downgrade a settled payment
        payment.status = Payment.Status.FAILED
        payment.failure_reason = (reason or "Payment failed")[:255]
        payment.gateway_response = (reason or "")[:255]
        payment.failed_at = timezone.now()
        payment.save(
            update_fields=["status", "failure_reason", "gateway_response", "failed_at", "updated_at"]
        )
        order = payment.order
        if order.payment_status == Order.PaymentStatus.PENDING:
            order.payment_status = Order.PaymentStatus.FAILED
            order.save(update_fields=["payment_status", "updated_at"])
        from apps.orders.services import OrderService

        OrderService.add_activity(
            order, event="payment_failed", message=f"Payment attempt failed: {reason}"[:300]
        )
        AuditService.record(
            action="payment_failed",
            entity_type="payment",
            entity_id=payment.pk,
            summary=f"Payment {payment.reference} failed: {reason}"[:255],
        )
        return payment

    # ------------------------------------------------------------------
    # Webhooks
    # ------------------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def record_webhook(*, payload: dict, signature: str, valid_signature: bool,
                       source_ip: str | None = None) -> PaymentWebhookEvent:
        """
        Stores a webhook delivery exactly once.

        ``event_key`` combines the event type and the Paystack transaction id, so
        a retried delivery resolves to the same row and is marked duplicate.
        """
        event_type = str(payload.get("event", ""))[:80]
        data = payload.get("data") or {}
        transaction_reference = str(
            data.get("reference") or data.get("transaction_reference") or data.get("id") or ""
        )[:120]
        event_key = f"paystack:{event_type}:{transaction_reference or payload.get('id', '')}"
        event_key = event_key[:200]

        existing = PaymentWebhookEvent.objects.filter(event_key=event_key).first()
        if existing is not None:
            existing.mark(PaymentWebhookEvent.ProcessingStatus.DUPLICATE,
                          "Duplicate delivery ignored.")
            return existing

        payment = Payment.objects.filter(
            reference=transaction_reference
        ).first() or Payment.objects.filter(provider_reference=transaction_reference).first()

        event = PaymentWebhookEvent.objects.create(
            provider="paystack",
            event_key=event_key,
            event_type=event_type,
            transaction_reference=transaction_reference,
            payment=payment,
            order=payment.order if payment else None,
            payload=payload,
            signature=signature[:255],
            signature_valid=valid_signature,
            source_ip=source_ip,
        )
        return event

    @staticmethod
    def process_webhook_event(event: PaymentWebhookEvent) -> dict:
        """Dispatches a stored webhook to the right handler. Idempotent by design."""
        if event.processing_status in {
            PaymentWebhookEvent.ProcessingStatus.PROCESSED,
            PaymentWebhookEvent.ProcessingStatus.DUPLICATE,
        }:
            return {"status": "already_processed", "event": event.event_key}

        if not event.signature_valid:
            event.mark(PaymentWebhookEvent.ProcessingStatus.REJECTED, "Invalid signature.")
            AuditService.record(
                action="webhook_rejected",
                entity_type="webhook",
                entity_id=event.pk,
                summary=f"Rejected webhook {event.event_type}: invalid signature",
                metadata={"source_ip": event.source_ip},
            )
            return {"status": "rejected"}

        if event.event_type in SUCCESSFUL_EVENTS:
            return PaymentService._handle_charge_success(event)
        if event.event_type in FAILED_EVENTS:
            return PaymentService._handle_charge_failed(event)
        if event.event_type in REFUND_EVENTS:
            return PaymentService._handle_refund_event(event)

        event.mark(PaymentWebhookEvent.ProcessingStatus.PROCESSED,
                   f"No handler for {event.event_type}; acknowledged.")
        return {"status": "ignored"}

    @staticmethod
    def _handle_charge_success(event: PaymentWebhookEvent) -> dict:
        reference = str((event.payload.get("data") or {}).get("reference", ""))[:120]
        payment = event.payment or Payment.objects.filter(reference=reference).first()
        if payment is None:
            event.mark(PaymentWebhookEvent.ProcessingStatus.FAILED,
                       "No matching payment for this reference.")
            logger.warning("Webhook for unknown reference %s", reference)
            return {"status": "unknown_reference"}

        if payment.is_successful:
            event.mark(PaymentWebhookEvent.ProcessingStatus.PROCESSED,
                       "Payment already settled; no double credit.")
            return {"status": "already_settled"}

        try:
            # Never trust the webhook body itself: re-verify with Paystack.
            verified = PaystackService.verify_transaction(reference)
            PaymentService.settle_from_verification(payment, verified, source="webhook")
            event.payment = payment
            event.order = payment.order
            event.save(update_fields=["payment", "order", "updated_at"])
            event.mark(PaymentWebhookEvent.ProcessingStatus.PROCESSED, "Payment settled via webhook.")
            return {"status": "settled", "reference": reference}
        except (PaymentError, ConflictError, ValidationError) as exc:
            event.mark(PaymentWebhookEvent.ProcessingStatus.FAILED, str(exc)[:255])
            if isinstance(exc, PaymentError):
                PaymentService.record_failure(payment.pk, exc.message)
            logger.warning("Webhook settlement failed for %s: %s", reference, exc)
            return {"status": "failed", "detail": str(exc)}

    @staticmethod
    def _handle_charge_failed(event: PaymentWebhookEvent) -> dict:
        reference = str((event.payload.get("data") or {}).get("reference", ""))
        payment = event.payment or Payment.objects.filter(reference=reference).first()
        if payment is not None and not payment.is_successful:
            reason = str((event.payload.get("data") or {}).get("gateway_response", "Charge failed"))
            PaymentService._mark_failed(payment, reason)
        event.mark(PaymentWebhookEvent.ProcessingStatus.PROCESSED, "Failure recorded.")
        return {"status": "recorded"}

    @staticmethod
    def _handle_refund_event(event: PaymentWebhookEvent) -> dict:
        """Refund state changes are finalised by RefundService against the provider."""
        from apps.refunds.services import RefundService

        event.mark(PaymentWebhookEvent.ProcessingStatus.PROCESSED,
                   "Refund event acknowledged; RefundService reconciles provider state.")
        try:
            RefundService.reconcile_pending()
        except Exception:  # pragma: no cover - reconciliation is best-effort here
            logger.exception("Refund reconciliation triggered by webhook failed")
        return {"status": "acknowledged"}

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    @staticmethod
    def public_payment_status(order: Order) -> dict:
        # Always report fresh database state: callers frequently hold an Order
        # instance that was loaded before the settlement transaction ran.
        order = Order.objects.get(pk=order.pk)
        latest = order.payments.order_by("-created_at").first()
        return {
            "order_number": order.order_number,
            "payment_status": order.payment_status,
            "order_status": order.status,
            "amount": str(order.grand_total),
            "amount_paid": str(order.amount_paid),
            "currency": order.currency,
            "reference": latest.reference if latest else None,
            "paid_at": order.paid_at.isoformat() if order.paid_at else None,
        }


def _parse_paystack_time(value):
    if not value:
        return None
    from django.utils.dateparse import parse_datetime

    try:
        parsed = parse_datetime(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed
