from django.db import models

from apps.core.models import TimeStampedModel


class ShippingZone(TimeStampedModel):
    """A named group of states with shared delivery availability."""
    name = models.CharField(max_length=120, unique=True)
    states = models.JSONField(default=list, help_text='e.g. ["Lagos", "Ogun", "Abuja FCT"]')
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "shipping_zone"
        ordering = ["name"]

    def __str__(self):
        return self.name

    @classmethod
    def for_state(cls, state):
        normalized = (state or "").strip().lower()
        for zone in cls.objects.filter(is_active=True):
            if any(str(s).strip().lower() == normalized for s in zone.states):
                return zone
        return None


class ShippingMethod(TimeStampedModel):
    class Kind(models.TextChoices):
        STANDARD = "standard", "Standard delivery"
        EXPRESS = "express", "Express delivery"
        PICKUP = "pickup", "Pickup / collection"

    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.STANDARD)
    zone = models.ForeignKey(ShippingZone, on_delete=models.CASCADE, null=True, blank=True,
                             related_name="methods", help_text="Null = applies to all zones (e.g. pickup).")
    fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    free_above_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True,
                                            help_text="Fee waived when order subtotal reaches this amount.")
    min_days = models.PositiveIntegerField(default=1)
    max_days = models.PositiveIntegerField(default=5)
    is_active = models.BooleanField(default=True, db_index=True)
    display_order = models.PositiveIntegerField(default=0)
    pickup_address = models.CharField(max_length=255, blank=True, help_text="Shown when kind=pickup.")

    class Meta:
        db_table = "shipping_method"
        ordering = ["display_order", "fee"]
        constraints = [models.CheckConstraint(check=models.Q(max_days__gte=models.F("min_days")), name="shipping_days_sane")]

    def __str__(self):
        return f"{self.name} ({self.get_kind_display()})"

    @property
    def estimated_delivery(self):
        if self.kind == self.Kind.PICKUP:
            return "Available for collection after confirmation."
        if self.min_days == self.max_days:
            return f"{self.min_days} day(s)"
        return f"{self.min_days}-{self.max_days} days"

    def fee_for(self, subtotal):
        if self.free_above_amount is not None and subtotal >= self.free_above_amount:
            from decimal import Decimal
            return Decimal("0.00")
        return self.fee
