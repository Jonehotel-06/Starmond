"""
CheckoutService — the only two ways an order may come into existence.

``checkout_cart``   : converts the customer's active cart into an order.
``checkout_buy_now``: converts exactly one product/variation into an order and
                      deliberately ignores whatever is sitting in the cart
                      (Section 45 rules 7 and 8).

Both paths share ``PricingService``, ``ShippingService`` and
``InventoryService``, so they cannot diverge on price, delivery or stock.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from django.db import transaction

from apps.cart.models import Cart
from apps.cart.services import CartService
from apps.core.exceptions import ConflictError, NotFound, ValidationError
from apps.core.idempotency import IdempotentRunner, fingerprint, lookup_completed
from apps.core.models import PublishableModel
from apps.core.utils import positive_int
from apps.inventory.services import InventoryService
from apps.orders.models import Order
from apps.orders.pricing import BasketLine, PriceBreakdown, PricingService
from apps.orders.services import OrderService
from apps.products.models import Product, ProductVariation
from apps.shipping.services import ShippingService

logger = logging.getLogger("apps.checkout")


@dataclass
class CheckoutResult:
    order: Order
    breakdown: PriceBreakdown
    replayed: bool = False


class CheckoutService:
    # ------------------------------------------------------------------
    # Shared internals
    # ------------------------------------------------------------------
    @staticmethod
    def _resolve_shipping(state: str, city: str, method_code: str | None):
        """Validates the destination before any order row is written."""
        if not (state or "").strip():
            raise ValidationError("A delivery state is required to calculate shipping.")
        return ShippingService.quote(state=state, city=city, method_code=method_code)

    @staticmethod
    def _validate_contact(customer, guest_email: str, shipping: dict) -> None:
        import re

        email = (guest_email or getattr(customer, "email", "") or "").strip()
        if not email or not re.match(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$", email):
            raise ValidationError({"email": ["A valid email address is required."]})
        for field, label in (("full_name", "Full name"), ("phone", "Phone number"),
                             ("address_line", "Street address"), ("city", "City"),
                             ("state", "State")):
            if not str(shipping.get(field, "")).strip():
                raise ValidationError({field: [f"{label} is required."]})

    # ------------------------------------------------------------------
    # Cart checkout
    # ------------------------------------------------------------------
    @staticmethod
    def checkout_cart(
        *,
        cart: Cart,
        shipping: dict,
        customer=None,
        guest_email: str = "",
        guest_phone: str = "",
        customer_note: str = "",
        shipping_method_code: str | None = None,
        promo_codes: list[str] | None = None,
        source_ip: str | None = None,
        user_agent: str = "",
        idempotency_key: str | None = None,
    ) -> CheckoutResult:
        """Converts the active cart into an order."""
        scope = f"checkout_cart:{customer.pk if customer else (guest_email or '').lower()}"
        replay = lookup_completed(scope, idempotency_key)
        if replay is not None:
            order = Order.objects.filter(
                order_number=(replay.response_body or {}).get("order_number")
            ).first()
            if order is not None:
                return CheckoutResult(
                    order=order,
                    breakdown=PricingService.price_basket(
                        [], shipping_state=str(shipping.get("state", ""))
                    ),
                    replayed=True,
                )

        if cart.status != Cart.Status.ACTIVE:
            raise ConflictError("This cart is no longer active.")
        if not cart.items.exists():
            raise ValidationError("Your cart is empty.")

        CheckoutService._validate_contact(customer, guest_email, shipping)

        codes = [c.strip().upper() for c in (promo_codes if promo_codes is not None
                                             else (cart.applied_codes or [])) if c and c.strip()]
        lines = CartService.basket_lines(cart)
        if not lines:
            raise ValidationError("The items in your cart are no longer available.")

        state = str(shipping.get("state", "")).strip()
        city = str(shipping.get("city", "")).strip()
        email = (guest_email or getattr(customer, "email", "") or "").strip().lower()

        payload_for_key = {
            "cart": str(cart.id),
            "state": state,
            "city": city,
            "lines": [(ln.product_id, ln.variation_id, ln.quantity) for ln in lines],
            "codes": codes,
        }

        with transaction.atomic():
            runner = IdempotentRunner(
                scope=scope,
                key=idempotency_key,
                payload=fingerprint(payload_for_key),
                actor=customer,
            )
            with runner:
                if runner.replayed:
                    body, _ = runner.replayed_response
                    order = Order.objects.filter(
                        order_number=(body or {}).get("order_number")
                    ).first()
                    if order is None:
                        raise ConflictError("This checkout was already processed.")
                    breakdown = PricingService.price_basket(
                        lines, promo_codes=codes, shipping_state=state, shipping_city=city,
                        shipping_method_code=shipping_method_code, user=customer, email=email,
                        currency=cart.currency,
                    )
                    return CheckoutResult(order=order, breakdown=breakdown, replayed=True)

                breakdown = PricingService.price_basket(
                    lines,
                    promo_codes=codes,
                    shipping_state=state,
                    shipping_city=city,
                    shipping_method_code=shipping_method_code,
                    user=customer,
                    email=email,
                    currency=cart.currency,
                )
                if not breakdown.shipping_eligible:
                    raise ValidationError(
                        breakdown.shipping.get("reason") or "Delivery is unavailable for this address."
                    )

                order = OrderService.create_order(
                    lines=lines,
                    breakdown=breakdown,
                    customer=customer,
                    guest_email=guest_email or email,
                    guest_phone=guest_phone,
                    shipping=shipping,
                    channel=Order.Channel.WEB_CART,
                    cart=cart,
                    customer_note=customer_note,
                    source_ip=source_ip,
                    user_agent=user_agent,
                    idempotency_key=idempotency_key or "",
                    promotion_codes=codes,
                )
                if order.customer_id is None:
                    token = order.new_guest_token()
                    order.save(update_fields=["guest_access_token_hash", "updated_at"])
                    order._plain_guest_token = token  # handed out once, never stored

                CartService.mark_converted(cart, order)

                runner.complete(201, {"order_number": order.order_number},
                                resource_type="order", resource_id=str(order.pk))
                return CheckoutResult(order=order, breakdown=breakdown)

    # ------------------------------------------------------------------
    # Buy Now
    # ------------------------------------------------------------------
    @staticmethod
    def checkout_buy_now(
        *,
        product_id: str,
        variation_id: str | None = None,
        quantity=1,
        shipping: dict,
        customer=None,
        guest_email: str = "",
        guest_phone: str = "",
        customer_note: str = "",
        shipping_method_code: str | None = None,
        promo_codes: list[str] | None = None,
        custom_order_details: dict | None = None,
        source_ip: str | None = None,
        user_agent: str = "",
        idempotency_key: str | None = None,
    ) -> CheckoutResult:
        """
        Direct, cart-independent checkout for a single selected item.

        The customer's existing cart is neither read nor modified — this is the
        explicit guarantee required by Section 45 rule 8.
        """
        scope = f"checkout_buy_now:{customer.pk if customer else (guest_email or '').lower()}"
        replay = lookup_completed(scope, idempotency_key)
        if replay is not None:
            order = Order.objects.filter(
                order_number=(replay.response_body or {}).get("order_number")
            ).first()
            if order is not None:
                return CheckoutResult(
                    order=order,
                    breakdown=PricingService.price_basket(
                        [], shipping_state=str(shipping.get("state", ""))
                    ),
                    replayed=True,
                )

        CheckoutService._validate_contact(customer, guest_email, shipping)
        quantity = positive_int(quantity, "quantity", minimum=1, maximum=50)

        product = Product.objects.select_related("category").filter(
            pk=product_id, deleted_at__isnull=True
        ).first()
        if product is None:
            raise NotFound("Product not found.")
        if product.status != PublishableModel.Status.PUBLISHED:
            raise ValidationError("This product is not currently available for purchase.")

        variation = None
        if variation_id:
            variation = ProductVariation.objects.filter(
                pk=variation_id, product=product, is_active=True
            ).first()
            if variation is None:
                raise ValidationError("The selected product option is not available.")
        elif product.variations.filter(is_active=True).exists():
            raise ValidationError("Please choose a product option first.")

        available = InventoryService.available_quantity(product, variation)
        if available < quantity:
            raise ConflictError(
                f"Only {available} unit(s) of {product.name} are available right now.",
                details={"available": available, "requested": quantity},
            )

        lines = [
            PricingService.build_line(
                product=product,
                variation=variation,
                quantity=quantity,
                custom_order_details=custom_order_details or {},
            )
        ]
        state = str(shipping.get("state", "")).strip()
        city = str(shipping.get("city", "")).strip()
        email = (guest_email or getattr(customer, "email", "") or "").strip().lower()
        codes = [c.strip().upper() for c in (promo_codes or []) if c and c.strip()]

        payload_for_key = {
            "buy_now": True,
            "product": str(product.pk),
            "variation": str(variation.pk) if variation else None,
            "quantity": quantity,
            "state": state,
            "city": city,
            "email": email,
            "codes": codes,
        }

        with transaction.atomic():
            runner = IdempotentRunner(
                scope=scope,
                key=idempotency_key,
                payload=fingerprint(payload_for_key),
                actor=customer,
            )
            with runner:
                if runner.replayed:
                    body, _ = runner.replayed_response
                    order = Order.objects.filter(
                        order_number=(body or {}).get("order_number")
                    ).first()
                    if order is None:
                        raise ConflictError("This checkout was already processed.")
                    breakdown = PricingService.price_basket(
                        lines, promo_codes=codes, shipping_state=state, shipping_city=city,
                        shipping_method_code=shipping_method_code, user=customer, email=email,
                    )
                    return CheckoutResult(order=order, breakdown=breakdown, replayed=True)

                breakdown = PricingService.price_basket(
                    lines,
                    promo_codes=codes,
                    shipping_state=state,
                    shipping_city=city,
                    shipping_method_code=shipping_method_code,
                    user=customer,
                    email=email,
                )
                if not breakdown.shipping_eligible:
                    raise ValidationError(
                        breakdown.shipping.get("reason") or "Delivery is unavailable for this address."
                    )

                order = OrderService.create_order(
                    lines=lines,
                    breakdown=breakdown,
                    customer=customer,
                    guest_email=guest_email or email,
                    guest_phone=guest_phone,
                    shipping=shipping,
                    channel=Order.Channel.BUY_NOW,
                    cart=None,
                    customer_note=customer_note,
                    source_ip=source_ip,
                    user_agent=user_agent,
                    idempotency_key=idempotency_key or "",
                    promotion_codes=codes,
                )
                if order.customer_id is None:
                    token = order.new_guest_token()
                    order.save(update_fields=["guest_access_token_hash", "updated_at"])
                    order._plain_guest_token = token

                runner.complete(201, {"order_number": order.order_number},
                                resource_type="order", resource_id=str(order.pk))
                return CheckoutResult(order=order, breakdown=breakdown)

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------
    @staticmethod
    def preview(
        *,
        cart: Cart | None = None,
        product_id: str | None = None,
        variation_id: str | None = None,
        quantity=1,
        state: str = "",
        city: str = "",
        shipping_method_code: str | None = None,
        promo_codes: list[str] | None = None,
        customer=None,
    ) -> dict:
        """
        Returns the exact figures checkout would produce, without creating
        anything. Used by the frontend's order-review step.
        """
        if product_id:
            product = Product.objects.select_related("category").filter(
                pk=product_id, deleted_at__isnull=True
            ).first()
            if product is None:
                raise NotFound("Product not found.")
            variation = (
                ProductVariation.objects.filter(pk=variation_id, product=product).first()
                if variation_id else None
            )
            lines = [
                PricingService.build_line(
                    product=product, variation=variation,
                    quantity=positive_int(quantity, "quantity", 1, 50),
                )
            ]
            codes = [c.strip().upper() for c in (promo_codes or []) if c and c.strip()]
            email = getattr(customer, "email", "") if customer else ""
        else:
            if cart is None or not cart.items.exists():
                raise ValidationError("Your cart is empty.")
            lines = CartService.basket_lines(cart)
            codes = [c.strip().upper() for c in (
                promo_codes if promo_codes is not None else (cart.applied_codes or [])
            ) if c and c.strip()]
            email = getattr(customer, "email", "") if customer else cart.guest_email

        breakdown = PricingService.price_basket(
            lines,
            promo_codes=codes,
            shipping_state=state,
            shipping_city=city,
            shipping_method_code=shipping_method_code,
            user=customer,
            email=email,
        )
        options = (
            ShippingService.options_for(
                state=state, city=city, subtotal=breakdown.subtotal,
                is_heavy=any(ln.is_heavy for ln in lines),
            )
            if state else []
        )
        payload = breakdown.as_dict()
        payload["shipping_options"] = options
        payload["eligible_states"] = ShippingService.eligible_states()
        return payload
