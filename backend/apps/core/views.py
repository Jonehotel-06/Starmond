"""Reusable view primitives: envelopes, client IP, cart/guest identity."""
from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.idempotency import IDEMPOTENCY_HEADER, IdempotentRunner


class EnvelopeMixin:
    """Guarantees every success response carries ``success: true``."""

    @staticmethod
    def ok(data=None, message: str = "", status_code: int = status.HTTP_200_OK, **extra) -> Response:
        payload = {"success": True}
        if message:
            payload["message"] = message
        if data is not None:
            payload["data"] = data
        payload.update(extra)
        return Response(payload, status=status_code)

    @staticmethod
    def created(data=None, message: str = "Created.", **extra) -> Response:
        return EnvelopeMixin.ok(data, message, status.HTTP_201_CREATED, **extra)


class BaseAPIView(EnvelopeMixin, APIView):
    """Project-wide base view."""


def client_ip(request) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.META.get("REMOTE_ADDR")


def idempotency_key(request) -> str | None:
    return request.META.get(IDEMPOTENCY_HEADER) or request.data.get("idempotency_key")


def run_idempotent(request, scope: str, payload, key: str | None = None):
    """Builds an IdempotentRunner bound to the incoming request."""
    return IdempotentRunner(
        scope=scope,
        key=key or idempotency_key(request),
        payload=payload,
        actor=getattr(request.user, "id", None),
    )


