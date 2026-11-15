"""NotificationService — orchestrates in-app notifications and transactional
emails with dedupe keys. Notification/email failure NEVER raises into the
calling business transaction."""
import logging

from django.conf import settings

logger = logging.getLogger("starmond.notifications")

STATUS_LABELS = {
    "processing": "being processed",
    "packed": "packed and ready for dispatch",
    "shipped": "on its way (dispatched)",
    "out_for_delivery": "out for delivery",
    "delivered": "delivered",
    "completed": "completed",
    "cancelled": "cancelled",
    "refund_requested": "under refund review",
    "partially_refunded": "partially refunded",
    "refunded": "refunded",
}


def _safe(fn):
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:
            logger.exception("Notification step failed: %s", fn.__name__)
            return None
    return wrapper


class NotificationService:
    # ---------------------------------------------------------------- account
    @staticmethod
    @_safe
    def send_email_verification(user, request=None):
        from apps.accounts.serializers import make_email_verify_token
        from apps.emails.services import EmailService
        token = make_email_verify_token(user)
        verify_url = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/verify-email.html?token={token}"
        EmailService.send("verify_email", user.email,
                          {"full_name": user.full_name, "verify_url": verify_url},
                          dedupe_key=f"verify_email:{user.pk}:{user.is_email_verified}")

    @staticmethod
    @_safe
    def send_password_reset(user, uid, token, request=None):
        from apps.emails.services import EmailService
        reset_url = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/reset-password.html?uid={uid}&token={token}"
        EmailService.send("password_reset", user.email,
                          {"full_name": user.full_name, "reset_url": reset_url},
                          dedupe_key=f"password_reset:{user.pk}:{token}")

    # ---------------------------------------------------------------- orders
    @staticmethod
    @_safe
    def order_created(order, request=None):
        from apps.emails.services import EmailService
        EmailService.send("order_received", order.contact_email, {
            "customer_name": order.contact_full_name, "reference": order.reference,
            "total": f"{order.total_amount:,.2f}",
            "expires_at": order.expires_at.strftime("%Y-%m-%d %H:%M") if order.expires_at else "-",
        }, related_order=order, dedupe_key=f"order_received:{order.reference}")
        NotificationService._in_app(order, "order", f"Order {order.reference} received",
                                    "Your order is awaiting payment.", f"/orders/{order.reference}/",
                                    f"order_created:{order.reference}")

    @staticmethod
    @_safe
    def payment_successful(order, payment):
        from apps.emails.services import EmailService
        items = [{
            "name": i.product_name, "variation": i.variation_label, "quantity": i.quantity,
            "line_total": f"{i.line_total:,.2f}",
        } for i in order.items.all()]
        EmailService.send("payment_successful", order.contact_email, {
            "customer_name": order.contact_full_name, "reference": order.reference,
            "amount": f"{payment.amount:,.2f}", "items": items,
            "subtotal": f"{order.subtotal_amount:,.2f}", "discount": f"{order.discount_amount:,.2f}",
            "shipping_fee": f"{order.shipping_fee:,.2f}", "total": f"{order.total_amount:,.2f}",
            "shipping_method": order.shipping_method_name, "estimate": order.shipping_estimate,
            "payment_reference": payment.reference,
        }, related_order=order, related_payment=payment,
            dedupe_key=f"payment_successful:{payment.reference}")
        NotificationService._in_app(order, "payment", f"Payment confirmed — {order.reference}",
                                    f"₦{payment.amount:,.2f} received. Your order is being prepared.",
                                    f"/orders/{order.reference}/", f"payment_ok:{payment.reference}")

    @staticmethod
    @_safe
    def payment_failed(order, payment):
        from apps.emails.services import EmailService
        EmailService.send("payment_failed", order.contact_email, {
            "customer_name": order.contact_full_name, "reference": order.reference,
            "reason": payment.failure_reason,
            "expires_at": order.expires_at.strftime("%Y-%m-%d %H:%M") if order.expires_at else "-",
        }, related_order=order, related_payment=payment,
            dedupe_key=f"payment_failed:{payment.reference}:{payment.attempts if hasattr(payment,'attempts') else payment.pk}")

    @staticmethod
    @_safe
    def order_cancelled(order, reason=""):
        from apps.emails.services import EmailService
        EmailService.send("order_cancelled", order.contact_email, {
            "customer_name": order.contact_full_name, "reference": order.reference, "reason": reason,
        }, related_order=order, dedupe_key=f"order_cancelled:{order.reference}")
        NotificationService._in_app(order, "order", f"Order {order.reference} cancelled", reason,
                                    f"/orders/{order.reference}/", f"order_cancelled:{order.reference}")

    @staticmethod
    @_safe
    def order_status_changed(order, new_status):
        from apps.emails.services import EmailService
        label = STATUS_LABELS.get(new_status, new_status.replace("_", " "))
        EmailService.send("order_status", order.contact_email, {
            "customer_name": order.contact_full_name, "reference": order.reference,
            "status_label": label, "tracking": order.tracking_reference, "note": "",
        }, related_order=order, dedupe_key=f"order_status:{order.reference}:{new_status}")
        NotificationService._in_app(order, "order", f"Order {order.reference}: {label}", "",
                                    f"/orders/{order.reference}/", f"status:{order.reference}:{new_status}")

    # ---------------------------------------------------------------- refunds
    @staticmethod
    @_safe
    def refund_requested(refund):
        from apps.emails.services import EmailService
        order = refund.order
        EmailService.send("refund_requested", order.contact_email, {
            "customer_name": order.contact_full_name, "refund_reference": refund.reference,
            "order_reference": order.reference, "amount": f"{refund.requested_amount:,.2f}",
        }, related_order=order, dedupe_key=f"refund_requested:{refund.reference}")

    @staticmethod
    @_safe
    def refund_processed(refund):
        from apps.emails.services import EmailService
        order = refund.order
        EmailService.send("refund_processed", order.contact_email, {
            "customer_name": order.contact_full_name, "refund_reference": refund.reference,
            "order_reference": order.reference, "amount": f"{refund.approved_amount:,.2f}",
        }, related_order=order, dedupe_key=f"refund_processed:{refund.reference}")
        NotificationService._in_app(order, "refund", f"Refund {refund.reference} processed", "",
                                    f"/orders/{order.reference}/", f"refund_ok:{refund.reference}")

    @staticmethod
    @_safe
    def refund_rejected(refund):
        from apps.emails.services import EmailService
        order = refund.order
        EmailService.send("refund_rejected", order.contact_email, {
            "customer_name": order.contact_full_name, "refund_reference": refund.reference,
            "order_reference": order.reference, "note": refund.staff_notes,
        }, related_order=order, dedupe_key=f"refund_rejected:{refund.reference}")

    # ------------------------------------------------------------ engagement
    @staticmethod
    @_safe
    def newsletter_welcome(email):
        from apps.emails.services import EmailService
        EmailService.send("newsletter_welcome", email, {}, dedupe_key=f"newsletter_welcome:{email}")

    @staticmethod
    @_safe
    def enquiry_ack(enquiry):
        from apps.emails.services import EmailService
        EmailService.send("enquiry_ack", enquiry.email, {
            "full_name": enquiry.full_name, "email": enquiry.email, "message": enquiry.message[:800],
        }, dedupe_key=f"enquiry_ack:{enquiry.pk}")

    # --------------------------------------------------------------- helpers
    @staticmethod
    @_safe
    def _in_app(order, kind, title, body, link, dedupe_key):
        from apps.notifications.models import Notification
        if order.customer_id:
            Notification.objects.get_or_create(
                dedupe_key=dedupe_key,
                defaults={"user_id": order.customer_id, "kind": kind, "title": title[:180],
                          "body": body[:2000], "link": link[:300]})
