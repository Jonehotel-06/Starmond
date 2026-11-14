import time
import uuid

from django.utils.deprecation import MiddlewareMixin


class RequestContextMiddleware(MiddlewareMixin):
    """Attach a request id and timing to every request; expose X-Request-ID."""

    def process_request(self, request):
        request.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        request._started_at = time.monotonic()

    def process_response(self, request, response):
        response["X-Request-ID"] = getattr(request, "request_id", "-")
        started = getattr(request, "_started_at", None)
        if started:
            response["X-Response-Time-Ms"] = f"{(time.monotonic() - started) * 1000:.1f}"
        return response
