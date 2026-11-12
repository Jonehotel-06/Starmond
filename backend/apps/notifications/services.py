"""
NotificationService — in-app notifications plus branded transactional email.

Every business event maps to exactly one notification. Calls are idempotent per
order/event so a retried Paystack webhook cannot spam the customer, and any
failure here is swallowed: a notification must never roll back a payment.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.utils import timezone

from apps.emails.services import EmailService
from apps.notifications.models import Enquiry, NewsletterSubscriber, Notification

logger = logging.getLogger("apps.notifications")


class NotificationService:
    # ------------------------------------------------------------------
    # Core
    # ------------------------------------------------------------------
    @staticmethod
    def push(*, user, notification_type: str, title: str, message: str,
             action_url: str = "", dedupe_key: str = "", metadata: dict | None = None):
        """Creates one in-app notification, skipping exact duplicates."""
        if user is None or not getattr(user, "pk", None):
            return None
        if dedupe_key and Notification.objects.filter(user=user, dedupe_key=dedupe_key).exists():
            return None
        try:
            return Notification.objects.create(
                user=user,
                notification_type=notification_type,
                title=title[:180],
                message=message,
                action_url=action_url[:300],
                dedupe_key=dedupe_key[:150],
                metadata=metadata,
            )
        except Exception:  # pragma: no cover
            logger.exception("Failed to create notification for %s", user.pk)
            return None

    @staticmethod
    def _email(**kwargs):
        try:
            return EmailService.send(**kwargs)
        except Exception:  # pragma: no cover - email must never break a flow
            logger.exception("Notification email failed: %s", kwargs.get("template"))
            return None

    # ------------------------------------------------------------------
    # Order lifecycle
    # ------------------------------------------------------------------
    @staticmethod
    def order_placed(order) -> None:
        """Order acknowledgement. Not a receipt — no payment has been taken yet."""
        email = order.customer_email
        if not email:
            return
        order_url = f"{settings.FRONTEND_URL}/orders/{order.order_number}"
        if order.customer_id:
            NotificationService.push(
                user=order.customer,
                notification_type=Notification.Type.ORDER,
                title=f"Order {order.order_number} received",
                message=(
                    f"Your order of ₦{order.grand_total:,.2f} has been created. "
                    f"Complete payment before {order.expires_at:%d %b %Y %H:%M} to keep it."
                ),
                action_url=order_url,
                dedupe_key=f"order_placed:{order.order_number}",
            )
        log = NotificationService._email(
            template="order_placed",
            to_email=email,
            to_name=order.customer_name,
            subject=f"Order {order.order_number} received — {settings.BUSINESS_NAME}",
            context={
                "order": order,
                "items": list(order.items.all()),
                "recipient_name": order.customer_name,
                "pay_url": f"{settings.FRONTEND_URL}/orders/{order.order_number}/pay",
            },
            user=order.customer if order.customer_id else None,
            related_type="order",
            related_id=order.order_number,
        )
        if log is not None and log.status == log.Status.SENT:
            EmailService.mark_dedupe(log, f"order_placed:{order.order_number}")

    @staticmethod
    def payment_received(order, payment) -> None:
        """The receipt. Sent once per order, deduped on the order number."""
        email = order.customer_email
        order_url = f"{settings.FRONTEND_URL}/orders/{order.order_number}"
        receipt_number = f"RCP-{order.order_number}"
        if order.customer_id:
            NotificationService.push(
                user=order.customer,
                notification_type=Notification.Type.PAYMENT,
                title=f"Payment confirmed — {order.order_number}",
                message=f"We received ₦{order.amount_paid:,.2f}. Your order is now being prepared.",
                action_url=order_url,
                dedupe_key=f"payment_received:{order.order_number}",
            )
        if not email:
            return
        log = NotificationService._email(
            template="payment_received",
            to_email=email,
            to_name=order.customer_name,
            subject=f"Payment confirmed for order {order.order_number} — {settings.BUSINESS_NAME}",
            context={
                "order": order,
                "payment": payment,
                "receipt_number": receipt_number,
                "recipient_name": order.customer_name,
                "order_url": order_url,
            },
            user=order.customer if order.customer_id else None,
            related_type="order",
            related_id=order.order_number,
        )
        if log is not None and log.status == log.Status.SENT:
            EmailService.mark_dedupe(log, f"payment_received:{order.order_number}")

    @staticmethod
    def order_status_changed(order, previous_status: str = "") -> None:
        """Status-transition email, deduped on (order, status)."""
        milestones = {"dispatched", "out_for_delivery", "delivered", "completed", "cancelled"}
        if order.status not in milestones:
            return
        email = order.customer_email
        order_url = f"{settings.FRONTEND_URL}/orders/{order.order_number}"
        shipment = order.shipments.order_by("-created_at").first()
        tracking = shipment.tracking_reference if shipment else ""
        note = {
            "dispatched": "Your order has left our warehouse and is on its way.",
            "out_for_delivery": "Your order is with the delivery rider today.",
            "delivered": "Your order has been delivered. Thank you for shopping with us.",
            "completed": "Your order is complete. We would love a review of your items.",
            "cancelled": f"Your order was cancelled. {order.cancellation_reason}".strip(),
        }.get(order.status, f"Your order is now {order.get_status_display()}.")

        if order.customer_id:
            NotificationService.push(
                user=order.customer,
                notification_type=Notification.Type.SHIPPING
                if order.status in {"dispatched", "out_for_delivery", "delivered"}
                else Notification.Type.ORDER,
                title=f"Order {order.order_number}: {order.get_status_display()}",
                message=note,
                action_url=order_url,
                dedupe_key=f"status:{order.order_number}:{order.status}",
            )
        if not email:
            return
        log = NotificationService._email(
            template="order_status_changed",
            to_email=email,
            to_name=order.customer_name,
            subject=f"Order {order.order_number}: {order.get_status_display()} — {settings.BUSINESS_NAME}",
            context={
                "order": order,
                "status_label": order.get_status_display(),
                "note": note,
                "tracking_reference": tracking,
                "recipient_name": order.customer_name,
                "order_url": order_url,
            },
            user=order.customer if order.customer_id else None,
            related_type="order",
            related_id=order.order_number,
        )
        if log is not None and log.status == log.Status.SENT:
            EmailService.mark_dedupe(log, f"status:{order.order_number}:{order.status}")

    @staticmethod
    def refund_completed(refund) -> None:
        order = refund.order
        email = order.customer_email
        order_url = f"{settings.FRONTEND_URL}/orders/{order.order_number}"
        if order.customer_id:
            NotificationService.push(
                user=order.customer,
                notification_type=Notification.Type.REFUND,
                title=f"Refund processed — {refund.refund_number}",
                message=f"₦{refund.amount_refunded:,.2f} has been returned for order {order.order_number}.",
                action_url=order_url,
                dedupe_key=f"refund:{refund.refund_number}",
            )
        if not email:
            return
        log = NotificationService._email(
            template="refund_completed",
            to_email=email,
            to_name=order.customer_name,
            subject=f"Refund processed — {refund.refund_number}",
            context={
                "refund": refund,
                "order_number": order.order_number,
                "amount": f"{refund.amount_refunded:,.2f}",
                "recipient_name": order.customer_name,
            },
            user=order.customer if order.customer_id else None,
            related_type="refund",
            related_id=refund.refund_number,
        )
        if log is not None and log.status == log.Status.SENT:
            EmailService.mark_dedupe(log, f"refund:{refund.refund_number}")

    # ------------------------------------------------------------------
    # Account
    # ------------------------------------------------------------------
    @staticmethod
    def welcome(user, verify_url: str) -> None:
        NotificationService.push(
            user=user,
            notification_type=Notification.Type.ACCOUNT,
            title="Welcome to STARMOND",
            message="Your account is ready. Verify your email to receive receipts and order updates.",
            dedupe_key=f"welcome:{user.pk}",
        )
        NotificationService._email(
            template="welcome",
            to_email=user.email,
            to_name=user.display_name,
            subject=f"Welcome to {settings.BUSINESS_NAME}",
            context={"recipient_name": user.display_name, "verify_url": verify_url},
            user=user,
            category="transactional",
            related_type="user",
            related_id=str(user.pk),
        )

    @staticmethod
    def email_verification(user, verify_url: str, expires_hours: int = 24) -> None:
        NotificationService._email(
            template="verify_email",
            to_email=user.email,
            to_name=user.display_name,
            subject=f"Verify your email address — {settings.BUSINESS_NAME}",
            context={
                "recipient_name": user.display_name,
                "verify_url": verify_url,
                "expires_hours": expires_hours,
            },
            user=user,
            category="security",
            related_type="user",
            related_id=str(user.pk),
        )

    @staticmethod
    def password_reset(user, reset_url: str, expires_hours: int = 2) -> None:
        NotificationService._email(
            template="password_reset",
            to_email=user.email,
            to_name=user.display_name,
            subject=f"Reset your password — {settings.BUSINESS_NAME}",
            context={
                "recipient_name": user.display_name,
                "reset_url": reset_url,
                "expires_hours": expires_hours,
            },
            user=user,
            category="security",
            related_type="user",
            related_id=str(user.pk),
        )

    # ------------------------------------------------------------------
    # Inbox
    # ------------------------------------------------------------------
    @staticmethod
    def record_enquiry(*, name: str, email: str, subject: str, message: str,
                       phone: str = "", order_number: str = "", user=None,
                       source_ip: str | None = None) -> Enquiry:
        enquiry = Enquiry.objects.create(
            name=name[:150],
            email=email.lower(),
            phone=phone[:16],
            subject=subject[:200],
            message=message[:5000],
            user=user if getattr(user, "pk", None) else None,
            order_number=order_number[:32],
            source_ip=source_ip,
        )
        NotificationService._email(
            template="contact_enquiry",
            to_email=settings.DEFAULT_FROM_EMAIL,
            to_name="Support team",
            subject=f"New enquiry: {enquiry.subject}",
            context={"enquiry": enquiry},
            category="system",
            related_type="enquiry",
            related_id=str(enquiry.pk),
        )
        return enquiry

    @staticmethod
    def subscribe_newsletter(*, email: str, name: str = "", source: str = "") -> NewsletterSubscriber:
        subscriber, created = NewsletterSubscriber.objects.get_or_create(
            email=email.lower(),
            defaults={"name": name[:150], "source": source[:60], "confirmed_at": timezone.now()},
        )
        if not created and not subscriber.is_active:
            subscriber.is_active = True
            subscriber.unsubscribed_at = None
            subscriber.save(update_fields=["is_active", "unsubscribed_at", "updated_at"])
        return subscriber

    @staticmethod
    def mark_all_read(user) -> int:
        return Notification.objects.filter(user=user, is_read=False).update(
            is_read=True, read_at=timezone.now()
        )
