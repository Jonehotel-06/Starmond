"""Delivery quoting and tracking endpoints."""
from __future__ import annotations

from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.throttling import ScopedRateThrottle

from apps.core.exceptions import ValidationError
from apps.core.permissions import RequiresPermission
from apps.core.views import BaseAPIView
from apps.orders.services import OrderService
from apps.shipping.constants import NIGERIAN_STATES
from apps.shipping.models import Shipment
from apps.shipping.services import ShippingService


class ShippingStatesView(BaseAPIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return self.ok({
            "eligible_states": ShippingService.eligible_states(),
            "all_states": NIGERIAN_STATES,
        })


class ShippingQuoteView(BaseAPIView):
    """Authoritative delivery fee for a destination."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "anon"

    def post(self, request):
        state = str(request.data.get("state", "")).strip()
        city = str(request.data.get("city", "")).strip()
        if not state:
            raise ValidationError("A delivery state is required.")
        subtotal = request.data.get("subtotal", 0)
        quote = ShippingService.quote(
            state=state, city=city, subtotal=subtotal,
            is_heavy=bool(request.data.get("is_heavy")),
            method_code=request.data.get("method_code") or None,
        )
        return self.ok({
            "quote": quote.as_dict(),
            "options": ShippingService.options_for(
                state=state, city=city, subtotal=subtotal,
                is_heavy=bool(request.data.get("is_heavy")),
            ),
        })


class CustomerTrackingView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, order_number: str):
        order = OrderService.get_customer_order(order_number, request.user)
        return self.ok(ShippingService.track(order))


class StaffShipmentCreateView(BaseAPIView):
    permission_classes = [RequiresPermission.of("shipping.add_shipment")]

    def post(self, request, order_number: str):
        from apps.orders.models import Order

        order = Order.objects.filter(order_number=order_number).first()
        if order is None:
            from apps.core.exceptions import NotFound

            raise NotFound("Order not found.")
        shipment = ShippingService.create_shipment(
            order,
            provider_code=request.data.get("provider", "internal"),
            tracking_reference=request.data.get("tracking_reference", ""),
            carrier=request.data.get("carrier", ""),
            notes=request.data.get("notes", ""),
        )
        return self.created(
            {
                "tracking_reference": shipment.tracking_reference,
                "status": shipment.status,
                "carrier": shipment.carrier,
            },
            message="Shipment created.",
        )


class StaffShipmentEventView(BaseAPIView):
    """Records a real tracking event; nothing is ever fabricated."""

    permission_classes = [RequiresPermission.of("shipping.change_shipment")]

    def post(self, request, tracking_reference: str):
        shipment = Shipment.objects.filter(tracking_reference=tracking_reference).first()
        if shipment is None:
            from apps.core.exceptions import NotFound

            raise NotFound("Shipment not found.")
        status = request.data.get("status")
        if status not in Shipment.Status.values:
            raise ValidationError("Unknown shipment status.")
        updated = ShippingService.update_shipment_status(
            shipment, status,
            description=request.data.get("description", ""),
            location=request.data.get("location", ""),
            actor=request.user,
        )
        return self.ok(
            {"tracking_reference": updated.tracking_reference, "status": updated.status},
            message="Tracking updated.",
        )
