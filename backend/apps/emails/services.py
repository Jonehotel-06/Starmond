"""EmailService — provider-independent transactional email.

Provider is configured via EMAIL_BACKEND (SMTP, Brevo, SES, Mailgun,
SendGrid, Postmark...). Sending is asynchronous via Celery with bounded
retries; every attempt is logged in EmailLog; dedupe_key guarantees a
transactional email is never sent twice (webhook retries included).
"""
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import IntegrityError, transaction
from django.template.loader import render_to_string
from django.utils import timezone

from .models import EmailLog

logger = logging.getLogger("starmond.emails")

SUBJECTS = {
    "verify_email": "Confirm your STARMOND account",
    "password_reset": "Reset your STARMOND password",
    "order_received": "We received your order {reference}",
    "payment_successful": "Payment received — Order {reference}",
    "payment_failed": "Payment issue with order {reference}",
    "order_cancelled": "Order {reference} cancelled",
    "order_status": "Update on your order {reference}",
    "refund_requested": "Refund request received — {reference}",
    "refund_processed": "Refund processed — {reference}",
    "refund_rejected": "Refund request update — {reference}",
    "newsletter_welcome": "Welcome to the STARMOND newsletter",
    "enquiry_ack": "We received your enquiry",
    "low_stock_alert": "Low stock alert: {product}",
}


class EmailService:
    @classmethod
    def send(cls, template_key, recipient, context, *, related_order=None, related_payment=None, dedupe_key=None):
        """Queue a transactional email. Returns the EmailLog (or None when a
        duplicate was skipped). NEVER raises for delivery problems."""
        subject_template = SUBJECTS.get(template_key, "Message from STARMOND TECHNOLOGY LIMITED")
        try:
            subject = subject_template.format(**context)
        except (KeyError, IndexError):
            subject = subject_template
        full_context = {**context, "subject": subject, "business_name": "STARMOND TECHNOLOGY LIMITED",
                        "frontend_url": settings.FRONTEND_BASE_URL, "support_email": settings.DEFAULT_FROM_EMAIL}
        try:
            with transaction.atomic():
                log = EmailLog.objects.create(
                    recipient=recipient, template_key=template_key, subject=subject[:255],
                    dedupe_key=(dedupe_key or None) and dedupe_key[:160],
                    related_order=related_order, related_payment=related_payment,
                    context_snapshot={k: str(v)[:400] for k, v in context.items()},
                    status=EmailLog.Status.QUEUED,
                )
        except IntegrityError:
            logger.info("Duplicate email skipped (dedupe_key=%s)", dedupe_key)
            return None
        cls._dispatch(log.pk, full_context)
        return log

    @classmethod
    def _dispatch(cls, log_id, full_context=None):
        """Send via Celery when available; fall back to sync in eager/dev mode."""
        try:
            from .tasks import send_email_task
            send_email_task.delay(log_id)
        except Exception:
            logger.warning("Celery unavailable — sending email %s synchronously", log_id)
            cls.deliver(log_id)

    @classmethod
    def deliver(cls, log_id):
        """Actual SMTP/provider delivery. Called by the Celery task."""
        log = EmailLog.objects.select_related("related_order").filter(pk=log_id).first()
        if not log or log.status == EmailLog.Status.SENT:
            return log
        context = dict(log.context_snapshot)
        try:
            html_body = render_to_string(f"emails/{log.template_key}.html", context)
        except Exception:
            html_body = render_to_string("emails/base_fallback.html", context)
        try:
            text_body = render_to_string(f"emails/{log.template_key}.txt", context)
        except Exception:
            text_body = render_to_string("emails/base_fallback.txt", context)
        message = EmailMultiAlternatives(
            subject=log.subject, body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL, to=[log.recipient])
        message.attach_alternative(html_body, "text/html")
        log.attempts += 1
        try:
            message.send(fail_silently=False)
            log.status = EmailLog.Status.SENT
            log.sent_at = timezone.now()
            log.last_error = ""
        except Exception as exc:
            log.status = EmailLog.Status.FAILED
            log.last_error = str(exc)[:500]
            logger.error("Email %s failed (attempt %s): %s", log.pk, log.attempts, exc)
        log.save(update_fields=["status", "attempts", "sent_at", "last_error", "updated_at"])
        return log
