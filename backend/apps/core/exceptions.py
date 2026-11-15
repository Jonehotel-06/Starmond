"""Consistent API error contract.

All errors return JSON of the form:
{
  "status": "error",
  "error": {"code": "...", "message": "...", "fields": {...} | null},
  "request_id": "..." | null
}
Internal exception details are never exposed.
"""
import logging
import uuid

from django.core.exceptions import PermissionDenied, ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import status as http_status
from rest_framework.exceptions import APIException, ValidationError as DRFValidationError
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger("starmond.api")


class ServiceError(APIException):
    """Business-rule failure raised from the service layer."""
    status_code = http_status.HTTP_400_BAD_REQUEST
    default_detail = "The request could not be completed."
    default_code = "service_error"

    def __init__(self, message=None, code=None, status_code=None, fields=None):
        self.fields = fields
        if code:
            self.default_code = code
        if status_code:
            self.status_code = status_code
        # Pass the message to APIException: calling super().__init__() with no
        # arguments replaced every specific message with default_detail.
        super().__init__(detail=message or None, code=code or None)
        self.message = str(self.detail)
        self.code = self.default_code


class StockUnavailableError(ServiceError):
    status_code = http_status.HTTP_409_CONFLICT
    default_detail = "The requested quantity is not available in stock."
    default_code = "stock_unavailable"


class PaymentVerificationError(ServiceError):
    status_code = http_status.HTTP_402_PAYMENT_REQUIRED
    default_detail = "Payment could not be verified."
    default_code = "payment_verification_failed"


def _envelope(code, message, fields=None, http_status_code=400, request_id=None):
    return {
        "status": "error",
        "error": {"code": code, "message": message, "fields": fields},
        "request_id": request_id,
    }


def api_exception_handler(exc, context):
    request_id = getattr(context.get("request"), "request_id", None) or uuid.uuid4().hex[:12]
    if isinstance(exc, Http404):
        exc = APIException(detail="Resource not found.")
        exc.status_code = 404
        exc.default_code = "not_found"
    if isinstance(exc, DjangoValidationError):
        exc = DRFValidationError(detail=getattr(exc, "message_dict", None) or getattr(exc, "messages", [str(exc)]))
    if isinstance(exc, PermissionDenied):
        exc = APIException(detail="You do not have permission to perform this action.")
        exc.status_code = 403
        exc.default_code = "permission_denied"

    response = drf_exception_handler(exc, context)
    if response is None:
        logger.exception("Unhandled server error", exc_info=exc)
        from django.conf import settings
        from django.http import JsonResponse
        if settings.DEBUG:
            raise exc
        return JsonResponse(
            _envelope("server_error", "An unexpected error occurred.", http_status_code=500, request_id=request_id),
            status=500,
        )

    code = getattr(exc, "default_code", "error") if hasattr(exc, "default_code") else "error"
    data = response.data
    message, fields = "", None
    if isinstance(data, dict):
        message = str(data.get("detail", ""))
        rest = {k: v for k, v in data.items() if k != "detail"}
        fields = rest or None
        if not message and fields:
            message = "Validation failed."
    elif isinstance(data, list):
        message = "; ".join(str(i) for i in data)
    if not message:
        message = str(data)
    if getattr(exc, "fields", None):
        fields = exc.fields
    status_code = response.status_code
    response.data = _envelope(code, message, fields, status_code, request_id)
    return response
