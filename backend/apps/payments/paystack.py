"""
PaystackService — a thin, defensive wrapper around the official Paystack API.

Everything here is server-side only. The secret key never leaves the backend and
is never included in a response body, log line or error message.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass, field

import requests
from django.conf import settings

from apps.core.exceptions import PaymentError, ValidationError
from apps.core.utils import from_kobo, money, to_kobo

logger = logging.getLogger("payments.paystack")

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


@dataclass
class PaystackResponse:
    ok: bool
    status_code: int
    message: str
    data: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)

    @property
    def reference(self) -> str:
        return str(self.data.get("reference", ""))

    @property
    def amount_kobo(self) -> int:
        try:
            return int(self.data.get("amount", 0))
        except (TypeError, ValueError):
            return 0

    @property
    def currency(self) -> str:
        return str(self.data.get("currency", "")).upper()

    @property
    def paid(self) -> bool:
        return str(self.data.get("status", "")).lower() == "success"


class PaystackService:
    """Official Paystack REST API client."""

    # ------------------------------------------------------------------
    # Configuration guards
    # ------------------------------------------------------------------
    @classmethod
    def assert_configured(cls) -> None:
        if not settings.PAYSTACK_SECRET_KEY:
            raise PaymentError(
                "Payment is temporarily unavailable. Please try again later.",
                code="payment_not_configured",
            )
        cls.assert_credential_mode()

    @classmethod
    def assert_credential_mode(cls) -> None:
        """
        Refuses to run live credentials in development (Section 12).

        This is a hard stop: taking real money while pointed at a sandbox
        database is worse than a failed checkout.
        """
        key = settings.PAYSTACK_SECRET_KEY or ""
        is_live_key = key.startswith("sk_live_")
        if is_live_key and settings.PAYSTACK_MODE != "live":
            raise PaymentError(
                "Live Paystack credentials are configured while PAYSTACK_MODE is not 'live'. "
                "Refusing to process payments.",
                code="paystack_mode_mismatch",
            )
        if settings.PAYSTACK_MODE == "live" and settings.DEBUG and not settings.PAYSTACK_ALLOW_LIVE_IN_DEBUG:
            raise PaymentError(
                "Live payments are blocked while DEBUG is enabled.",
                code="paystack_live_blocked_in_debug",
            )

    @staticmethod
    def _headers() -> dict:
        return {
            "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "STARMOND-Backend/1.0",
        }

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------
    @classmethod
    def _request(cls, method: str, path: str, payload: dict | None = None) -> PaystackResponse:
        cls.assert_configured()
        url = f"{settings.PAYSTACK_BASE_URL.rstrip('/')}{path}"
        last_error: str = ""

        for attempt in range(1, settings.PAYSTACK_MAX_RETRIES + 1):
            try:
                response = requests.request(
                    method,
                    url,
                    headers=cls._headers(),
                    json=payload,
                    timeout=settings.PAYSTACK_TIMEOUT_SECONDS,
                )
            except requests.Timeout:
                last_error = "Paystack request timed out."
                logger.warning("Paystack timeout: %s %s (attempt %s)", method, path, attempt)
                time.sleep(min(0.4 * attempt, 2.0))
                continue
            except requests.RequestException as exc:
                last_error = "Could not reach the payment provider."
                logger.warning("Paystack transport error: %s (attempt %s)", exc.__class__.__name__, attempt)
                time.sleep(min(0.4 * attempt, 2.0))
                continue

            try:
                body = response.json()
            except ValueError:
                body = {}

            ok = 200 <= response.status_code < 300 and bool(body.get("status"))
            message = str(body.get("message", "") or "")

            if not ok and response.status_code in RETRYABLE_STATUS and attempt < settings.PAYSTACK_MAX_RETRIES:
                last_error = message or "Payment provider is busy."
                time.sleep(min(0.5 * attempt, 2.0))
                continue

            return PaystackResponse(
                ok=ok,
                status_code=response.status_code,
                message=message,
                data=body.get("data") or {},
                raw=body,
            )

        raise PaymentError(
            last_error or "The payment provider is unavailable. Please try again.",
            code="paystack_unavailable",
        )

    # ------------------------------------------------------------------
    # Transactions
    # ------------------------------------------------------------------
    @classmethod
    def initialize_transaction(
        cls,
        *,
        email: str,
        amount,
        reference: str,
        currency: str = "NGN",
        callback_url: str | None = None,
        metadata: dict | None = None,
        channels: list[str] | None = None,
    ) -> PaystackResponse:
        """Initialises a transaction and returns the authorization URL."""
        amount_kobo = to_kobo(amount)
        if amount_kobo <= 0:
            raise ValidationError("The payment amount must be greater than zero.")
        payload = {
            "email": email,
            "amount": amount_kobo,
            "currency": currency,
            "reference": reference,
            "callback_url": callback_url or settings.PAYSTACK_CALLBACK_URL,
            "channels": channels or settings.PAYSTACK_CHANNELS,
            "metadata": metadata or {},
        }
        response = cls._request("POST", "/transaction/initialize", payload)
        if not response.ok:
            logger.warning("Paystack initialize failed (%s): %s", response.status_code, response.message)
            raise PaymentError(
                response.message or "The payment could not be initialised. Please try again.",
                code="paystack_initialize_failed",
            )
        return response

    @classmethod
    def verify_transaction(cls, reference: str) -> PaystackResponse:
        """Independent server-side verification — the only proof of payment we accept."""
        if not reference:
            raise ValidationError("A transaction reference is required.")
        response = cls._request("GET", f"/transaction/verify/{reference}")
        if response.status_code == 404:
            raise PaymentError(
                "We could not find that transaction with the payment provider.",
                code="paystack_reference_not_found",
            )
        return response

    @classmethod
    def refund_transaction(
        cls,
        *,
        transaction_reference: str,
        amount=None,
        reason: str = "",
        merchant_note: str = "",
        customer_note: str = "",
    ) -> PaystackResponse:
        """
        Submits a refund request. A submitted request is **not** a completed
        refund — the final outcome must be confirmed via ``fetch_refund``.
        """
        payload: dict = {
            "transaction": transaction_reference,
            "merchant_note": (merchant_note or reason or "Customer refund")[:255],
            "customer_note": (customer_note or reason or "Your refund has been processed")[:255],
        }
        if amount is not None:
            payload["amount"] = to_kobo(amount)
        response = cls._request("POST", "/refund", payload)
        if not response.ok:
            logger.warning("Paystack refund failed (%s): %s", response.status_code, response.message)
            raise PaymentError(
                response.message or "The refund could not be submitted to the provider.",
                code="paystack_refund_failed",
            )
        return response

    @classmethod
    def fetch_refund(cls, identifier) -> PaystackResponse:
        """Retrieves the authoritative state of a submitted refund."""
        return cls._request("GET", f"/refund/{identifier}")

    @classmethod
    def list_refunds(cls, *, per_page: int = 50, page: int = 1) -> PaystackResponse:
        return cls._request("GET", f"/refund?perPage={per_page}&page={page}")

    # ------------------------------------------------------------------
    # Webhooks
    # ------------------------------------------------------------------
    @staticmethod
    def compute_signature(raw_body: bytes) -> str:
        secret = settings.PAYSTACK_WEBHOOK_SECRET or settings.PAYSTACK_SECRET_KEY
        return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha512).hexdigest()

    @classmethod
    def verify_webhook_signature(cls, raw_body: bytes, signature: str) -> bool:
        """
        Constant-time comparison of the ``x-paystack-signature`` header.

        An unsigned or wrongly-signed webhook is always rejected, no matter how
        convincing the payload looks.
        """
        if not signature or not settings.PAYSTACK_WEBHOOK_SECRET and not settings.PAYSTACK_SECRET_KEY:
            return False
        expected = cls.compute_signature(raw_body)
        return hmac.compare_digest(expected, str(signature).strip().lower())

    @staticmethod
    def parse_webhook(raw_body: bytes) -> dict:
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ValidationError("The webhook payload could not be parsed.")
        if not isinstance(payload, dict):
            raise ValidationError("The webhook payload has an unexpected shape.")
        return payload

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------
    @staticmethod
    def public_config() -> dict:
        """The only Paystack information the browser may receive."""
        return {
            "provider": "paystack",
            "public_key": settings.PAYSTACK_PUBLIC_KEY,
            "mode": settings.PAYSTACK_MODE,
            "currency": settings.DEFAULT_CURRENCY,
            "channels": settings.PAYSTACK_CHANNELS,
            "callback_url": settings.PAYSTACK_CALLBACK_URL,
        }

    @staticmethod
    def amount_from_response(paystack_data: dict):
        return from_kobo(paystack_data.get("amount", 0))

    @staticmethod
    def normalise_amount(value):
        return money(value)
