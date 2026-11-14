"""PricingService — the ONLY source of truth for money.

All amounts are Decimal. Client-submitted prices, totals and discounts are
NEVER trusted; every figure is recomputed from the database on each call.
"""
from decimal import Decimal

from apps.core.money import ZERO, to_decimal


class PricingService:
    @staticmethod
    def unit_price(product, variation=None):
        return variation.effective_price if variation else product.effective_price

    @classmethod
    def cart_lines(cls, cart):
        lines = []
        for item in cart.items.select_related("product__category", "variation"):
            if not item.product.is_public:
                continue  # silently drop delisted items; checkout re-validates hard
            if item.variation and not item.variation.is_available:
                continue
            unit = cls.unit_price(item.product, item.variation)
            lines.append({
                "product": item.product, "variation": item.variation,
                "quantity": item.quantity, "unit_price": unit,
                "line_total": to_decimal(unit * item.quantity),
                "cart_item_id": item.pk,
            })
        return lines

    @classmethod
    def price_lines(cls, lines, *, promotion_code=None, customer=None, shipping_method_id=None,
                    shipping_state=None, check_usage=True):
        subtotal = sum((l["line_total"] for l in lines), ZERO)
        discount, promotion = ZERO, None
        if promotion_code:
            from apps.promotions.services import PromotionService
            promotion, discount = PromotionService.validate(
                promotion_code, lines=lines, subtotal=subtotal, customer=customer, check_usage=check_usage)
        shipping_fee, shipping_method = ZERO, None
        if shipping_method_id and shipping_state:
            from apps.shipping.services import ShippingService
            shipping_method, shipping_fee = ShippingService.quote(shipping_method_id, shipping_state, subtotal - discount)
        total = to_decimal(subtotal - discount + shipping_fee)
        return {
            "lines": lines,
            "subtotal": to_decimal(subtotal),
            "discount": to_decimal(discount),
            "shipping_fee": to_decimal(shipping_fee),
            "total": total,
            "promotion": promotion,
            "shipping_method": shipping_method,
            "currency": "NGN",
        }

    @classmethod
    def price_cart(cls, cart, **kwargs):
        lines = cls.cart_lines(cart)
        priced = cls.price_lines(lines, **kwargs)
        priced["item_count"] = sum(l["quantity"] for l in lines)
        return priced

    @classmethod
    def price_buy_now(cls, product, variation, quantity, **kwargs):
        unit = cls.unit_price(product, variation)
        lines = [{
            "product": product, "variation": variation, "quantity": quantity,
            "unit_price": unit, "line_total": to_decimal(unit * quantity), "cart_item_id": None,
        }]
        priced = cls.price_lines(lines, **kwargs)
        priced["item_count"] = quantity
        return priced
