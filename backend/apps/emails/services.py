"""
EmailService — branded transactional email with a durable log.

Design rules (Section 23):

* an email failure never invalidates a successful payment or order — every
  caller wraps this in a try/except and this module never raises on delivery
  problems (``EMAIL_FAIL_SILENTLY``);
* the same transactional message is never sent twice for the same business
  event, so a retried webhook cannot spam the customer;
* every attempt is recorded in ``EmailLog`` for support and auditing.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template import TemplateDoesNotExist
from django.template.loader import render_to_string
from django.utils import timezone

from apps.emails.models import EmailLog

logger = logging.getLogger("apps.emails")

BRAND = "STARMOND TECHNOLOGY LIMITED"


class EmailService:
    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @staticmethod
    def send(
        *,
        template: str,
        to_email: str,
        subject: str,
        context: dict | None = None,
        to_name: str = "",
        category: str = EmailLog.Category.TRANSACTIONAL,
        user=None,
        related_type: str = "",
        related_id: str = "",
        dedupe_key: str | None = None,
        from_email: str | None = None,
    ) -> EmailLog:
        """
        Renders and sends one email, returning its log row.

        ``dedupe_key`` makes the call idempotent for a given business event.
        """
        context = dict(context or {})
        context.setdefault("business_name", settings.BUSINESS_NAME)
        context.setdefault("site_url", settings.SITE_URL)
        context.setdefault("frontend_url", settings.FRONTEND_URL)
        context.setdefault("support_email", settings.DEFAULT_FROM_EMAIL)
        context.setdefault("recipient_name", to_name or to_email.split("@")[0])

        if dedupe_key and EmailService._already_sent(template, to_email, dedupe_key):
            log = EmailLog.objects.create(
                to_email=to_email,
                to_name=to_name,
                subject=subject,
                template=template,
                category=category,
                status=EmailLog.Status.SKIPPED,
                user=user if getattr(user, "pk", None) else None,
                related_type=related_type,
                related_id=str(related_id),
                context_keys=sorted(context.keys()),
                is_duplicate_suspected=True,
            )
            logger.info("Skipped duplicate email %s → %s (%s)", template, to_email, dedupe_key)
            return log

        log = EmailLog.objects.create(
            to_email=to_email,
            to_name=to_name,
            from_email=from_email or settings.DEFAULT_FROM_EMAIL,
            subject=subject[:255],
            template=template,
            category=category,
            status=EmailLog.Status.QUEUED,
            user=user if getattr(user, "pk", None) else None,
            related_type=related_type[:60],
            related_id=str(related_id)[:64],
            context_keys=sorted(context.keys()),
        )

        try:
            html_body = render_to_string(f"emails/{template}.html", context)
        except TemplateDoesNotExist:
            html_body = None
        try:
            text_body = render_to_string(f"emails/{template}.txt", context)
        except TemplateDoesNotExist:
            text_body = None

        if not html_body and not text_body:
            log.status = EmailLog.Status.FAILED
            log.error = f"Email template '{template}' not found."
            log.save(update_fields=["status", "error", "updated_at"])
            logger.error("Missing email template: %s", template)
            return log

        message = EmailMultiAlternatives(
            subject=subject,
            body=text_body or _strip_tags(html_body or ""),
            from_email=from_email or settings.DEFAULT_FROM_EMAIL,
            to=[to_email],
        )
        if html_body:
            message.attach_alternative(html_body, "text/html")

        try:
            log.attempts += 1
            sent = message.send(fail_silently=False)
            log.status = EmailLog.Status.SENT if sent else EmailLog.Status.FAILED
            log.sent_at = timezone.now() if sent else None
            if not sent:
                log.error = "The mail backend reported zero messages sent."
        except Exception as exc:  # noqa: BLE001 - never let email break a business flow
            log.status = EmailLog.Status.FAILED
            log.error = f"{exc.__class__.__name__}: {exc}"[:2000]
            logger.exception("Email delivery failed: %s → %s", template, to_email)

        log.save(update_fields=["status", "attempts", "error", "sent_at", "updated_at"])
        return log

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _already_sent(template: str, to_email: str, dedupe_key: str) -> bool:
        return EmailLog.objects.filter(
            template=template,
            to_email__iexact=to_email,
            related_type="dedupe",
            related_id=str(dedupe_key)[:64],
            status=EmailLog.Status.SENT,
        ).exists()

    @staticmethod
    def mark_dedupe(log: EmailLog, dedupe_key: str) -> EmailLog:
        """Stamps a sent log with its dedupe key so the next call is a no-op."""
        log.related_type = "dedupe"
        log.related_id = str(dedupe_key)[:64]
        log.save(update_fields=["related_type", "related_id", "updated_at"])
        return log

    @staticmethod
    def retry_failed(limit: int = 50) -> dict:
        """Re-attempts failed transactional emails (housekeeping job)."""
        retried = 0
        for log in EmailLog.objects.filter(
            status=EmailLog.Status.FAILED, attempts__lt=3, category=EmailLog.Category.TRANSACTIONAL
        )[:limit]:
            EmailService.send(
                template=log.template,
                to_email=log.to_email,
                subject=log.subject,
                to_name=log.to_name,
                category=log.category,
                related_type=log.related_type,
                related_id=log.related_id,
            )
            retried += 1
        return {"retried": retried}


def _strip_tags(html: str) -> str:
    import re

    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()
