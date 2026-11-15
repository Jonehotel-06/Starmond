import django_filters as filters
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import AuditService
from apps.core.constants import Perm
from apps.core.exceptions import ServiceError
from apps.core.permissions import IsStaffWithPermission, user_has_permission
from services.checkout_service import GUEST_TOKEN_SALT, CheckoutService
from services.notification_service import NotificationService

from .models import Order
from .serializers import (
    CheckoutSerializer,
    GuestLookupSerializer,
    OrderDetailSerializer,
    OrderStaffSerializer,
    OrderStatusUpdateSerializer,
    OrderSummarySerializer,
)
from .services import OrderService


from drf_spectacular.utils import OpenApiTypes, extend_schema, extend_schema_view

@extend_schema(tags=["checkout"], request=CheckoutSerializer,
    responses={201: OpenApiTypes.OBJECT, 200: OpenApiTypes.OBJECT},
    description="Create a pending order from the cart (source.type=cart) or directly (source.type=buy_now). Send an Idempotency-Key header to make retries safe.")
class CheckoutView(APIView):
    """POST /api/checkout/ — cart checkout AND Buy Now (source.type).

    Creates a pending order, reserves stock, applies authoritative pricing.
    Send an Idempotency-Key header to make retries safe.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = dict(serializer.validated_data)
        payload["idempotency_key"] = (
            request.headers.get("Idempotency-Key") or payload.get("idempotency_key") or None)
        order, created = CheckoutService.create_order(request, payload=payload)
        if created:
            NotificationService.order_created(order, request)
            AuditService.log(request.user if request.user.is_authenticated else None,
                             "order.create", "Order", order.pk,
                             {"reference": order.reference, "total": str(order.total_amount), "source": order.source},
                             request=request)
        data = OrderDetailSerializer(order).data
        data["created"] = created
        data["next_step"] = {
            "action": "initialize_payment",
            "endpoint": "/api/payments/paystack/initialize/",
            "payload": {"order_reference": order.reference,
                        **({"guest_token": order.guest_access_token} if order.guest_access_token else {})},
            "expires_at": order.expires_at,
        }
        return Response({"status": "success", "data": data},
                        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


@extend_schema(tags=["checkout"], request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT,
    description="Authoritative price quote for the current cart or a Buy Now line. Creates nothing and reserves nothing.")
class CheckoutPreviewView(APIView):
    """POST /api/checkout/preview/ — server-calculated totals for the checkout
    summary. Body: {source, cart_token?, promotion_code?, delivery: {state,
    shipping_method_id}?}. The same pricing runs again when the order is placed."""
    permission_classes = [AllowAny]

    def post(self, request):
        from apps.cart.serializers import CartItemSerializer
        from apps.products.models import Product, ProductVariation
        from services.cart_service import CartService
        from services.pricing_service import PricingService

        data = request.data if isinstance(request.data, dict) else {}
        source = data.get("source") or {"type": "cart"}
        delivery = data.get("delivery") or {}
        user = request.user if request.user.is_authenticated else None
        kwargs = {
            "customer": user,
            "shipping_method_id": delivery.get("shipping_method_id") or None,
            "shipping_state": delivery.get("state") or None,
        }
        code = str(data.get("promotion_code") or "").strip()
        items = []
        if source.get("type") == "buy_now":
            product = Product.objects.filter(pk=source.get("product_id")).first()
            if not product or not product.is_public:
                raise ServiceError("The selected product is not available.", code="product_unavailable", status_code=409)
            variation = None
            if source.get("variation_id"):
                variation = ProductVariation.objects.filter(
                    pk=source["variation_id"], product=product, is_available=True).first()
                if not variation:
                    raise ServiceError("The selected option is not available.", code="invalid_variation", status_code=409)
            try:
                quantity = int(source.get("quantity", 1))
            except (TypeError, ValueError):
                quantity = 0
            if quantity < 1:
                raise ServiceError("Invalid quantity.", code="invalid_quantity")
            available = CartService.available_stock(product, variation)
            if quantity > available:
                raise ServiceError(f"Only {available} unit(s) available.", code="stock_unavailable", status_code=409)
            price = lambda **kw: PricingService.price_buy_now(product, variation, quantity, **kw)  # noqa: E731
        else:
            cart = CartService.get_or_create_cart(request)
            price = lambda **kw: PricingService.price_cart(cart, **kw)  # noqa: E731

        promotion_error = None
        try:
            priced = price(promotion_code=code or None, **kwargs)
        except ServiceError as exc:
            # An invalid code must not hide the totals: re-price without it and
            # report why the code was rejected.
            if not code or str(getattr(exc, "code", "")).startswith(("shipping", "delivery")):
                raise
            promotion_error = str(getattr(exc, "message", "") or exc)
            priced = price(promotion_code=None, **kwargs)

        for line in priced["lines"]:
            product, variation = line["product"], line.get("variation")
            image = (variation.image if variation and variation.image else None) or product.main_image
            items.append({
                "id": line.get("cart_item_id"), "product": product.pk, "product_name": product.name,
                "product_slug": product.slug, "variation": variation.pk if variation else None,
                "variation_label": variation.display_name if variation else None,
                "quantity": line["quantity"], "unit_price": str(line["unit_price"]),
                "line_total": str(line["line_total"]), "image_url": image.file_url if image else None,
            })
        promotion, method = priced.get("promotion"), priced.get("shipping_method")
        return Response({"status": "success", "data": {
            "items": items, "item_count": priced.get("item_count", 0),
            "totals": {
                "subtotal": str(priced["subtotal"]), "discount": str(priced["discount"]),
                "shipping_fee": str(priced["shipping_fee"]) if method else None,
                "total": str(priced["total"]), "currency": priced["currency"],
            },
            "promotion": ({"code": promotion.code, "name": promotion.name, "discount": str(priced["discount"])}
                          if promotion else None),
            "promotion_error": promotion_error,
            "shipping_method": ({"id": method.pk, "name": method.name, "kind": method.kind,
                                 "estimated_delivery": method.estimated_delivery} if method else None),
        }})


@extend_schema(tags=["orders"], responses=OpenApiTypes.OBJECT)
class CustomerOrderListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Order.objects.filter(customer=request.user).prefetch_related("items")
        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        from apps.core.pagination import StandardPagination
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(OrderSummarySerializer(page, many=True).data)


@extend_schema_view(
    get=extend_schema(tags=["orders"], responses=OpenApiTypes.OBJECT),
    post=extend_schema(tags=["orders"], request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT,
        description="Cancel own pending-payment order."))
class CustomerOrderDetailView(APIView):
    """Authenticated owners OR guests holding a valid signed access token."""
    permission_classes = [AllowAny]

    def get(self, request, reference):
        order = get_object_or_404(Order.objects.prefetch_related("items"), reference=reference)
        if request.user.is_authenticated and order.customer_id == request.user.pk:
            return Response({"status": "success", "data": OrderDetailSerializer(order).data})
        token = request.query_params.get("token", "")
        if order.guest_access_token and token and CheckoutService.verify_guest_token(order, token):
            return Response({"status": "success", "data": OrderDetailSerializer(order).data})
        raise ServiceError("You do not have access to this order.", code="forbidden", status_code=403)

    def post(self, request, reference):
        """Cancel own pending-payment order."""
        order = get_object_or_404(Order, reference=reference)
        owner = request.user.is_authenticated and order.customer_id == request.user.pk
        guest_ok = order.guest_access_token and CheckoutService.verify_guest_token(
            order, request.data.get("token", ""))
        if not (owner or guest_ok):
            raise ServiceError("You do not have access to this order.", code="forbidden", status_code=403)
        if order.status != Order.Status.PENDING_PAYMENT:
            raise ServiceError("Only orders awaiting payment can be cancelled here. "
                               "For paid orders, submit a refund request.",
                               code="cancel_not_allowed", status_code=409)
        OrderService.cancel(order, actor=request.user if request.user.is_authenticated else None,
                            note="Cancelled by customer")
        NotificationService.order_cancelled(order)
        return Response({"status": "success", "message": f"Order {order.reference} cancelled."})


@extend_schema(tags=["orders"], request=GuestLookupSerializer, responses=OpenApiTypes.OBJECT)
class GuestOrderLookupView(APIView):
    """POST /api/orders/lookup/ {reference, email} -> expiring signed access token."""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = GuestLookupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = Order.objects.filter(
            reference=serializer.validated_data["reference"].upper(),
            contact_email=serializer.validated_data["email"].lower()).first()
        if not order:
            # Uniform error to avoid confirming order existence by enumeration
            raise ServiceError("No order found for that reference and email combination.", code="order_not_found", status_code=404)
        if not order.guest_access_token:
            from django.core import signing
            order.guest_access_token = signing.dumps(
                {"ref": order.reference, "email": order.contact_email}, salt=GUEST_TOKEN_SALT)
            order.save(update_fields=["guest_access_token"])
        return Response({"status": "success", "data": {
            "reference": order.reference, "token": order.guest_access_token,
            "detail_url": f"/api/orders/{order.reference}/?token={order.guest_access_token}",
            "summary": OrderSummarySerializer(order).data,
        }})


# --------------------------------------------------------------------- staff
class StaffOrderFilter(filters.FilterSet):
    q = filters.CharFilter(method="filter_q")
    date_from = filters.DateFilter(field_name="placed_at", lookup_expr="date__gte")
    date_to = filters.DateFilter(field_name="placed_at", lookup_expr="date__lte")

    class Meta:
        model = Order
        fields = ["status", "payment_status", "source", "delivery_state", "date_from", "date_to", "q"]

    def filter_q(self, qs, name, value):
        from django.db.models import Q
        return qs.filter(
            Q(reference__icontains=value) | Q(contact_email__icontains=value) |
            Q(contact_full_name__icontains=value) | Q(contact_phone__icontains=value) |
            Q(delivery_full_name__icontains=value) | Q(delivery_phone__icontains=value) |
            Q(items__product_name__icontains=value)
        ).distinct()


class StaffOrderViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsStaffWithPermission]
    permission_codename = Perm.ORDERS_VIEW
    serializer_class = OrderStaffSerializer
    queryset = Order.objects.select_related("customer").prefetch_related(
        "items", "status_logs__actor", "payments").all()
    filterset_class = StaffOrderFilter
    search_fields = ["reference", "contact_email"]
    ordering_fields = ["placed_at", "total_amount"]
    ordering = ["-placed_at"]
    lookup_field = "reference"

    def _manage_perm(self, request, codename=Perm.ORDERS_MANAGE):
        if not user_has_permission(request.user, codename):
            raise ServiceError("You lack the required permission for this action.", code="permission_denied", status_code=403)

    @action(detail=True, methods=["post"], url_path="status")
    def update_status(self, request, reference=None):
        self._manage_perm(request, Perm.ORDERS_FULFIL)
        order = self.get_object()
        serializer = OrderStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data["status"]
        # Financial statuses are driven ONLY by the payment layer.
        if new_status in (Order.Status.PAID, Order.Status.REFUNDED, Order.Status.PARTIALLY_REFUNDED,
                          Order.Status.EXPIRED, Order.Status.PAYMENT_FAILED):
            raise ServiceError(f"Status '{new_status}' is set automatically by the payment/refund system.",
                               code="protected_status", status_code=409)
        if new_status == Order.Status.CANCELLED:
            if order.payment_status == Order.PaymentStatus.PAID:
                raise ServiceError("Paid orders cannot be cancelled — process a refund instead.",
                                   code="paid_order_cancel", status_code=409)
            OrderService.cancel(order, actor=request.user, note=serializer.validated_data.get("note") or "Cancelled by staff")
        else:
            if serializer.validated_data.get("tracking_reference"):
                order.tracking_reference = serializer.validated_data["tracking_reference"][:120]
                order.save(update_fields=["tracking_reference", "updated_at"])
            OrderService.transition(order, new_status, actor=request.user,
                                    note=serializer.validated_data.get("note", ""))
        NotificationService.order_status_changed(order, new_status)
        AuditService.log(request.user, "order.status", "Order", order.pk,
                         {"to": new_status, "reference": order.reference}, request=request)
        return Response({"status": "success", "data": OrderStaffSerializer(order).data})

    @action(detail=True, methods=["post"], url_path="notes")
    def add_note(self, request, reference=None):
        self._manage_perm(request)
        order = self.get_object()
        note = (request.data.get("note") or "").strip()
        if not note:
            raise ServiceError("note is required.", code="required_field")
        order.internal_notes = (order.internal_notes + ("\n" if order.internal_notes else "") + note)[:5000]
        order.save(update_fields=["internal_notes", "updated_at"])
        AuditService.log(request.user, "order.note", "Order", order.pk, {"note": note[:200]}, request=request)
        return Response({"status": "success", "message": "Note added."})

    @action(detail=True, methods=["get"], url_path="receipt")
    def receipt(self, request, reference=None):
        """Receipt / invoice data for printing (frontend renders the document)."""
        order = self.get_object()
        from apps.cms.services import BusinessSettingsService
        business = BusinessSettingsService.all_values()
        payments = [
            {"reference": p.reference, "provider": p.provider, "provider_reference": p.provider_reference,
             "amount": str(p.amount), "currency": p.currency, "status": p.status, "channel": p.channel,
             "verified_at": p.verified_at}
            for p in order.payments.filter(status="successful")
        ]
        refunds = [
            {"reference": r.reference, "amount": str(r.approved_amount), "status": r.status, "processed_at": r.processed_at}
            for r in order.refunds.filter(status__in=["successful"])
        ]
        return Response({"status": "success", "data": {
            "business": business,
            "order": OrderStaffSerializer(order).data,
            "payments": payments,
            "refunds": refunds,
            "invoice_number": f"INV-{order.reference}",
            "generated_at": timezone.now().isoformat(),
        }})
