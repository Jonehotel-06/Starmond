"""Checkout, order retrieval, tracking and customer order actions."""
from __future__ import annotations

from django.conf import settings
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.throttling import ScopedRateThrottle

from apps.cart.services import CartService
from apps.core.exceptions import ValidationError
from apps.core.pagination import StandardResultsSetPagination
from apps.core.views import BaseAPIView, client_ip
from apps.orders.checkout import CheckoutService
from apps.orders.models import Order
from apps.orders.serializers import (
    BuyNowSerializer, CheckoutSerializer, OrderDetailSerializer, OrderSummarySerializer,
)
from apps.orders.services import OrderService
from apps.payments.services import PaymentService


def _order_payload(order, request) -> dict:
    payload = OrderDetailSerializer(order).data
    payload["payment"] = PaymentService.public_payment_status(order)
    if order.payment_status in {Order.PaymentStatus.UNPAID, Order.PaymentStatus.FAILED,
                                Order.PaymentStatus.PENDING}:
        payload["payment_endpoint"] = str(request.build_absolute_uri("/api/v1/payments/initialize/"))
    # A guest receives their one-time access token exactly once, here.
    token = getattr(order, "_plain_guest_token", None)
    if token:
        payload["guest_access_token"] = token
    return payload


class CheckoutPreviewView(BaseAPIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "checkout"

    def post(self, request):
        data = request.data
        customer = request.user if request.user.is_authenticated else None
        cart = CartService.get_for_request(request, create=False)
        payload = CheckoutService.preview(
            cart=cart,
            product_id=data.get("product_id"),
            variation_id=data.get("variation_id"),
            quantity=data.get("quantity", 1),
            state=data.get("state", ""),
            city=data.get("city", ""),
            shipping_method_code=data.get("shipping_method_code") or None,
            promo_codes=data.get("promo_codes"),
            customer=customer,
        )
        return self.ok(payload)


class CartCheckoutView(BaseAPIView):
    """Converts the active cart into an order. Requires an idempotency key."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "checkout"

    def post(self, request):
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cart = CartService.get_for_request(request)
        customer = request.user if request.user.is_authenticated else None

        result = CheckoutService.checkout_cart(
            cart=cart,
            shipping=serializer.to_shipping(),
            customer=customer,
            guest_email=serializer.validated_data.get("email", ""),
            guest_phone=serializer.validated_data.get("phone", ""),
            customer_note=serializer.validated_data.get("customer_note", ""),
            shipping_method_code=serializer.validated_data.get("shipping_method_code") or None,
            promo_codes=serializer.validated_data.get("promo_codes"),
            source_ip=client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
            idempotency_key=serializer.validated_data.get("idempotency_key")
            or request.META.get("HTTP_X_IDEMPOTENCY_KEY"),
        )
        payload = _order_payload(result.order, request)
        return self.created(
            payload,
            message="Order created. Complete payment to confirm it."
            if not result.replayed else "This order was already created.",
        )


class BuyNowCheckoutView(BaseAPIView):
    """Direct checkout that never touches the customer's existing cart."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "checkout"

    def post(self, request):
        serializer = BuyNowSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        customer = request.user if request.user.is_authenticated else None

        result = CheckoutService.checkout_buy_now(
            product_id=str(data["product_id"]),
            variation_id=str(data["variation_id"]) if data.get("variation_id") else None,
            quantity=data["quantity"],
            shipping=serializer.to_shipping(),
            customer=customer,
            guest_email=data.get("email", ""),
            guest_phone=data.get("phone", ""),
            customer_note=data.get("customer_note", ""),
            shipping_method_code=data.get("shipping_method_code") or None,
            promo_codes=data.get("promo_codes"),
            custom_order_details=data.get("custom_order_details"),
            source_ip=client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
            idempotency_key=data.get("idempotency_key")
            or request.META.get("HTTP_X_IDEMPOTENCY_KEY"),
        )
        return self.created(_order_payload(result.order, request),
                            message="Order created. Complete payment to confirm it.")


class CustomerOrderListView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = Order.objects.filter(customer=request.user).order_by("-created_at")
        if request.query_params.get("status"):
            queryset = queryset.filter(status=request.query_params["status"])
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(OrderSummarySerializer(page, many=True).data)


class CustomerOrderDetailView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, order_number: str):
        order = OrderService.get_customer_order(order_number, request.user)
        return self.ok(_order_payload(order, request))


class GuestOrderDetailView(BaseAPIView):
    """Guest access via the expiring token issued at checkout."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "anon"

    def get(self, request, order_number: str):
        token = request.query_params.get("token") or request.META.get("HTTP_X_ORDER_TOKEN", "")
        order = OrderService.get_guest_order(order_number, token)
        return self.ok(_order_payload(order, request))


class CustomerOrderCancelView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, order_number: str):
        order = OrderService.get_customer_order(order_number, request.user)
        updated = OrderService.cancel(order, actor=request.user,
                                      reason=request.data.get("reason", ""))
        return self.ok(_order_payload(updated, request), message="Order cancelled.")


class CustomerOrderTrackView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, order_number: str):
        order = OrderService.get_customer_order(order_number, request.user)
        from apps.shipping.services import ShippingService

        return self.ok({
            "order_number": order.order_number,
            "status": order.status,
            "status_label": order.get_status_display(),
            "progress": order.fulfilment_progress,
            "tracking": ShippingService.track(order),
            "timeline": OrderDetailSerializer(order).data["activities"],
        })


class OrderReceiptView(BaseAPIView):
    """Machine-readable receipt; printable HTML lives on the frontend."""

    permission_classes = [IsAuthenticated]

    def get(self, request, order_number: str):
        order = OrderService.get_customer_order(order_number, request.user)
        if not order.is_paid:
            raise ValidationError("A receipt is only available for a paid order.")
        from apps.cms.services import SettingsService

        return self.ok({
            "receipt_number": f"RCP-{order.order_number}",
            "issued_at": order.paid_at.isoformat() if order.paid_at else None,
            "business": {
                "name": settings.BUSINESS_NAME,
                "email": SettingsService.get("support_email", ""),
                "phone": SettingsService.get("support_phone", ""),
                "address": SettingsService.get("business_address", ""),
            },
            "customer": {"name": order.customer_name, "email": order.customer_email},
            "order": OrderDetailSerializer(order).data,
            "amount_paid": str(order.amount_paid),
            "amount_refunded": str(order.amount_refunded),
            "currency": order.currency,
        })
