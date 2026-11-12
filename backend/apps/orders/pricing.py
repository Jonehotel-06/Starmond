"""
PricingService — the single authority on what a customer will be charged.

Every figure produced here is derived from database records:

* unit prices come from ``Product`` / ``ProductVariation``;
* discounts come from ``PromotionService`` (re-validated on every call);
* shipping comes from ``ShippingService`` (destination-driven);
* totals are recomputed from scratch — a client-submitted total is never read.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal

from apps.core.utils import money
from apps.promotions.services import DiscountResult, PromotionService
from apps.shipping.services import DeliveryQuote, ShippingService

logger = logging.getLogger("apps.pricing")


@dataclass
class BasketLine:
    """A validated, priced line. Constructed only from database records."""

    product_id: str
    variation_id: str | None
    category_id: str
    name: str
    sku: str
    variation_label: str
    quantity: int
    unit_price: Decimal
    compare_at_price: Decimal | None = None
    tax_rate_percent: Decimal = Decimal("0")
    requires_shipping: bool = True
    is_heavy: bool = False
    custom_order_details: dict = field(default_factory=dict)
    cart_item_id: str | None = None

    @property
    def line_subtotal(self) -> Decimal:
        return money(self.unit_price * self.quantity)

    def as_dict(self) -> dict:
        return {
            "cart_item_id": self.cart_item_id,
            "product_id": self.product_id,
            "variation_id": self.variation_id,
            "name": self.name,
            "sku": self.sku,
            "variation_label": self.variation_label,
            "quantity": self.quantity,
            "unit_price": str(money(self.unit_price)),
            "compare_at_price": str(money(self.compare_at_price)) if self.compare_at_price else None,
            "line_subtotal": str(self.line_subtotal),
        }


@dataclass
class PriceBreakdown:
    """The complete, authoritative money picture for a basket."""

    lines: list[dict]
    subtotal: Decimal
    discount_total: Decimal
    shipping_total: Decimal
    tax_total: Decimal
    grand_total: Decimal
    applied_discounts: list[dict]
    shipping: dict
    shipping_eligible: bool
    currency: str = "NGN"
    messages: list[str] = field(default_factory=list)

    @property
    def total_due(self) -> Decimal:
        return self.grand_total

    def as_dict(self) -> dict:
        return {
            "currency": self.currency,
            "lines": self.lines,
            "subtotal": str(money(self.subtotal)),
            "discount_total": str(money(self.discount_total)),
            "shipping_total": str(money(self.shipping_total)),
            "tax_total": str(money(self.tax_total)),
            "grand_total": str(money(self.grand_total)),
            "applied_discounts": self.applied_discounts,
            "shipping": self.shipping,
            "shipping_eligible": self.shipping_eligible,
            "messages": self.messages,
        }


def _compare_at_price(product, variation):
    """Display-only 'was' price: variation override wins, then the product's."""
    if variation is not None and variation.compare_at_price is not None:
        return money(variation.compare_at_price)
    if product.compare_at_price is not None:
        return money(product.compare_at_price)
    return None


class PricingService:
    @staticmethod
    def build_line(*, product, variation=None, quantity: int = 1,
                   custom_order_details: dict | None = None, cart_item_id=None) -> BasketLine:
        """Builds a priced line straight from the catalogue — no client input."""
        if variation is not None and variation.product_id != product.pk:
            raise ValueError("Variation does not belong to the selected product.")
        unit_price = variation.effective_price if variation is not None else product.price
        return BasketLine(
            product_id=str(product.pk),
            variation_id=str(variation.pk) if variation is not None else None,
            category_id=str(product.category_id),
            name=product.name,
            sku=variation.sku if variation is not None else product.sku,
            variation_label=variation.label if variation is not None else "",
            quantity=int(quantity),
            unit_price=money(unit_price),
            compare_at_price=_compare_at_price(product, variation),
            tax_rate_percent=money(product.tax_rate_percent),
            requires_shipping=product.requires_shipping,
            is_heavy=product.is_heavy,
            custom_order_details=custom_order_details or {},
            cart_item_id=cart_item_id,
        )

    @staticmethod
    def price_basket(
        lines: list[BasketLine],
        *,
        promo_codes: list[str] | None = None,
        shipping_state: str = "",
        shipping_city: str = "",
        shipping_method_code: str | None = None,
        user=None,
        email: str = "",
        currency: str = "NGN",
        include_automatic_promotions: bool = True,
    ) -> PriceBreakdown:
        """
        Prices a basket end-to-end.

        Called by the cart summary, the checkout preview and order creation, so
        the number the customer sees is always the number that gets charged.
        """
        promo_codes = [c.strip().upper() for c in (promo_codes or []) if c and c.strip()]
        messages: list[str] = []
        dict_lines = [
            {
                "product_id": ln.product_id,
                "variation_id": ln.variation_id,
                "category_id": ln.category_id,
                "unit_price": ln.unit_price,
                "quantity": ln.quantity,
            }
            for ln in lines
        ]

        subtotal = money(sum(ln.line_subtotal for ln in lines))
        requires_shipping = any(ln.requires_shipping for ln in lines)
        is_heavy = any(ln.is_heavy for ln in lines)

        # ---- shipping ----------------------------------------------------
        if not lines:
            quote = DeliveryQuote(
                eligible=True, method_id=None, method_name="", method_code="",
                zone_name="", fee=Decimal("0.00"), estimated_days_min=0,
                estimated_days_max=0, is_pickup=False,
                reason="Add an item to see delivery options.",
            )
        elif requires_shipping:
            quote: DeliveryQuote = ShippingService.quote(
                state=shipping_state,
                city=shipping_city,
                subtotal=subtotal,
                item_count=sum(ln.quantity for ln in lines),
                is_heavy=is_heavy,
                method_code=shipping_method_code,
            )
        else:
            quote = DeliveryQuote(
                eligible=True, method_id=None, method_name="Digital delivery",
                method_code="digital", zone_name="Digital", fee=Decimal("0.00"),
                estimated_days_min=0, estimated_days_max=0, is_pickup=False,
            )

        shipping_fee = money(quote.fee)

        # ---- promotions --------------------------------------------------
        applied: list[DiscountResult] = []
        seen_promotions: list = []

        for code in promo_codes:
            result = PromotionService.validate_code(
                code=code, lines=dict_lines, subtotal=subtotal, shipping_fee=shipping_fee,
                user=user, email=email, existing=seen_promotions,
            )
            if result.message:
                messages.append(result.message)
            if result.applied:
                applied.append(result)
                from apps.promotions.models import Promotion

                promo = Promotion.objects.filter(pk=result.promotion_id).first()
                if promo is not None:
                    seen_promotions.append(promo)

        if include_automatic_promotions and not applied:
            applied = PromotionService.automatic_promotions(
                lines=dict_lines, subtotal=subtotal, shipping_fee=shipping_fee,
                user=user, email=email,
            )

        # ---- discount maths ----------------------------------------------
        free_shipping = any(r.free_shipping for r in applied)
        discount_total = money(sum(r.discount_amount for r in applied))
        discount_total = min(discount_total, subtotal)
        if free_shipping:
            shipping_fee = Decimal("0.00")

        # ---- tax ---------------------------------------------------------
        tax_total = money(
            sum(
                ln.unit_price * ln.quantity * ln.tax_rate_percent / Decimal("100")
                for ln in lines
            )
        )

        grand_total = money(subtotal - discount_total + shipping_fee + tax_total)

        return PriceBreakdown(
            lines=[ln.as_dict() for ln in lines],
            subtotal=subtotal,
            discount_total=money(discount_total),
            shipping_total=money(shipping_fee),
            tax_total=tax_total,
            grand_total=grand_total,
            applied_discounts=[r.as_dict() | {"free_shipping": r.free_shipping} for r in applied],
            shipping=quote.as_dict(),
            shipping_eligible=quote.eligible,
            currency=currency,
            messages=messages,
        )

    @staticmethod
    def allocate_line_discounts(lines: list[BasketLine], discount_total: Decimal) -> list[Decimal]:
        """
        Spreads an order-level discount across lines proportionally so each line keeps
        an accurate ``discount_allocated`` for refunds and margin reporting.
        """
        subtotal = sum(ln.line_subtotal for ln in lines)
        allocations: list[Decimal] = []
        if subtotal <= 0 or discount_total <= 0:
            return [Decimal("0.00") for _ in lines]

        running = Decimal("0.00")
        for index, line in enumerate(lines):
            if index == len(lines) - 1:
                share = money(discount_total) - running  # absorb rounding
            else:
                share = money(money(discount_total) * line.line_subtotal / subtotal)
                running += share
            allocations.append(max(share, Decimal("0.00")))
        return allocations
