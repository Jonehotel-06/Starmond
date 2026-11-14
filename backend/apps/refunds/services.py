"""RefundService — refunds are executed through the official Paystack refund
API and are only marked SUCCESSFUL after the provider confirms the outcome.
Submitting a request NEVER marks anything refunded."""
import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import ServiceError
from apps.core.money import kobo_to_naira, naira_to_kobo, to_decimal
from apps.orders.models import Order
from apps.orders.services import OrderService
from apps.payments.models import Payment

from .models import Refund

logger = logging.getLogger("starmond.refunds")


class RefundService:
    @staticmethod
    def refund_window_days():
        from apps.cms.services import BusinessSettingsService
        try:
            return int(BusinessSettingsService.get("refund_window_days", "7"))
        except (TypeError, ValueError):
            return 7

    @classmethod
    @transaction.atomic
    def request_refund(cls, order, *, requester=None, reason="", amount=None, restock=False, staff_created=False):
        if not reason.strip():
            raise ServiceError("A refund reason is required.", code="reason_required")
        if order.payment_status not in (Order.PaymentStatus.PAID, Order.PaymentStatus.PARTIALLY_REFUNDED):
            raise ServiceError("Only paid orders can be refunded.", code="order_not_paid", status_code=409)
        payment = order.payments.filter(status__in=[Payment.Status.SUCCESSFUL, Payment.Status.PARTIALLY_REFUNDED]).first()
        if not payment:
            raise ServiceError("No successful payment found for this order.", code="payment_missing", status_code=409)
        if not staff_created:
            if order.paid_at and (timezone.now() - order.paid_at).days > cls.refund_window_days():
                raise ServiceError(
                    f"Refund window ({cls.refund_window_days()} days) has elapsed. Contact support.",
                    code="refund_window_elapsed", status_code=409)
        already = order.total_refunded
        open_requests = Refund.objects.filter(order=order, status__in=[Refund.Status.REQUESTED, Refund.Status.APPROVED, Refund.Status.PROCESSING])
        if open_requests.exists():
            raise ServiceError("A refund request for this order is already in progress.", code="refund_in_progress", status_code=409)
        requested = to_decimal(amount) if amount else to_decimal(order.total_amount - already)
        if requested <= Decimal("0"):
            raise ServiceError("Nothing left to refund on this order.", code="nothing_to_refund")
        if already + requested > order.total_amount:
            raise ServiceError("Refund amount exceeds the amount paid on this order.", code="refund_exceeds_payment")
        refund = Refund.objects.create(
            order=order, payment=payment,
            requested_by=requester if getattr(requester, "is_authenticated", False) else None,
            requester_email=(requester.email if getattr(requester, "is_authenticated", False) else order.contact_email),
            reason=reason[:2000], requested_amount=requested, restock_items=bool(restock),
        )
        OrderService.transition(order, Order.Status.REFUND_REQUESTED, actor=requester, note=f"Refund requested: {refund.reference}")
        from services.notification_service import NotificationService
        transaction.on_commit(lambda: NotificationService.refund_requested(refund))
        return refund

    @classmethod
    @transaction.atomic
    def approve(cls, refund, staff, approved_amount=None, notes=""):
        from apps.payments.paystack import PaystackError, PaystackService
        refund = Refund.objects.select_for_update().select_related("order", "payment").get(pk=refund.pk)
        if refund.status not in (Refund.Status.REQUESTED, Refund.Status.FAILED):
            raise ServiceError(f"Refund {refund.reference} is {refund.status} and cannot be approved.",
                               code="invalid_refund_state", status_code=409)
        amount = to_decimal(approved_amount) if approved_amount is not None else refund.requested_amount
        if amount <= Decimal("0") or amount > refund.requested_amount + Decimal("0.01"):
            raise ServiceError("Approved amount must be positive and cannot exceed the requested amount.",
                               code="invalid_amount")
        payment = refund.payment
        if not payment.provider_transaction_id and not payment.provider_reference:
            raise ServiceError("Original payment lacks provider references.", code="provider_reference_missing", status_code=409)
        refund.approved_amount = amount
        refund.processed_by = staff
        refund.decided_at = timezone.now()
        refund.staff_notes = notes[:2000]
        try:
            result = PaystackService.refund(
                payment.provider_transaction_id or payment.provider_reference,
                amount_kobo=naira_to_kobo(amount), reason=f"Refund {refund.reference}")
        except PaystackError as exc:
            refund.status = Refund.Status.FAILED
            refund.provider_response = {"error": str(exc.detail)}
            refund.save()
            raise
        refund.provider_response = result
        refund.provider_refund_id = str(result.get("id", ""))[:80]
        provider_status = str(result.get("status", "")).lower()
        if provider_status in ("processed", "success", "paid"):
            cls._finalize_success(refund)
        else:
            refund.status = Refund.Status.PROCESSING
            refund.save()
        return refund

    @classmethod
    @transaction.atomic
    def reject(cls, refund, staff, notes=""):
        refund = Refund.objects.select_for_update().get(pk=refund.pk)
        if refund.status != Refund.Status.REQUESTED:
            raise ServiceError("Only requested refunds can be rejected.", code="invalid_refund_state", status_code=409)
        refund.status = Refund.Status.REJECTED
        refund.processed_by = staff
        refund.decided_at = timezone.now()
        refund.staff_notes = notes[:2000]
        refund.save()
        order = refund.order
        if order.status == Order.Status.REFUND_REQUESTED:
            OrderService.transition(order, Order.Status.PROCESSING if order.paid_at else order.status,
                                    actor=staff, note=f"Refund {refund.reference} rejected")
        from services.notification_service import NotificationService
        transaction.on_commit(lambda: NotificationService.refund_rejected(refund))
        return refund

    @classmethod
    @transaction.atomic
    def check_provider_status(cls, refund):
        """Poll Paystack for the final refund outcome (never guess success)."""
        from apps.payments.paystack import PaystackError, PaystackService
        refund = Refund.objects.select_for_update().select_related("order", "payment").get(pk=refund.pk)
        if refund.status not in (Refund.Status.PROCESSING, Refund.Status.APPROVED):
            return refund
        if not refund.provider_refund_id:
            return refund
        try:
            data = PaystackService._request("GET", f"/refund/{refund.provider_refund_id}")
        except PaystackError:
            return refund
        result = data.get("data") or {}
        refund.provider_response = result
        status = str(result.get("status", "")).lower()
        if status in ("processed", "success", "paid"):
            cls._finalize_success(refund)
        elif status in ("failed", "abandoned"):
            refund.status = Refund.Status.FAILED
            refund.save()
        else:
            refund.save()
        return refund

    @classmethod
    def _finalize_success(cls, refund):
        """Provider-confirmed refund: update money states and (optionally) stock."""
        refund.status = Refund.Status.SUCCESSFUL
        refund.processed_at = timezone.now()
        refund.save()
        order = refund.order
        payment = refund.payment
        total_refunded = order.total_refunded
        if total_refunded >= order.total_amount:
            payment.status = Payment.Status.REFUNDED
            OrderService.transition(order, Order.Status.REFUNDED, actor=refund.processed_by,
                                    note=f"Fully refunded via {refund.reference}")
        else:
            payment.status = Payment.Status.PARTIALLY_REFUNDED
            if order.status != Order.Status.PARTIALLY_REFUNDED:
                OrderService.transition(order, Order.Status.PARTIALLY_REFUNDED, actor=refund.processed_by,
                                        note=f"Partial refund via {refund.reference}")
            order.payment_status = Order.PaymentStatus.PARTIALLY_REFUNDED
            order.save(update_fields=["payment_status", "updated_at"])
        payment.save(update_fields=["status", "updated_at"])
        if refund.restock_items:
            from apps.inventory.services import InventoryService
            for item in order.items.select_related("variation"):
                inventory = InventoryService.resolve_inventory(item.product, item.variation)
                if inventory:
                    InventoryService.restore(inventory, item.quantity, order=order,
                                             performed_by=refund.processed_by,
                                             reason=f"Restock after refund {refund.reference}")
        from services.notification_service import NotificationService
        transaction.on_commit(lambda: NotificationService.refund_processed(refund))
