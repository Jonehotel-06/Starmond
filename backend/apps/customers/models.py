"""Customer profiles, saved addresses, wishlists and one-time action tokens."""
from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import BaseModel, TimeStampedModel, UUIDModel


class CustomerProfile(TimeStampedModel):
    """Commerce-specific data for a customer account."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="customer_profile"
    )
    default_shipping_address = models.ForeignKey(
        "customers.Address", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="default_for_shipping",
    )
    date_of_birth = models.DateField(null=True, blank=True)
    order_count = models.PositiveIntegerField(default=0, editable=False)
    lifetime_value = models.DecimalField(max_digits=14, decimal_places=2, default=0, editable=False)

    # notification preferences
    notify_order_updates = models.BooleanField(default=True)
    notify_promotions = models.BooleanField(default=False)
    notify_newsletter = models.BooleanField(default=False)
    notify_sms = models.BooleanField(default=False)

    class Meta:
        db_table = "customers_profile"

    def __str__(self) -> str:
        return f"Profile<{self.user_id}>"


class Address(BaseModel):
    """A customer's saved delivery address. Only its owner may read or change it."""

    class Label(models.TextChoices):
        HOME = "home", "Home"
        WORK = "work", "Work"
        OTHER = "other", "Other"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="addresses"
    )
    label = models.CharField(max_length=20, choices=Label.choices, default=Label.HOME)
    recipient_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=16)
    email = models.EmailField(blank=True)
    street_address = models.CharField(max_length=255)
    apartment = models.CharField(max_length=120, blank=True)
    city = models.CharField(max_length=80, db_index=True)
    state = models.CharField(max_length=80, db_index=True)
    lga = models.CharField(max_length=80, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=80, default="Nigeria")
    delivery_instructions = models.TextField(blank=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        db_table = "customers_address"
        ordering = ["-is_default", "-created_at"]
        indexes = [models.Index(fields=["user", "is_default"])]

    def __str__(self) -> str:
        return f"{self.recipient_name} — {self.city}, {self.state}"

    def save(self, *a, **kw):
        super().save(*a, **kw)
        if self.is_default:
            Address.objects.filter(user=self.user, is_default=True).exclude(pk=self.pk).update(
                is_default=False
            )

    @property
    def one_line(self) -> str:
        parts = [self.street_address, self.apartment, self.city, self.state, self.country]
        return ", ".join(p for p in parts if p)


class Wishlist(TimeStampedModel):
    """One active wishlist per authenticated customer."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wishlist"
    )

    class Meta:
        db_table = "customers_wishlist"

    def __str__(self) -> str:
        return f"Wishlist<{self.user_id}>"

    @property
    def item_count(self) -> int:
        return self.items.count()


class WishlistItem(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wishlist = models.ForeignKey(Wishlist, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("products.Product", on_delete=models.CASCADE, related_name="wishlist_items")
    variation = models.ForeignKey(
        "products.ProductVariation", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="wishlist_items",
    )

    class Meta:
        db_table = "customers_wishlist_item"
        constraints = [
            models.UniqueConstraint(fields=["wishlist", "product"], name="uniq_wishlist_product"),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.product_id} in wishlist"


class OneTimeToken(UUIDModel, TimeStampedModel):
    """
    Single-use, expiring token for email verification, password reset and
    signed guest-order access. Only the hash is stored.
    """

    class Purpose(models.TextChoices):
        EMAIL_VERIFICATION = "email_verification", "Email verification"
        PASSWORD_RESET = "password_reset", "Password reset"
        GUEST_ORDER_ACCESS = "guest_order_access", "Guest order access"
        EMAIL_CHANGE = "email_change", "Email change"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE,
        related_name="one_time_tokens",
    )
    guest_email = models.EmailField(blank=True)
    purpose = models.CharField(max_length=30, choices=Purpose.choices, db_index=True)
    token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    target_reference = models.CharField(max_length=64, blank=True, db_index=True)
    expires_at = models.DateTimeField(db_index=True)
    used_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = "customers_one_time_token"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["purpose", "expires_at"])]

    def __str__(self) -> str:
        return f"{self.purpose} token"

    @property
    def is_valid(self) -> bool:
        return self.used_at is None and self.expires_at > timezone.now()

    def consume(self) -> bool:
        """Atomically marks the token used. Returns False if it was already spent."""
        updated = OneTimeToken.objects.filter(pk=self.pk, used_at__isnull=True).update(
            used_at=timezone.now()
        )
        return bool(updated)
