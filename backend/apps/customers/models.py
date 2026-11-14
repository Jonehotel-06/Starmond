from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel, UUIDModel


class CustomerProfile(TimeStampedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="customer_profile")
    marketing_emails = models.BooleanField(default=True)
    order_update_emails = models.BooleanField(default=True)
    sms_updates = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "customers_profile"

    def __str__(self):
        return f"profile:{self.user.email}"


class Address(UUIDModel, TimeStampedModel):
    class Kind(models.TextChoices):
        SHIPPING = "shipping", "Shipping"
        BILLING = "billing", "Billing"

    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="addresses")
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.SHIPPING)
    label = models.CharField(max_length=60, blank=True)
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30)
    state = models.CharField(max_length=80, db_index=True)
    city = models.CharField(max_length=80)
    street = models.CharField(max_length=255)
    details = models.CharField(max_length=255, blank=True)
    instructions = models.TextField(blank=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        db_table = "customers_address"
        ordering = ["-is_default", "-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["customer", "kind", "is_default"], name="one_default_per_kind",
                                      condition=models.Q(is_default=True)),
        ]

    def __str__(self):
        return f"{self.label or self.kind}: {self.street}, {self.city}"


class Wishlist(TimeStampedModel):
    customer = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wishlist")

    class Meta:
        db_table = "customers_wishlist"

    def __str__(self):
        return f"wishlist:{self.customer.email}"


class WishlistItem(TimeStampedModel):
    wishlist = models.ForeignKey(Wishlist, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("products.Product", on_delete=models.CASCADE, related_name="wishlist_items")

    class Meta:
        db_table = "customers_wishlist_item"
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["wishlist", "product"], name="unique_wishlist_product")]
