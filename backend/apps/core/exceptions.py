"""
Stable API error contract for the STARMOND platform.

Every error response has the shape::

    {
      "success": false,
      "error": {
        "code": "validation_error",
        "message": "Human readable summary.",
        "details": {"field": ["reason"]} | null
      },
      "request_id": "..."
    }

Internal exception traces and provider payloads are never exposed to clients.
"""
from __future__ import annotations

import logging

from django.core.exceptions import ObjectDoesNotExist, PermissionDenied as DjangoPermissionDenied
from django.db import IntegrityError
from django.http import Http404
from rest_framework import exceptions as drf_exceptions
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger("apps.core.exceptions")


class DomainError(Exception):
    """Base class for expected, business-level failures."""

    code = "domain_error"
    status_code = status.HTTP_400_BAD_REQUEST
    message = "Request could not be processed."

    def __init__(self, message: str | None = None, *, details=None, code: str | None = None):
        self.message = message or self.message
        self.details = details
        if code:
            self.code = code
        super().__init__(self.message)


class ValidationError(DomainError):
    code = "validation_error"
    status_code = status.HTTP_400_BAD_REQUEST
    message = "The submitted data is invalid."


class NotFound(DomainError):
    code = "not_found"
    status_code = status.HTTP_404_NOT_FOUND
    message = "The requested resource was not found."


class ConflictError(DomainError):
    code = "conflict"
    status_code = status.HTTP_409_CONFLICT
    message = "The request conflicts with the current state of the resource."


class PermissionDeniedError(DomainError):
    code = "permission_denied"
    status_code = status.HTTP_403_FORBIDDEN
    message = "You do not have permission to perform this action."


class AuthenticationRequired(DomainError):
    code = "authentication_required"
    status_code = status.HTTP_401_UNAUTHORIZED
    message = "Authentication credentials were not provided or are invalid."


class InsufficientStock(DomainError):
    code = "insufficient_stock"
    status_code = status.HTTP_409_CONFLICT
    message = "One or more items do not have sufficient stock."


class PaymentError(DomainError):
    code = "payment_error"
    status_code = status.HTTP_502_BAD_GATEWAY
    message = "The payment provider could not complete the request."


class IdempotencyConflict(DomainError):
    code = "idempotency_conflict"
    status_code = status.HTTP_409_CONFLICT
    message = "This idempotency key was already used with a different payload."


class RateLimited(DomainError):
    code = "rate_limited"
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    message = "Too many requests. Please slow down."


class InvalidStateTransition(ConflictError):
    code = "invalid_state_transition"
    message = "This action is not allowed from the current state."


def _envelope(code: str, message: str, details=None, status_code: int = 400, request=None) -> Response:
    payload = {
        "success": False,
        "error": {"code": code, "message": message, "details": details},
        "request_id": getattr(request, "request_id", None),
    }
    return Response(payload, status=status_code)


def api_exception_handler(exc, context):  # noqa: C901
    request = context.get("request")
    view = context.get("view")

    # --- Domain errors -----------------------------------------------------
    if isinstance(exc, DomainError):
        return _envelope(exc.code, exc.message, exc.details, exc.status_code, request)

    # --- DRF errors --------------------------------------------------------
    response = drf_exception_handler(exc, context)
    if response is not None:
        detail = response.data
        code = "error"
        details = None
        message = "Request failed."

        if isinstance(exc, drf_exceptions.ValidationError):
            code = "validation_error"
            message = "The submitted data is invalid."
            details = detail if isinstance(detail, dict) else {"non_field_errors": detail}
        elif isinstance(exc, drf_exceptions.NotAuthenticated):
            code, message = "authentication_required", "Authentication credentials were not provided or are invalid."
        elif isinstance(exc, (drf_exceptions.AuthenticationFailed,)):
            code, message = "authentication_failed", "Unable to authenticate with the provided credentials."
        elif isinstance(exc, (drf_exceptions.PermissionDenied, DjangoPermissionDenied)):
            code, message = "permission_denied", "You do not have permission to perform this action."
        elif isinstance(exc, Http404):
            code, message = "not_found", "The requested resource was not found."
        elif isinstance(exc, drf_exceptions.Throttled):
            code = "rate_limited"
            message = "Too many requests. Please slow down."
            details = {"retry_after_seconds": exc.wait}
        elif isinstance(exc, drf_exceptions.MethodNotAllowed):
            code, message = "method_not_allowed", "This HTTP method is not allowed on this endpoint."
        elif isinstance(exc, drf_exceptions.UnsupportedMediaType):
            code, message = "unsupported_media_type", "The request content type is not supported."
        elif isinstance(exc, drf_exceptions.ParseError):
            code, message = "parse_error", "The request body could not be parsed."
        else:
            if isinstance(detail, dict) and "detail" in detail:
                message = str(detail["detail"])
            elif isinstance(detail, (str, list)):
                message = str(detail)
            code = getattr(exc, "default_code", "error") or "error"

        response.data = {
            "success": False,
            "error": {"code": code, "message": message, "details": details},
            "request_id": getattr(request, "request_id", None),
        }
        return response

    # --- Unhandled infrastructure errors ----------------------------------
    if isinstance(exc, IntegrityError):
        logger.warning("IntegrityError on %s: %s", getattr(view, "__class__", "?"), exc)
        return _envelope(
            "integrity_conflict",
            "The request conflicts with existing records.",
            None,
            status.HTTP_409_CONFLICT,
            request,
        )

    if isinstance(exc, ObjectDoesNotExist):
        return _envelope("not_found", "The requested resource was not found.", None, 404, request)

    logger.exception("Unhandled exception on %s", getattr(view, "__class__", "?"))
    return _envelope(
        "server_error",
        "An unexpected error occurred. Our team has been notified.",
        None,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        request,
    )
