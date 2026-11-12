"""Request correlation, audit context and lightweight security headers."""
from __future__ import annotations

import threading
import uuid

_local = threading.local()


def get_current_request():
    return getattr(_local, "request", None)


def set_current_request(request):
    _local.request = request


class RequestIDMiddleware:
    """Attaches a correlation id to every request/response for traceable support."""

    HEADER = "HTTP_X_REQUEST_ID"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.META.get(self.HEADER) or uuid.uuid4().hex
        request.request_id = str(request_id)[:64]
        response = self.get_response(request)
        response["X-Request-ID"] = request.request_id
        return response


class AuditContextMiddleware:
    """Binds the active request to the thread so audit logging can see the actor."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        set_current_request(request)
        try:
            return self.get_response(request)
        finally:
            set_current_request(None)
