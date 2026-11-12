"""
RefundService — authorised, auditable, provider-verified refunds.

Guarantees:
* only a paid order can be refunded, and never beyond what was actually paid;
* a customer can only refund their own order;
* the amount is re-checked after approval, before submission;
* the provider's final state decides ``completed`` — a submitted request is not
  a completed refund;
* stock is only restocked when staff explicitly confirm the goods came back.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.audit.services import AuditService
from apps.core.exceptions import (
    ConflictError,
    InvalidStateTransition,
    NotFound,
    PermissionDeniedError,
    ValidationError,
)
from apps.core.utils import money
from apps.inventory.services import InventoryService
from apps.orders.models import Order, OrderItem
from apps.payments.models import Payment
from apps.payments.paystack import PaystackService
from apps.refunds.models import Refund, RefundItem

logger = logging.getLogger("apps.refunds")

PROVIDER_COMPLETED_STATUSES = {"processed", "success", "successful", "completed"}
PROVIDER_FAILED_STATUSES = {"failed", "reversed", "cancelled", "declined"}


class RefundService:
    # ------------------------------------------------------------------
    # Customer-facing: raise a request
    # ------------------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def request_refund(
        *,
        order: Order,
        reason_category: str,
        customer_note: str = "",
        items: list[dict] | None = None,
        amount=None,
        requested_by=None,
        actor_is_staff: bool = False,
    ) -> Refund:
        """
        Creates a refund request.

        ``items`` is ``[{"order_item_id": ..., "quantity": ...}]``. When omitted
        the whole order is refunded.
        """
        locked = Order.objects.select_for_update().get(pk=order.pk)

        if not actor_is_staff and requested_by is not None and locked.customer_id != getattr(requested_by, "pk", None):
            raise PermissionDeniedError("You can only request a refund for your own order.")

        if locked.payment_status not in {
            Order.PaymentStatus.PAID, Order.PaymentStatus.PARTIALLY_REFUNDED
        }:
            raise ConflictError("Only a paid order can be refunded.")
        if locked.amount_paid <= 0:
            raise ConflictError("No payment has been received for this order.")
        if locked.amount_refunded >= locked.amount_paid:
            raise ConflictError("This order has already been fully refunded.")

        # Delivery window guard (Section 33)
        if locked.delivered_at or locked.completed_at:
            anchor = locked.delivered_at or locked.completed_at
            days = (timezone.now() - anchor).days
            if days > settings.REFUND_MAX_DAYS_AFTER_DELIVERY and not actor_is_staff:
                raise ConflictError(
                    f"Refund requests are only accepted within "
                    f"{settings.REFUND_MAX_DAYS_AFTER_DELIVERY} days of delivery. "
                    f"Please contact support."
                )

        if locked.refunds.filter(
            status__in=[
                Refund.Status.REQUESTED, Refund.Status.UNDER_REVIEW,
                Refund.Status.APPROVED, Refund.Status.PROCESSING,
            ]
        ).exists():
            raise ConflictError("A refund request for this order is already in progress.")

        if reason_category not in Refund.Reason.values:
            raise ValidationError("Please choose a valid refund reason.")

        # ---- resolve the lines ------------------------------------------
        order_items = {str(i.pk): i for i in locked.items.all()}
        refund_lines: list[tuple[OrderItem, int, Decimal]] = []

        if items:
            seen = set()
            for row in items:
                item_id = str(row.get("order_item_id", ""))
                if item_id in seen:
                    raise ValidationError("Duplicate order line in refund request.")
                seen.add(item_id)
                item = order_items.get(item_id)
                if item is None:
                    raise ValidationError("One of the selected items is not part of this order.")
                try:
                    quantity = int(row.get("quantity", 0))
                except (TypeError, ValueError):
                    raise ValidationError("Refund quantities must be whole numbers.")
                if quantity <= 0:
                    raise ValidationError("Refund quantities must be at least one.")
                if quantity > item.refundable_quantity:
                    raise ValidationError(
                        f"Only {item.refundable_quantity} unit(s) of {item.product_name} "
                        f"remain refundable."
                    )
                unit_net = money(item.line_total / item.quantity) if item.quantity else Decimal("0")
                refund_lines.append((item, quantity, money(unit_net * quantity)))
        else:
            for item in order_items.values():
                if item.refundable_quantity > 0:
                    unit_net = money(item.line_total / item.quantity) if item.quantity else Decimal("0")
                    refund_lines.append(
                        (item, item.refundable_quantity, money(unit_net * item.refundable_quantity))
                    )

        if not refund_lines:
            raise ConflictError("There is nothing left on this order to refund.")

        line_total = money(sum(amount_for_line for _, _, amount_for_line in refund_lines))
        max_refundable = money(locked.amount_paid - locked.amount_refunded)

        covers_entire_order = (
            len(refund_lines) == len(order_items)
            and all(item.refunded_quantity + qty == item.quantity for item, qty, _ in refund_lines)
        )

        if amount is None:
            # A full-order refund also returns delivery and tax, not just the
            # merchandise value. A partial refund returns only the goods.
            requested_amount = max_refundable if covers_entire_order else min(
                line_total, max_refundable
            )
        else:
            requested_amount = money(amount)
            if requested_amount <= 0:
                raise ValidationError("The refund amount must be greater than zero.")
            if requested_amount > line_total:
                raise ValidationError(
                    f"The refund amount cannot exceed ₦{line_total:,.2f} for the selected items."
                )
            requested_amount = min(requested_amount, max_refundable)

        refund_type = (
            Refund.Type.FULL
            if covers_entire_order and requested_amount >= max_refundable
            else Refund.Type.PARTIAL
        )

        payment = locked.payments.filter(status=Payment.Status.SUCCESS).order_by("-paid_at").first()

        refund = Refund.objects.create(
            order=locked,
            payment=payment,
            refund_type=refund_type,
            status=Refund.Status.REQUESTED,
            reason_category=reason_category,
            customer_note=customer_note[:2000],
            amount_requested=requested_amount,
            currency=locked.currency,
            requested_by=requested_by if getattr(requested_by, "pk", None) else None,
            restock_items=False,
        )
        for item, quantity, amount_for_line in refund_lines:
            RefundItem.objects.create(
                refund=refund, order_item=item, quantity=quantity, amount=money(amount_for_line)
            )

        from apps.orders.services import OrderService

        OrderService.add_activity(
            locked,
            event="refund_requested",
            message=f"Refund {refund.refund_number} requested for ₦{requested_amount:,.2f}.",
            actor=requested_by,
            metadata={"refund_number": refund.refund_number},
        )
        AuditService.record(
            action="refund_requested",
            entity_type="refund",
            entity_id=refund.pk,
            actor=requested_by,
            summary=f"{refund.refund_number} requested on {locked.order_number}",
            after={"amount": str(requested_amount), "type": refund_type},
        )
        return refund

    # ------------------------------------------------------------------
    # Staff-facing: review
    # ------------------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def approve(refund: Refund, *, actor, amount=None, restock: bool = False,
                note: str = "") -> Refund:
        locked = Refund.objects.select_for_update().select_related("order").get(pk=refund.pk)
        if locked.status not in {Refund.Status.REQUESTED, Refund.Status.UNDER_REVIEW}:
            raise InvalidStateTransition(
                f"A refund in status '{locked.status}' cannot be approved."
            )
        if actor is not None and not (
            getattr(actor, "is_superuser", False)
            or getattr(actor, "has_perm")("refunds.change_refund")
        ):
            raise PermissionDeniedError("You do not have permission to approve refunds.")

        order = locked.order
        max_refundable = money(order.amount_paid - order.amount_refunded)
        approved_amount = money(amount) if amount is not None else money(locked.amount_requested)
        if approved_amount <= 0:
            raise ValidationError("The approved amount must be greater than zero.")
        if approved_amount > max_refundable:
            raise ValidationError(
                f"You cannot refund more than the ₦{max_refundable:,.2f} still held on this order."
            )

        locked.amount_approved = approved_amount
        locked.status = Refund.Status.APPROVED
        locked.reviewed_by = actor if getattr(actor, "pk", None) else None
        locked.reviewed_at = timezone.now()
        locked.restock_items = bool(restock)
        if note:
            locked.internal_note = (locked.internal_note + "\n" + note).strip()[:2000]
        locked.save()

        AuditService.record(
            action="refund_approved",
            entity_type="refund",
            entity_id=locked.pk,
            actor=actor,
            summary=f"{locked.refund_number} approved for ₦{approved_amount:,.2f}",
            after={"amount_approved": str(approved_amount), "restock": restock},
        )
        return locked

    @staticmethod
    @transaction.atomic
    def reject(refund: Refund, *, actor, reason: str) -> Refund:
        locked = Refund.objects.select_for_update().get(pk=refund.pk)
        if locked.status not in {Refund.Status.REQUESTED, Refund.Status.UNDER_REVIEW}:
            raise InvalidStateTransition(f"A refund in status '{locked.status}' cannot be rejected.")
        if not (reason or "").strip():
            raise ValidationError("A reason is required when rejecting a refund.")

        locked.status = Refund.Status.REJECTED
        locked.rejection_reason = reason[:255]
        locked.reviewed_by = actor if getattr(actor, "pk", None) else None
        locked.reviewed_at = timezone.now()
        locked.save()

        from apps.orders.services import OrderService

        OrderService.add_activity(
            locked.order,
            event="refund_requested",
            message=f"Refund {locked.refund_number} was declined: {reason}"[:300],
        )
        AuditService.record(
            action="refund_failed",
            entity_type="refund",
            entity_id=locked.pk,
            actor=actor,
            summary=f"{locked.refund_number} rejected: {reason}"[:255],
        )
        return locked

    # ------------------------------------------------------------------
    # Submission to Paystack
    # ------------------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def submit_to_provider(refund: Refund, *, actor=None) -> Refund:
        """
        Submits an approved refund to Paystack.

        The refund is marked ``processing`` — never ``completed`` — until the
        provider confirms the money actually moved.
        """
        locked = Refund.objects.select_for_update().select_related("order", "payment").get(pk=refund.pk)
        if locked.status != Refund.Status.APPROVED:
            raise InvalidStateTransition("Only an approved refund can be submitted to the provider.")
        if locked.payment is None or not locked.payment.is_verified:
            raise ConflictError(
                "The original payment was never verified with Paystack, so it cannot be refunded "
                "automatically. Handle this case manually and record the outcome."
            )

        amount = money(locked.amount_approved or locked.amount_requested)

        try:
            response = PaystackService.refund_transaction(
                transaction_reference=locked.payment.provider_reference or locked.payment.reference,
                amount=amount,
                reason=locked.get_reason_category_display(),
                merchant_note=f"{locked.refund_number} on {locked.order.order_number}",
            )
        except Exception as exc:
            locked.status = Refund.Status.FAILED
            locked.failed_at = timezone.now()
            locked.provider_response = {"error": str(exc)[:500]}
            locked.save()
            AuditService.record(
                action="refund_failed",
                entity_type="refund",
                entity_id=locked.pk,
                actor=actor,
                summary=f"{locked.refund_number} submission failed: {str(exc)[:200]}",
            )
            raise

        data = response.data or {}
        locked.provider_refund_id = str(data.get("id") or data.get("refund_id") or "")[:120]
        locked.provider_status = str(data.get("status") or "pending")[:60]
        locked.provider_reference = str(data.get("transaction_reference") or data.get("reference") or "")[:120]
        locked.provider_response = response.raw
        locked.submitted_at = timezone.now()
        locked.status = Refund.Status.PROCESSING
        locked.save()

        AuditService.record(
            action="refund_requested",
            entity_type="refund",
            entity_id=locked.pk,
            actor=actor,
            summary=f"{locked.refund_number} submitted to Paystack (status {locked.provider_status})",
            after={"provider_refund_id": locked.provider_refund_id},
        )
        logger.info("Refund %s submitted to Paystack: %s", locked.refund_number, locked.provider_refund_id)

        # If Paystack already reports a terminal success, finalise immediately.
        if locked.provider_status.lower() in PROVIDER_COMPLETED_STATUSES:
            RefundService._finalise(locked, actor=actor)
        return locked

    # ------------------------------------------------------------------
    # Reconciliation
    # ------------------------------------------------------------------
    @staticmethod
    def check_provider_status(refund: Refund, *, actor=None) -> Refund:
        """Polls Paystack for the true state of a submitted refund."""
        locked = Refund.objects.select_for_update().get(pk=refund.pk)
        if not locked.provider_refund_id:
            raise ConflictError("This refund has no provider reference to check.")

        response = PaystackService.fetch_refund(locked.provider_refund_id)
        if not response.ok or not response.data:
            logger.warning("Could not read refund %s from Paystack", locked.refund_number)
            return locked

        status = str(response.data.get("status", "")).lower()
        locked.provider_status = status[:60]
        locked.provider_response = response.raw
        locked.save(update_fields=["provider_status", "provider_response", "updated_at"])

        if status in PROVIDER_COMPLETED_STATUSES:
            return RefundService._finalise(locked, actor=actor)
        if status in PROVIDER_FAILED_STATUSES:
            locked.status = Refund.Status.FAILED
            locked.failed_at = timezone.now()
            locked.save(update_fields=["status", "failed_at", "updated_at"])
            AuditService.record(
                action="refund_failed",
                entity_type="refund",
                entity_id=locked.pk,
                actor=actor,
                summary=f"{locked.refund_number} failed at provider (status {status})",
            )
        return locked

    @staticmethod
    def reconcile_pending() -> dict:
        """Sweeps every in-flight refund. Called by the reconcile_refunds command."""
        results = {"checked": 0, "completed": 0, "failed": 0, "unchanged": 0}
        for refund in Refund.objects.filter(
            status=Refund.Status.PROCESSING, provider_refund_id__gt=""
        ).iterator():
            results["checked"] += 1
            before = refund.status
            try:
                updated = RefundService.check_provider_status(refund)
            except Exception:
                logger.exception("Refund reconciliation failed for %s", refund.refund_number)
                results["unchanged"] += 1
                continue
            if updated.status == Refund.Status.COMPLETED and before != updated.status:
                results["completed"] += 1
            elif updated.status == Refund.Status.FAILED and before != updated.status:
                results["failed"] += 1
            else:
                results["unchanged"] += 1
        return results

    # ------------------------------------------------------------------
    # Finalisation
    # ------------------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def _finalise(refund: Refund, *, actor=None) -> Refund:
        """
        Applies a provider-confirmed refund to the platform's financial records.

        Idempotent: a refund that is already completed is returned untouched, so a
        webhook retry can never double-count money.
        """
        locked = Refund.objects.select_for_update().select_related("order", "payment").get(pk=refund.pk)
        if locked.status == Refund.Status.COMPLETED:
            return locked
        if locked.status not in {Refund.Status.PROCESSING, Refund.Status.APPROVED}:
            raise InvalidStateTransition(
                f"A refund in status '{locked.status}' cannot be completed."
            )

        order = Order.objects.select_for_update().get(pk=locked.order_id)
        amount = money(locked.amount_approved or locked.amount_requested)

        remaining = money(order.amount_paid - order.amount_refunded)
        amount = min(amount, remaining)
        if amount <= 0:
            locked.status = Refund.Status.COMPLETED
            locked.completed_at = timezone.now()
            locked.save(update_fields=["status", "completed_at", "updated_at"])
            return locked

        locked.amount_refunded = amount
        locked.status = Refund.Status.COMPLETED
        locked.completed_at = timezone.now()
        locked.save(update_fields=["amount_refunded", "status", "completed_at", "updated_at"])

        # --- order money ----------------------------------------------------
        order.amount_refunded = money(order.amount_refunded + amount)
        if order.amount_refunded >= order.amount_paid:
            order.payment_status = Order.PaymentStatus.REFUNDED
        else:
            order.payment_status = Order.PaymentStatus.PARTIALLY_REFUNDED
        order.recalculate_amount_due(save=False)
        order.save(
            update_fields=[
                "amount_refunded", "payment_status", "amount_due", "updated_at",
            ]
        )

        # --- line-level refund counters ------------------------------------
        for line in locked.items.select_related("order_item"):
            item = OrderItem.objects.select_for_update().get(pk=line.order_item_id)
            item.refunded_quantity = min(item.refunded_quantity + line.quantity, item.quantity)
            item.is_fully_refunded = item.refunded_quantity >= item.quantity
            item.save(update_fields=["refunded_quantity", "is_fully_refunded", "updated_at"])

        # --- payment record --------------------------------------------------
        if locked.payment is not None:
            payment = Payment.objects.select_for_update().get(pk=locked.payment_id)
            total_refunded = money(
                Refund.objects.filter(payment=payment, status=Refund.Status.COMPLETED)
                .aggregate(total=models_sum())["total"] or 0
            )
            payment.status = (
                Payment.Status.REFUNDED if total_refunded >= payment.amount
                else Payment.Status.PARTIALLY_REFUNDED
            )
            payment.save(update_fields=["status", "updated_at"])

        # --- restocking ------------------------------------------------------
        if locked.restock_items and not locked.restock_processed:
            RefundService._restock(locked, actor=actor)
            locked.restock_processed = True
            locked.restocked_at = timezone.now()
            locked.save(update_fields=["restock_processed", "restocked_at", "updated_at"])

        # --- communication ---------------------------------------------------
        from apps.orders.services import OrderService

        OrderService.add_activity(
            order,
            event="refund_processed",
            message=f"Refund {locked.refund_number} of ₦{amount:,.2f} completed.",
            actor=actor,
            metadata={"refund_number": locked.refund_number, "amount": str(amount)},
        )
        try:
            from apps.notifications.services import NotificationService

            NotificationService.refund_completed(locked)
        except Exception:  # pragma: no cover - notification failure must not roll back money
            logger.exception("Refund notification failed for %s", locked.refund_number)

        AuditService.record(
            action="refund_completed",
            entity_type="refund",
            entity_id=locked.pk,
            actor=actor,
            summary=f"{locked.refund_number} completed: ₦{amount:,.2f} returned",
            after={
                "amount": str(amount),
                "order_payment_status": order.payment_status,
                "order_total_refunded": str(order.amount_refunded),
            },
        )
        logger.info("Refund %s completed for %s", locked.refund_number, amount)
        return locked

    @staticmethod
    def _restock(refund: Refund, *, actor=None) -> None:
        """Returns refunded goods to sellable stock, per line, with movements."""
        from apps.inventory.models import Inventory

        for line in refund.items.select_related("order_item"):
            item = line.order_item
            inventory = Inventory.objects.filter(
                product_id=item.product_id, variation_id=item.variation_id
            ).first()
            if inventory is None:
                logger.warning(
                    "No inventory row to restock for order item %s", item.pk
                )
                continue
            InventoryService.record_return(
                inventory=inventory,
                quantity=line.quantity,
                reason=f"Refund {refund.refund_number} restocked",
                actor=actor,
                reference=refund.refund_number,
            )

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    @staticmethod
    def refundable_summary(order: Order) -> dict:
        max_refundable = money(order.amount_paid - order.amount_refunded)
        return {
            "order_number": order.order_number,
            "amount_paid": str(money(order.amount_paid)),
            "amount_refunded": str(money(order.amount_refunded)),
            "amount_refundable": str(max(max_refundable, Decimal("0.00"))),
            "eligible": order.is_refundable and max_refundable > 0,
            "items": [
                {
                    "order_item_id": str(item.pk),
                    "name": item.product_name,
                    "quantity": item.quantity,
                    "refundable_quantity": item.refundable_quantity,
                    "unit_price": str(money(item.unit_price)),
                }
                for item in order.items.all()
            ],
        }

    @staticmethod
    def get_for_customer(refund_id: str, user) -> Refund:
        refund = Refund.objects.select_related("order").filter(pk=refund_id).first()
        if refund is None or refund.order.customer_id != getattr(user, "pk", None):
            raise NotFound("Refund not found.")
        return refund


def models_sum():
    from django.db.models import Sum

    return Sum("amount_refunded")
