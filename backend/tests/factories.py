"""
Shared test factories.

These build real database rows through the same services the API uses — no
mocked persistence, so the tests exercise actual constraints, transactions and
inventory behaviour.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.categories.models import Category
from apps.core.models import PublishableModel
from apps.cms.services import SettingsService
from apps.inventory.services import InventoryService
from apps.products.models import (
    Product, ProductAttribute, ProductAttributeValue, ProductVariation,
)
from apps.shipping.models import ShippingArea, ShippingMethod, ShippingZone

User = get_user_model()

_counter = {"n": 0}


def uniq(prefix: str = "x") -> str:
    _counter["n"] += 1
    return f"{prefix}{_counter['n']}-{uuid.uuid4().hex[:6]}"


def make_settings():
    """Seeds business settings so CMS/SEO lookups behave like production."""
    SettingsService.seed_defaults()


def make_staff(superuser: bool = True, email: str | None = None):
    email = email or f"staff-{uniq()}@starmond.test"
    if superuser:
        return User.objects.create_superuser(email=email, password="TestPassw0rd!2026")
    return User.objects.create_user(email=email, password="TestPassw0rd!2026", is_staff=True)


def make_customer(email: str | None = None, verified: bool = True):
    user = User.objects.create_user(
        email=email or f"cust-{uniq()}@example.com",
        password="TestPassw0rd!2026",
        first_name="Ada",
        last_name="Okafor",
    )
    if verified:
        user.mark_email_verified()
    return user


def make_category(name: str | None = None, parent: Category | None = None,
                  published: bool = True) -> Category:
    name = name or f"Category {uniq()}"
    from apps.core.utils import unique_slug

    category = Category.objects.create(
        name=name,
        slug=unique_slug(Category, name),
        parent=parent,
        status=PublishableModel.Status.PUBLISHED if published else PublishableModel.Status.DRAFT,
        published_at=timezone.now() if published else None,
        is_active=True,
    )
    category.refresh_from_db()
    return category


def make_product(name: str | None = None, category: Category | None = None,
                 price="10000.00", stock: int = 20, published: bool = True,
                 sku: str | None = None) -> Product:
    category = category or make_category()
    name = name or f"Product {uniq()}"
    product = Product.objects.create(
        name=name,
        slug=f"{name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:8]}",
        sku=(sku or f"SKU-{uuid.uuid4().hex[:10].upper()}"),
        category=category,
        price=Decimal(str(price)),
        status=PublishableModel.Status.PUBLISHED if published else PublishableModel.Status.DRAFT,
        published_at=timezone.now() if published else None,
        short_description="A dependable product for everyday use.",
        description="Long form description of the product for the catalogue.",
    )
    InventoryService.get_or_create_for(product, None, opening_quantity=stock)
    return product


def make_variation(product: Product, label: str = "Large", price="12000.00",
                   stock: int = 10) -> ProductVariation:
    attribute, _ = ProductAttribute.objects.get_or_create(
        name="Size", defaults={"slug": "size", "is_variation_axis": True}
    )
    value, _ = ProductAttributeValue.objects.get_or_create(
        attribute=attribute, value=label,
        defaults={"slug": label.lower().replace(" ", "-")},
    )
    variation = ProductVariation.objects.create(
        product=product,
        sku=f"{product.sku}-{label[:3].upper()}-{uuid.uuid4().hex[:6].upper()}",
        price_override=Decimal(str(price)) if price else None,
    )
    variation.attribute_values.add(value)
    product.is_variation_based = True
    product.save(update_fields=["is_variation_based", "updated_at"])
    InventoryService.get_or_create_for(product, variation, opening_quantity=stock)
    return variation


def make_shipping_zone(state: str = "Enugu", price="1800.00", free_over=None):
    zone, created = ShippingZone.objects.get_or_create(
        name=f"Test zone {state}",
        defaults={"slug": f"test-zone-{state.lower()}-{uuid.uuid4().hex[:4]}"},
    )
    ShippingArea.objects.get_or_create(zone=zone, state=state, city="")
    ShippingMethod.objects.get_or_create(
        zone=zone,
        code="standard",
        defaults={
            "name": "Standard delivery",
            "price": Decimal(str(price)),
            "estimated_days_min": 2,
            "estimated_days_max": 4,
            "free_over_amount": Decimal(str(free_over)) if free_over else None,
        },
    )
    return zone


def make_promotion(**kwargs):
    from apps.promotions.models import Promotion

    defaults = {
        "name": f"Promo {uniq()}",
        "code": f"PROMO{uniq()}".upper()[:20],
        "promotion_type": Promotion.Type.PERCENTAGE,
        "value": Decimal("10.00"),
        "is_active": True,
        "starts_at": timezone.now() - timezone.timedelta(days=1),
    }
    defaults.update(kwargs)
    return Promotion.objects.create(**defaults)


def shipping_payload(state: str = "Enugu") -> dict:
    return {
        "full_name": "Ada Okafor",
        "phone": "+2348012345678",
        "address_line": "12 Ogui Road",
        "apartment": "",
        "city": "Enugu",
        "state": state,
        "lga": "Enugu North",
        "postal_code": "400001",
        "country": "Nigeria",
        "delivery_instructions": "",
    }


def paystack_success_payload(reference: str, amount_kobo: int, currency: str = "NGN",
                             status: str = "success") -> dict:
    return {
        "status": True,
        "message": "Verification successful",
        "data": {
            "id": 302961,
            "reference": reference,
            "amount": amount_kobo,
            "currency": currency,
            "status": status,
            "channel": "card",
            "gateway_response": "Successful" if status == "success" else "Declined",
            "paid_at": timezone.now().isoformat(),
            "customer": {"email": "cust@example.com", "customer_code": "CUS_x", "phone": None},
            "authorization": {
                "authorization_code": "AUTH_123", "bin": "408408", "last4": "4081",
                "exp_month": "12", "exp_year": "2030", "card_type": "visa",
                "bank": "Test Bank", "channel": "card", "brand": "visa", "reusable": True,
                "signature": "SIG",
            },
        },
    }
