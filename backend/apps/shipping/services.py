"""ShippingService — authoritative delivery fee calculation and an extensible
provider abstraction for future logistics integrations."""
from decimal import Decimal

from apps.core.exceptions import ServiceError

from .models import ShippingMethod, ShippingZone


class ShippingProvider:
    """Extension point: implement create_shipment/track for future carriers.
    Tracking events are NEVER invented — providers must return real events."""
    name = "manual"

    def create_shipment(self, order):
        raise NotImplementedError

    def fetch_tracking_events(self, shipment_reference):
        raise NotImplementedError


class ShippingService:
    providers = {"manual": ShippingProvider()}

    @staticmethod
    def available_methods(state, subtotal=Decimal("0.00")):
        zone = ShippingZone.for_state(state)
        qs = ShippingMethod.objects.filter(is_active=True)
        methods = [m for m in qs if (m.zone_id is None or (zone and m.zone_id == zone.pk))]
        result = []
        for m in methods:
            result.append({
                "id": m.pk, "name": m.name, "kind": m.kind,
                "fee": str(m.fee_for(subtotal)), "base_fee": str(m.fee),
                "estimated_delivery": m.estimated_delivery,
                "pickup_address": m.pickup_address if m.kind == ShippingMethod.Kind.PICKUP else "",
                "free_above_amount": str(m.free_above_amount) if m.free_above_amount is not None else None,
            })
        return result

    @staticmethod
    def quote(method_id, state, subtotal):
        try:
            method = ShippingMethod.objects.get(pk=method_id, is_active=True)
        except ShippingMethod.DoesNotExist:
            raise ServiceError("Selected delivery method is unavailable.", code="shipping_method_unavailable")
        zone = ShippingZone.for_state(state)
        if method.zone_id is not None and (zone is None or method.zone_id != zone.pk):
            raise ServiceError(f"'{method.name}' does not deliver to {state}.", code="shipping_zone_mismatch")
        return method, method.fee_for(subtotal)
