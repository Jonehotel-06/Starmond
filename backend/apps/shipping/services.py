"""
ShippingService and the extensible delivery-provider abstraction.

The abstract ``BaseShippingProvider`` lets a real courier API be dropped in
later without touching order logic. ``InternalDeliveryProvider`` is the default
implementation: it records only events that staff actually confirm, so no
tracking history is ever invented.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from typing import Protocol

from django.db import models, transaction
from django.utils import timezone

from apps.core.exceptions import ConflictError, NotFound, ValidationError
from apps.core.utils import money
from apps.shipping.constants import NIGERIAN_STATES, STATE_ALIASES
from apps.shipping.models import (
    DeliveryAttempt,
    Shipment,
    ShipmentEvent,
    ShippingArea,
    ShippingMethod,
    ShippingZone,
)

logger = logging.getLogger("apps.shipping")


@dataclass(frozen=True)
class DeliveryQuote:
    """The authoritative delivery answer returned to checkout."""

    eligible: bool
    method_id: str | None
    method_name: str
    method_code: str
    zone_name: str
    fee: Decimal
    estimated_days_min: int
    estimated_days_max: int
    is_pickup: bool
    free_shipping_applied: bool = False
    reason: str = ""
    extras: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "eligible": self.eligible,
            "shipping_method_id": self.method_id,
            "method_name": self.method_name,
            "method_code": self.method_code,
            "zone": self.zone_name,
            "fee": str(money(self.fee)),
            "estimated_days_min": self.estimated_days_min,
            "estimated_days_max": self.estimated_days_max,
            "is_pickup": self.is_pickup,
            "free_shipping_applied": self.free_shipping_applied,
            "reason": self.reason,
        }


class BaseShippingProvider(Protocol):
    """Contract every delivery provider must satisfy."""

    code: str

    def create_shipment(self, order, method=None, **kwargs) -> Shipment: ...

    def add_event(self, shipment: Shipment, status: str, *, description: str = "",
                  location: str = "", occurred_at=None, source: str = "staff") -> ShipmentEvent: ...

    def track(self, shipment: Shipment) -> dict: ...


class InternalDeliveryProvider:
    """Default provider: in-house dispatch with staff-recorded tracking events."""

    code = "internal"

    def create_shipment(self, order, method=None, **kwargs) -> Shipment:
        tracking = kwargs.pop("tracking_reference", "") or self._generate_reference(order)
        if Shipment.objects.filter(tracking_reference=tracking).exists():
            raise ConflictError("That tracking reference is already in use.")
        shipment = Shipment.objects.create(
            order=order,
            method=method or order.shipping_method,
            carrier=kwargs.pop("carrier", ""),
            tracking_reference=tracking,
            provider=self.code,
            status=Shipment.Status.PENDING,
            recipient_name=kwargs.pop("recipient_name", order.shipping_full_name),
            recipient_phone=kwargs.pop("recipient_phone", order.shipping_phone),
            delivery_address=kwargs.pop("delivery_address", order.shipping_address_line),
            notes=kwargs.pop("notes", ""),
        )
        self.add_event(shipment, Shipment.Status.PENDING, description="Shipment created",
                       source="system")
        return shipment

    def add_event(self, shipment: Shipment, status: str, *, description: str = "",
                  location: str = "", occurred_at=None, source: str = "staff") -> ShipmentEvent:
        if status not in Shipment.Status.values:
            raise ValidationError(f"Unknown shipment status '{status}'.")
        event = ShipmentEvent.objects.create(
            shipment=shipment,
            status=status,
            description=description[:255],
            location=location[:150],
            occurred_at=occurred_at or timezone.now(),
            recorded_by=source,
            source=source,
        )
        updates = {"status": status, "updated_at": timezone.now()}
        if status == Shipment.Status.DISPATCHED and shipment.dispatched_at is None:
            updates["dispatched_at"] = event.occurred_at
        if status == Shipment.Status.DELIVERED and shipment.delivered_at is None:
            updates["delivered_at"] = event.occurred_at
        Shipment.objects.filter(pk=shipment.pk).update(**updates)
        shipment.refresh_from_db()
        return event

    def track(self, shipment: Shipment) -> dict:
        events = [
            {
                "status": e.status,
                "description": e.description,
                "location": e.location,
                "occurred_at": e.occurred_at.isoformat(),
                "source": e.source,
            }
            for e in shipment.events.all()
        ]
        return {
            "tracking_reference": shipment.tracking_reference,
            "carrier": shipment.carrier,
            "status": shipment.status,
            "estimated_delivery": None,
            "events": events,
        }

    @staticmethod
    def _generate_reference(order) -> str:
        stamp = timezone.now().strftime("%y%m%d")
        for attempt in range(1, 50):
            candidate = f"STM{stamp}{order.order_number[-6:]}{attempt:02d}"
            if not Shipment.objects.filter(tracking_reference=candidate).exists():
                return candidate
        raise ConflictError("Unable to allocate a tracking reference. Please retry.")


PROVIDERS: dict[str, type] = {
    "internal": InternalDeliveryProvider,
}


def get_provider(code: str = "internal") -> BaseShippingProvider:
    try:
        return PROVIDERS[code]()
    except KeyError:
        raise ValidationError(f"Unknown shipping provider '{code}'.")


class ShippingService:
    # ------------------------------------------------------------------
    # Zone resolution
    # ------------------------------------------------------------------
    @staticmethod
    def normalise_state(state: str) -> str:
        value = (state or "").strip()
        alias = STATE_ALIASES.get(value.lower())
        if alias:
            return alias
        for known in NIGERIAN_STATES:
            if known.lower() == value.lower():
                return known
        return value.title()

    @staticmethod
    def resolve_zone(state: str, city: str = "") -> ShippingZone | None:
        state = ShippingService.normalise_state(state)
        if not state:
            return None
        # Prefer a city-specific match, then a state-wide match.
        city_matches = ShippingArea.objects.select_related("zone").filter(
            state__iexact=state, city__iexact=city, is_active=True, zone__is_active=True
        ) if city else ShippingArea.objects.none()
        for area in city_matches:
            return area.zone
        area = (
            ShippingArea.objects.select_related("zone")
            .filter(state__iexact=state, city="", is_active=True, zone__is_active=True)
            .first()
        )
        return area.zone if area else None

    # ------------------------------------------------------------------
    # Quoting
    # ------------------------------------------------------------------
    @staticmethod
    def quote(*, state: str, city: str = "", subtotal=0, item_count: int = 1,
              is_heavy: bool = False, method_code: str | None = None) -> DeliveryQuote:
        """
        Calculates the delivery fee for a destination. The single source of truth
        for every shipping price shown or charged.
        """
        subtotal = money(subtotal)
        state_norm = ShippingService.normalise_state(state)
        if not state_norm:
            return DeliveryQuote(
                eligible=False, method_id=None, method_name="", method_code="", zone_name="",
                fee=Decimal("0.00"), estimated_days_min=0, estimated_days_max=0,
                is_pickup=False, reason="A delivery state is required.",
            )

        zone = ShippingService.resolve_zone(state_norm, city)
        if zone is None:
            return DeliveryQuote(
                eligible=False, method_id=None, method_name="", method_code="", zone_name="",
                fee=Decimal("0.00"), estimated_days_min=0, estimated_days_max=0,
                is_pickup=False,
                reason=f"We do not currently deliver to {state_norm}. Please contact support.",
            )

        methods = list(zone.methods.filter(is_active=True).order_by("position", "price"))
        if not methods:
            return DeliveryQuote(
                eligible=False, method_id=None, method_name="", method_code="", zone_name=zone.name,
                fee=Decimal("0.00"), estimated_days_min=0, estimated_days_max=0,
                is_pickup=False, reason="No delivery option is configured for this zone.",
            )

        chosen = None
        if method_code:
            chosen = next((m for m in methods if m.code == method_code), None)
            if chosen is None:
                return DeliveryQuote(
                    eligible=False, method_id=None, method_name="", method_code="", zone_name=zone.name,
                    fee=Decimal("0.00"), estimated_days_min=0, estimated_days_max=0,
                    is_pickup=False, reason="The selected delivery method is not available here.",
                )
        else:
            chosen = methods[0]

        fee = money(chosen.price)
        free_applied = False
        if chosen.free_over_amount is not None and subtotal >= money(chosen.free_over_amount):
            fee, free_applied = Decimal("0.00"), True
        if zone.free_shipping_threshold is not None and subtotal >= money(zone.free_shipping_threshold):
            fee, free_applied = Decimal("0.00"), True
        if is_heavy and chosen.kind != ShippingMethod.Kind.PICKUP:
            fee = money(fee + money(fee) * Decimal("0.25"))

        return DeliveryQuote(
            eligible=True,
            method_id=str(chosen.pk),
            method_name=chosen.name,
            method_code=chosen.code,
            zone_name=zone.name,
            fee=fee,
            estimated_days_min=chosen.estimated_days_min,
            estimated_days_max=chosen.estimated_days_max,
            is_pickup=chosen.kind == ShippingMethod.Kind.PICKUP,
            free_shipping_applied=free_applied,
            reason="",
        )

    @staticmethod
    def options_for(*, state: str, city: str = "", subtotal=0, is_heavy: bool = False) -> list[dict]:
        """All deliverable options for a destination — powers the checkout dropdown."""
        state_norm = ShippingService.normalise_state(state)
        zone = ShippingService.resolve_zone(state_norm, city) if state_norm else None
        if zone is None:
            return []
        options = []
        for method in zone.methods.filter(is_active=True).order_by("position", "price"):
            quote = ShippingService.quote(
                state=state_norm, city=city, subtotal=subtotal,
                is_heavy=is_heavy, method_code=method.code,
            )
            options.append(quote.as_dict())
        return options

    @staticmethod
    def eligible_states() -> list[str]:
        covered = (
            ShippingArea.objects.filter(is_active=True, zone__is_active=True)
            .values_list("state", flat=True)
            .distinct()
        )
        return sorted({ShippingService.normalise_state(s) for s in covered})

    # ------------------------------------------------------------------
    # Fulfilment
    # ------------------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def create_shipment(order, *, provider_code: str = "internal", tracking_reference: str = "",
                        carrier: str = "", notes: str = "") -> Shipment:
        if not order.is_paid:
            raise ConflictError("Only paid orders can be dispatched.")
        if order.status in {"cancelled", "expired", "refunded"}:
            raise ConflictError("This order can no longer be shipped.")
        existing = order.shipments.exclude(
            status=Shipment.Status.RETURNED
        ).filter(status__in=[Shipment.Status.PENDING, Shipment.Status.DISPATCHED,
                             Shipment.Status.IN_TRANSIT, Shipment.Status.OUT_FOR_DELIVERY,
                             Shipment.Status.DELIVERED]).first()
        if existing is not None:
            raise ConflictError(
                f"A shipment already exists for this order ({existing.tracking_reference})."
            )
        provider = get_provider(provider_code)
        return provider.create_shipment(
            order, order.shipping_method, tracking_reference=tracking_reference,
            carrier=carrier, notes=notes,
        )

    @staticmethod
    @transaction.atomic
    def update_shipment_status(shipment: Shipment, status: str, *, description: str = "",
                               location: str = "", occurred_at=None, actor=None,
                               source: str = "staff") -> Shipment:
        provider = get_provider(shipment.provider)
        provider.add_event(
            shipment, status, description=description, location=location,
            occurred_at=occurred_at, source=source,
        )
        shipment.refresh_from_db()
        ShippingService._sync_order_status(shipment, status, actor=actor)
        return shipment

    @staticmethod
    def _sync_order_status(shipment: Shipment, status: str, actor=None) -> None:
        """Advances the parent order when the shipemnt reaches a milestone."""
        from apps.orders.services import OrderService

        order = shipment.order
        mapping = {
            Shipment.Status.DISPATCHED: "dispatched",
            Shipment.Status.OUT_FOR_DELIVERY: "out_for_delivery",
            Shipment.Status.DELIVERED: "delivered",
        }
        target = mapping.get(status)
        if not target:
            return
        if order.status == target:
            return
        try:
            OrderService.advance_to(order, target, actor=actor,
                                    note=f"Shipment {shipment.tracking_reference}: {status}")
        except ConflictError as exc:
            logger.warning("Shipment status could not advance order %s: %s", order.order_number, exc)

    @staticmethod
    def track(order) -> dict:
        shipment = order.shipments.order_by("-created_at").first()
        if shipment is None:
            return {
                "status": "not_dispatched",
                "tracking_reference": None,
                "events": [],
                "message": "This order has not been dispatched yet.",
            }
        return get_provider(shipment.provider).track(shipment)

    @staticmethod
    def record_delivery_attempt(order, *, successful: bool, notes: str = "",
                                recipient_signature: str = "") -> DeliveryAttempt:
        return DeliveryAttempt.objects.create(
            order=order,
            attempted_at=timezone.now(),
            successful=successful,
            notes=notes,
            recipient_signature=recipient_signature,
        )
