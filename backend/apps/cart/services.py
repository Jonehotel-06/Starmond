"""
CartService — guest and customer carts with merge support.

Design notes
------------
* A guest cart is identified by an unguessable UUID ``token`` sent in the
  ``X-Cart-Token`` header (or held in the session).
* Adding the same product/variation twice increments the existing line rather
  than creating a duplicate (Section 45 rule 6).
* Quantities are validated against live availability on every write.
* Nothing about price is trusted from the client.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.cart.models import Cart, CartItem
from apps.core.exceptions import ConflictError, NotFound, ValidationError
from apps.core.models import PublishableModel
from apps.core.utils import positive_int
from apps.inventory.services import InventoryService
from apps.orders.pricing import BasketLine, PriceBreakdown, PricingService
from apps.products.models import Product, ProductVariation

logger = logging.getLogger("apps.cart")

CART_TOKEN_HEADER = "HTTP_X_CART_TOKEN"
CART_TOKEN_SESSION_KEY = "starmond_cart_token"
CART_LIFETIME_DAYS = 30


class CartService:
    # ------------------------------------------------------------------
    # Retrieval / creation
    # ------------------------------------------------------------------
    @staticmethod
    def get_for_request(request, *, create: bool = True) -> Cart | None:
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            cart = Cart.objects.filter(
                user=user, status=Cart.Status.ACTIVE
            ).order_by("-created_at").first()
            if cart is None and create:
                cart = Cart.objects.create(user=user)
            return cart

        token = request.META.get(CART_TOKEN_HEADER) or request.session.get(CART_TOKEN_SESSION_KEY)
        if token:
            try:
                cart = Cart.objects.filter(token=token, status=Cart.Status.ACTIVE).first()
            except (ValueError, TypeError):
                cart = None
            if cart is not None:
                return cart

        if not create:
            return None
        cart = Cart.objects.create()
        request.session[CART_TOKEN_SESSION_KEY] = str(cart.token)
        return cart

    @staticmethod
    def bind_token(request, cart: Cart) -> None:
        request.session[CART_TOKEN_SESSION_KEY] = str(cart.token)

    @staticmethod
    def load(cart, *, authenticated: bool = False) -> Cart:
        return cart

    # ------------------------------------------------------------------
    # Line mutations
    # ------------------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def add_item(
        cart: Cart,
        *,
        product_id: str,
        variation_id: str | None = None,
        quantity=1,
        custom_order_details: dict | None = None,
        replace: bool = False,
    ) -> CartItem:
        if cart.status != Cart.Status.ACTIVE:
            raise ConflictError("This cart is no longer active. Please start a new cart.")

        quantity = positive_int(
            quantity, "quantity", minimum=1, maximum=settings.MAX_CART_ITEM_QUANTITY
        )

        product = (
            Product.objects.select_related("category")
            .filter(pk=product_id, deleted_at__isnull=True)
            .first()
        )
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
        elif product.is_variation_based or product.variations.filter(is_active=True).exists():
            raise ValidationError("Please choose a product option before adding to cart.")

        if product.custom_order_enabled and not custom_order_details:
            if product.custom_order_instructions:
                raise ValidationError(
                    "Please provide your custom order details: "
                    + product.custom_order_instructions
                )

        existing = cart.items.filter(product=product, variation=variation).first()
        target_quantity = quantity if replace else (existing.quantity + quantity if existing else quantity)

        if target_quantity > settings.MAX_CART_ITEM_QUANTITY:
            raise ValidationError(
                f"You may order at most {settings.MAX_CART_ITEM_QUANTITY} units of this item."
            )

        available = InventoryService.available_quantity(product, variation)
        if available < target_quantity:
            raise ConflictError(
                f"Only {available} unit(s) of {product.name} are available right now.",
                details={
                    "product_id": str(product.pk),
                    "variation_id": str(variation.pk) if variation else None,
                    "requested": target_quantity,
                    "available": available,
                },
            )

        if existing is None:
            if cart.items.count() >= settings.MAX_CART_LINES:
                raise ConflictError(
                    f"A cart may hold at most {settings.MAX_CART_LINES} different items."
                )
        elif existing is not None:
            existing.quantity = target_quantity
            existing.custom_order_details = custom_order_details or existing.custom_order_details
            existing.save(update_fields=["quantity", "custom_order_details", "updated_at"])
            cart.touch()
            return existing

        item = CartItem.objects.create(
            cart=cart,
            product=product,
            variation=variation,
            quantity=target_quantity,
            unit_price_at_add=PricingService.build_line(
                product=product, variation=variation, quantity=target_quantity
            ).unit_price,
            custom_order_details=custom_order_details or {},
        )
        cart.touch()
        return item

    @staticmethod
    @transaction.atomic
    def update_item(cart: Cart, *, item_id: str, quantity) -> CartItem:
        item = cart.items.select_related("product", "variation").filter(pk=item_id).first()
        if item is None:
            raise NotFound("That item is not in your cart.")
        quantity = positive_int(
            quantity, "quantity", minimum=1, maximum=settings.MAX_CART_ITEM_QUANTITY
        )
        available = InventoryService.available_quantity(item.product, item.variation)
        if available < quantity:
            raise ConflictError(
                f"Only {available} unit(s) of {item.product.name} are available right now.",
                details={"requested": quantity, "available": available},
            )
        item.quantity = quantity
        item.save(update_fields=["quantity", "updated_at"])
        cart.touch()
        return item

    @staticmethod
    @transaction.atomic
    def remove_item(cart: Cart, *, item_id: str) -> None:
        item = cart.items.filter(pk=item_id).first()
        if item is None:
            raise NotFound("That item is not in your cart.")
        item.delete()
        cart.touch()

    @staticmethod
    @transaction.atomic
    def clear(cart: Cart) -> None:
        cart.items.all().delete()
        cart.applied_codes = []
        cart.save(update_fields=["applied_codes", "updated_at"])
        cart.touch()

    @staticmethod
    @transaction.atomic
    def apply_code(cart: Cart, code: str) -> Cart:
        code = (code or "").strip().upper()
        if not code:
            raise ValidationError("Enter a discount code.")
        codes = [c for c in (cart.applied_codes or []) if c != code]
        if len(codes) >= 3:
            raise ValidationError("A maximum of three promotion codes may be applied.")
        cart.applied_codes = codes + [code]
        cart.save(update_fields=["applied_codes", "updated_at"])
        cart.touch()
        return cart

    @staticmethod
    @transaction.atomic
    def remove_code(cart: Cart, code: str) -> Cart:
        code = (code or "").strip().upper()
        cart.applied_codes = [c for c in (cart.applied_codes or []) if c != code]
        cart.save(update_fields=["applied_codes", "updated_at"])
        cart.touch()
        return cart

    # ------------------------------------------------------------------
    # Merge on login
    # ------------------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def merge_guest_cart(request, user) -> tuple[Cart | None, dict]:
        """
        Merges the guest cart into the customer's cart the moment they sign in.

        Quantities are combined and capped at live availability; the guest cart
        is archived rather than deleted so the merge stays auditable.
        """
        guest_token = request.session.get(CART_TOKEN_SESSION_KEY)
        if not guest_token:
            return (Cart.objects.filter(user=user, status=Cart.Status.ACTIVE).first(), {})
        guest_cart = Cart.objects.filter(
            token=guest_token, status=Cart.Status.ACTIVE, user__isnull=True
        ).first()
        if guest_cart is None:
            return (Cart.objects.filter(user=user, status=Cart.Status.ACTIVE).first(), {})

        target, _ = Cart.objects.get_or_create(user=user, status=Cart.Status.ACTIVE)
        merged, skipped = 0, []
        for item in guest_cart.items.select_related("product", "variation"):
            if item.product.status != PublishableModel.Status.PUBLISHED:
                skipped.append({"product": item.product.name, "reason": "no longer available"})
                continue
            available = InventoryService.available_quantity(item.product, item.variation)
            existing = target.items.filter(product=item.product, variation=item.variation).first()
            desired = (existing.quantity if existing else 0) + item.quantity
            capped = min(desired, available, settings.MAX_CART_ITEM_QUANTITY)
            if capped <= 0:
                skipped.append({"product": item.product.name, "reason": "out of stock"})
                continue
            if existing is not None:
                existing.quantity = capped
                existing.save(update_fields=["quantity", "updated_at"])
            else:
                CartItem.objects.create(
                    cart=target,
                    product=item.product,
                    variation=item.variation,
                    quantity=capped,
                    unit_price_at_add=item.unit_price_at_add,
                    custom_order_details=item.custom_order_details,
                )
            merged += 1

        for code in guest_cart.applied_codes or []:
            if code not in (target.applied_codes or []):
                target.applied_codes = (target.applied_codes or []) + [code]
        target.save(update_fields=["applied_codes", "updated_at"])

        guest_cart.status = Cart.Status.MERGED
        guest_cart.save(update_fields=["status", "updated_at"])
        request.session[CART_TOKEN_SESSION_KEY] = str(target.token)
        target.touch()
        return target, {"merged_lines": merged, "skipped": skipped}

    # ------------------------------------------------------------------
    # Read paths
    # ------------------------------------------------------------------
    @staticmethod
    def basket_lines(cart: Cart) -> list[BasketLine]:
        """Converts cart rows into priced lines using current catalogue data."""
        lines: list[BasketLine] = []
        items = cart.items.select_related("product", "product__category", "variation").filter(
            product__status=PublishableModel.Status.PUBLISHED, product__deleted_at__isnull=True
        )
        for item in items:
            lines.append(
                PricingService.build_line(
                    product=item.product,
                    variation=item.variation,
                    quantity=item.quantity,
                    custom_order_details=item.custom_order_details,
                    cart_item_id=str(item.pk),
                )
            )
        return lines

    @staticmethod
    def summary(
        cart: Cart,
        *,
        shipping_state: str = "",
        shipping_city: str = "",
        shipping_method_code: str | None = None,
        user=None,
        email: str = "",
    ) -> dict:
        lines = CartService.basket_lines(cart)
        user = user or cart.user
        breakdown: PriceBreakdown = PricingService.price_basket(
            lines,
            promo_codes=cart.applied_codes or [],
            shipping_state=shipping_state,
            shipping_city=shipping_city,
            shipping_method_code=shipping_method_code,
            user=user,
            email=email or (getattr(user, "email", "") if user else cart.guest_email),
            currency=cart.currency,
        )
        payload = breakdown.as_dict()
        payload["cart"] = {
            "id": str(cart.id),
            "token": str(cart.token),
            "item_count": cart.item_count,
            "line_count": cart.line_count,
            "applied_codes": cart.applied_codes or [],
            "status": cart.status,
        }
        payload["lines"] = CartService._lines_with_availability(cart, breakdown)
        return payload

    @staticmethod
    def _lines_with_availability(cart: Cart, breakdown: PriceBreakdown) -> list[dict]:
        priced = {ln["cart_item_id"]: ln for ln in breakdown.lines}
        output = []
        for item in cart.items.select_related("product", "variation"):
            base = priced.get(str(item.pk), {})
            available = InventoryService.available_quantity(item.product, item.variation)
            output.append(
                base
                | {
                    "cart_item_id": str(item.pk),
                    "product_slug": item.product.slug,
                    "image": (item.product.primary_image.image.url
                              if item.product.primary_image else None),
                    "available_quantity": available,
                    "stock_status": InventoryService.stock_status_for(
                        item.product, item.variation
                    ),
                    "quantity_in_stock": available >= item.quantity,
                    "custom_order_details": item.custom_order_details or {},
                    "custom_order_enabled": item.product.custom_order_enabled,
                }
            )
        return output

    @staticmethod
    def mark_converted(cart: Cart, order) -> None:
        cart.status = Cart.Status.CONVERTED
        cart.save(update_fields=["status", "updated_at"])
        CartItem.objects.filter(cart=cart).delete()

    @staticmethod
    def purge_abandoned(days: int = CART_LIFETIME_DAYS) -> int:
        cutoff = timezone.now() - timezone.timedelta(days=days)
        updated = Cart.objects.filter(
            status=Cart.Status.ACTIVE, last_activity_at__lt=cutoff
        ).update(status=Cart.Status.ABANDONED, updated_at=timezone.now())
        return updated
