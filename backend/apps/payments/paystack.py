"""PaystackService — the ONLY component that talks to Paystack.

The secret key never leaves the backend. All calls are server-side:
initialize, verify, refund. Webhook signatures are HMAC SHA-512 of the raw
request body using PAYSTACK_WEBHOOK_SECRET.
"""
import hashlib
import hmac
import logging

import requests
from django.conf import settings

from apps.core.exceptions import ServiceError

logger = logging.getLogger("starmond.payments")

TIMEOUT = (5, 15)  # connect, read


class PaystackError(ServiceError):
    status_code = 502
    default_code = "paystack_error"
    default_detail = "Payment provider is unavailable. Please try again."


class PaystackService:
    @classmethod
    def _base_url(cls):
        return getattr(settings, "PAYSTACK_BASE_URL", "https://api.paystack.co")

    @classmethod
    def _headers(cls):
        if not settings.PAYSTACK_SECRET_KEY:
            raise PaystackError("Paystack is not configured on this server.", code="paystack_not_configured")
        return {
            "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
            "Content-Type": "application/json",
        }

    @classmethod
    def _request(cls, method, path, **kwargs):
        url = f"{cls._base_url()}{path}"
        try:
            response = requests.request(method, url, headers=cls._headers(), timeout=TIMEOUT, **kwargs)
        except requests.RequestException as exc:
            logger.error("Paystack network error on %s: %s", path, exc)
            raise PaystackError("Could not reach the payment provider.")
        try:
            data = response.json()
        except ValueError:
            logger.error("Paystack non-JSON response on %s (%s)", path, response.status_code)
            raise PaystackError("Unexpected response from the payment provider.")
        if response.status_code >= 500:
            raise PaystackError("Payment provider error. Please retry shortly.")
        return data

    # ------------------------------------------------------------------ APIs
    @classmethod
    def initialize(cls, *, email, amount_kobo, reference, callback_url=None, metadata=None):
        payload = {"email": email, "amount": int(amount_kobo), "reference": reference,
                   "currency": settings.PAYSTACK_CURRENCY}
        if callback_url:
            payload["callback_url"] = callback_url
        if metadata:
            payload["metadata"] = metadata
        data = cls._request("POST", "/transaction/initialize", json=payload)
        if not data.get("status"):
            raise PaystackError(data.get("message") or "Paystack could not initialize the transaction.",
                                code="paystack_initialize_failed")
        auth = data.get("data") or {}
        return {
            "authorization_url": auth.get("authorization_url", ""),
            "access_code": auth.get("access_code", ""),
            "reference": auth.get("reference", reference),
        }

    @classmethod
    def verify(cls, reference):
        data = cls._request("GET", f"/transaction/verify/{reference}")
        if not data.get("status"):
            raise PaystackError(data.get("message") or "Verification failed.", code="paystack_verify_failed")
        return data.get("data") or {}

    @classmethod
    def refund(cls, transaction_id_or_reference, amount_kobo=None, reason=""):
        payload = {"transaction": str(transaction_id_or_reference)}
        if amount_kobo is not None:
            payload["amount"] = int(amount_kobo)
        if reason:
            payload["refund_reason"] = reason[:250]
        data = cls._request("POST", "/refund", json=payload)
        if not data.get("status"):
            raise PaystackError(data.get("message") or "Refund request rejected by provider.",
                                code="paystack_refund_failed")
        return data.get("data") or {}

    # --------------------------------------------------------------- webhook
    @staticmethod
    def verify_webhook_signature(raw_body: bytes, signature_header: str) -> bool:
        secrets = {s for s in (settings.PAYSTACK_WEBHOOK_SECRET, settings.PAYSTACK_SECRET_KEY) if s}
        if not secrets:
            logger.error("Paystack secret not configured — rejecting webhook.")
            return False
        if not signature_header:
            return False
        for secret in secrets:
            expected = hmac.new(secret.encode(), raw_body, digestmod=hashlib.sha512).hexdigest()
            if hmac.compare_digest(expected, signature_header):
                return True
        return False
