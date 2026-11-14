"""Idempotency support for state-changing endpoints.

Clients send an `Idempotency-Key` header. The first request for a key stores
the response; replays return the stored response without re-executing side
effects (order creation, payment initialization, etc.).
"""
import hashlib
import json

from django.core.cache import cache
from rest_framework.response import Response

IDEMPOTENCY_TTL_SECONDS = 60 * 60 * 24  # 24h


def _cache_key(scope, key, user_id):
    digest = hashlib.sha256(f"{scope}:{user_id}:{key}".encode()).hexdigest()
    return f"idem:{digest}"


def get_cached_response(scope, key, user_id):
    if not key:
        return None
    return cache.get(_cache_key(scope, key, user_id))


def store_response(scope, key, user_id, status_code, data):
    if not key:
        return
    cache.set(_cache_key(scope, key, user_id), {"status_code": status_code, "data": data}, IDEMPOTENCY_TTL_SECONDS)


def idempotent_response(cached):
    return Response(cached["data"], status=cached["status_code"])
