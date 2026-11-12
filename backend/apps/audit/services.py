"""AuditService — the single write path for the audit trail."""
from __future__ import annotations

import logging
from typing import Any

from apps.audit.models import AuditLog
from apps.core.middleware import get_current_request

logger = logging.getLogger("apps.audit")


class AuditService:
    @staticmethod
    def record(
        *,
        action: str,
        entity_type: str,
        entity_id: Any = "",
        actor=None,
        summary: str = "",
        before: dict | None = None,
        after: dict | None = None,
        metadata: dict | None = None,
    ) -> AuditLog | None:
        """
        Writes one audit entry.

        Auditing must never break the business transaction it observes, so any
        failure here is logged and swallowed.
        """
        request = get_current_request()
        if actor is None and request is not None:
            candidate = getattr(request, "user", None)
            if candidate is not None and getattr(candidate, "is_authenticated", False):
                actor = candidate
        try:
            role = ""
            profile = getattr(actor, "staff_profile", None) if actor else None
            if profile is not None and profile.role_id:
                role = profile.role.slug
            elif getattr(actor, "is_superuser", False):
                role = "super_admin"
            return AuditLog.objects.create(
                actor=actor if getattr(actor, "pk", None) else None,
                actor_email=getattr(actor, "email", "") or "",
                actor_role=role,
                action=action,
                entity_type=entity_type[:80],
                entity_id=str(entity_id)[:64],
                summary=summary[:255],
                before=before,
                after=after,
                metadata=metadata,
                ip_address=getattr(request, "client_ip", None) if request else None,
                user_agent=(request.META.get("HTTP_USER_AGENT", "")[:255] if request else ""),
                request_id=getattr(request, "request_id", "") if request else "",
            )
        except Exception:  # pragma: no cover - defensive
            logger.exception("Audit write failed for %s %s:%s", action, entity_type, entity_id)
            return None

    @staticmethod
    def diff(before: dict, after: dict) -> dict:
        """Returns the changed keys only — keeps audit payloads small and useful."""
        changed = {}
        for key in set(before) | set(after):
            if before.get(key) != after.get(key):
                changed[key] = {"from": before.get(key), "to": after.get(key)}
        return changed
