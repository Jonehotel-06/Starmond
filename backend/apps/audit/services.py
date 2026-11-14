import logging

from django.db import transaction

logger = logging.getLogger("starmond.audit")


class AuditService:
    """Records audit entries. Audit failure must never break the business
    transaction it observes, so writes are best-effort outside the caller's
    critical path but inside the same request."""

    @staticmethod
    def log(actor, action, entity_type="", entity_id="", data=None, request=None):
        try:
            from .models import AuditLog
            ip = None
            ua = ""
            if request is not None:
                ip = request.META.get("REMOTE_ADDR")
                fwd = request.META.get("HTTP_X_FORWARDED_FOR")
                if fwd:
                    ip = fwd.split(",")[0].strip()
                ua = request.META.get("HTTP_USER_AGENT", "")[:255]
            AuditLog.objects.create(
                actor=actor if (actor and getattr(actor, "is_authenticated", False)) else None,
                action=action, entity_type=entity_type, entity_id=str(entity_id or ""),
                data=data or {}, ip_address=ip, user_agent=ua,
            )
        except Exception:  # pragma: no cover - defensive
            logger.exception("Audit log write failed for action=%s", action)
