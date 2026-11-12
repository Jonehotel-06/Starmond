"""Logging helpers."""
from __future__ import annotations

import logging

from apps.core.middleware import get_current_request


class RequestIDLogFilter(logging.Filter):
    def filter(self, record):
        request = get_current_request()
        record.request_id = getattr(request, "request_id", "-") if request else "-"
        return True
