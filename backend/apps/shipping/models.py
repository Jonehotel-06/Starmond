"""
Delivery zones, methods and shipments.

Delivery eligibility and fees are always computed on the server (Section 45
rule 16). Nothing here trusts a client-submitted fee.
"""
from __future__ import annotations

import uuid

from django.db import models

from apps.core.models import BaseModel, TimeStampedModel


class ShippingZone(BaseModel):
    """A named delivery zone covering one or more Nigerian states/cities."""

    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    position = models.PositiveIntegerField(default=0)
    free_shipping_threshold = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        help_text="Order subtotal at or above which shipping is free in this zone.",
    )

    class Meta:
        db_table = "shipping_zone"
        ordering = ["position", "name"]

    def __str__(self) -> str:
        return self.name

    def covers_state(self, state: str, city: str = "") -> bool:
        areas = list(self.areas.filter(is_active=True))
        if not areas:
            return False
        state_norm = (state or "").strip().lower()
        city_norm = (city or "").strip().lower()
        for area in areas:
            if area.state.strip().lower() != state_norm:
                continue
            if not area.city:
                return True
            if area.city.strip().lower() == city_norm:
                return True
        return False


class ShippingArea(BaseModel):
    """A state (optionally narrowed to a city) inside a zone."""

    zone = models.ForeignKey(ShippingZone, on_delete=models.CASCADE, related_name="areas")
    state = models.CharField(max_length=80, db_index=True)
    city = models.CharField(max_length=80, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "shipping_area"
        ordering = ["state", "city"]
        constraints = [
            models.UniqueConstraint(fields=["zone", "state", "city"], name="uniq_zone_state_city"),
        ]
        indexes = [models.Index(fields=["state", "city"])]

    def __str__(self) -> str:
        return f"{self.state}{f' / {self.city}' if self.city else ''}"


class ShippingMethod(BaseModel):
    """A priced delivery option inside a zone (home delivery, pickup, express…)."""

    class Kind(models.TextChoices):
        DELIVERY = "delivery", "Home delivery"
        EXPRESS = "express", "Express delivery"
        PICKUP = "pickup", "Store pickup"

    zone = models.ForeignKey(ShippingZone, on_delete=models.CASCADE, related_name="methods")
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=60, db_index=True)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.DELIVERY)
    price = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    free_over_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    estimated_days_min = models.PositiveSmallIntegerField(default=1)
    estimated_days_max = models.PositiveSmallIntegerField(default=5)
    pickup_address = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "shipping_method"
        ordering = ["zone__position", "position", "price"]
        constraints = [
            models.UniqueConstraint(fields=["zone", "code"], name="uniq_method_code_per_zone"),
            models.CheckConstraint(check=models.Q(price__gte=0), name="shipping_price_non_negative"),
            models.CheckConstraint(
                check=models.Q(estimated_days_max__gte=models.F("estimated_days_min")),
                name="shipping_estimate_ordered",
            ),
        ]
        indexes = [models.Index(fields=["zone", "is_active"])]

    def __str__(self) -> str:
        return f"{self.name} ({self.zone.name})"

    @property
    def estimated_label(self) -> str:
        if self.estimated_days_min == self.estimated_days_max:
            days = self.estimated_days_min
            return f"{days} business day{'s' if days != 1 else ''}"
        return f"{self.estimated_days_min}–{self.estimated_days_max} business days"


class Shipment(BaseModel):
    """A dispatch record with a tracking reference for the customer."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending dispatch"
        DISPATCHED = "dispatched", "Dispatched"
        IN_TRANSIT = "in_transit", "In transit"
        OUT_FOR_DELIVERY = "out_for_delivery", "Out for delivery"
        DELIVERED = "delivered", "Delivered"
        FAILED = "failed", "Delivery failed"
        RETURNED = "returned", "Returned to sender"

    order = models.ForeignKey("orders.Order", on_delete=models.CASCADE, related_name="shipments")
    method = models.ForeignKey(
        ShippingMethod, null=True, blank=True, on_delete=models.SET_NULL, related_name="shipments"
    )
    carrier = models.CharField(max_length=120, blank=True)
    tracking_reference = models.CharField(max_length=64, unique=True, db_index=True)
    provider = models.CharField(max_length=60, default="internal")
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.PENDING, db_index=True)
    dispatched_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    recipient_name = models.CharField(max_length=150, blank=True)
    recipient_phone = models.CharField(max_length=16, blank=True)
    delivery_address = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "shipping_shipment"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["order", "status"])]

    def __str__(self) -> str:
        return f"Shipment {self.tracking_reference} ({self.status})"


class ShipmentEvent(TimeStampedModel):
    """A single, real tracking event. Events are never fabricated."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, related_name="events")
    status = models.CharField(max_length=30, choices=Shipment.Status.choices)
    description = models.CharField(max_length=255, blank=True)
    location = models.CharField(max_length=150, blank=True)
    occurred_at = models.DateTimeField()
    recorded_by = models.CharField(max_length=120, blank=True)
    source = models.CharField(max_length=40, default="staff", help_text="staff | provider | system")

    class Meta:
        db_table = "shipping_shipment_event"
        ordering = ["-occurred_at"]
        indexes = [models.Index(fields=["shipment", "-occurred_at"])]

    def __str__(self) -> str:
        return f"{self.status} @ {self.occurred_at:%Y-%m-%d %H:%M}"


class DeliveryAttempt(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey("orders.Order", on_delete=models.CASCADE, related_name="delivery_attempts")
    attempted_at = models.DateTimeField()
    successful = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    recipient_signature = models.CharField(max_length=150, blank=True)

    class Meta:
        db_table = "shipping_delivery_attempt"
        ordering = ["-attempted_at"]
