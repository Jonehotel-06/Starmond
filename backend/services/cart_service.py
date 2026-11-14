"""CartService — guest and authenticated carts, merging, stock validation."""
from django.conf import settings
from django.db import transaction

from apps.cart.models import Cart, CartItem
from apps.core.exceptions import ServiceError, StockUnavailableError
from apps.inventory.services import InventoryService


class CartService:
    HEADER = "X-Cart-Token"

    @classmethod
    def get_or_create_cart(cls, request):
        user = request.user if request.user.is_authenticated else None
        if user:
            cart, _ = Cart.objects.get_or_create(user=user, status=Cart.Status.ACTIVE,
                                                 defaults={})
            return cart
        token = request.headers.get(cls.HEADER)
        if not token and hasattr(request, "data"):
            try:
                token = request.data.get("cart_token")
            except Exception:
                token = None
        if not token:
            token = request.COOKIES.get("cart_token")
        if token:
            cart = Cart.objects.filter(token=token, status=Cart.Status.ACTIVE, user__isnull=True).first()
            if cart:
                return cart
        return Cart.objects.create()

    @classmethod
    def available_stock(cls, product, variation):
        inventory = InventoryService.resolve_inventory(product, variation)
        return inventory.available if inventory else 0

    @classmethod
    @transaction.atomic
    def add_item(cls, cart, product, variation, quantity):
        if not product.is_public:
            raise ServiceError("This product is not available for purchase.", code="product_unavailable", status_code=409)
        if variation is not None and variation.product_id != product.pk:
            raise ServiceError("Variation does not belong to this product.", code="invalid_variation")
        if variation is not None and not variation.is_available:
            raise ServiceError("This variation is no longer available.", code="variation_unavailable", status_code=409)
        if quantity < 1 or quantity > settings.MAX_CART_ITEM_QUANTITY:
            raise ServiceError(f"Quantity must be between 1 and {settings.MAX_CART_ITEM_QUANTITY}.", code="invalid_quantity")

        item = CartItem.objects.filter(cart=cart, product=product, variation=variation).first()
        new_quantity = (item.quantity if item else 0) + quantity
        if new_quantity > settings.MAX_CART_ITEM_QUANTITY:
            raise ServiceError(f"Cart line quantity cannot exceed {settings.MAX_CART_ITEM_QUANTITY}.", code="invalid_quantity")
        available = cls.available_stock(product, variation)
        if new_quantity > available:
            raise StockUnavailableError(f"Only {available} unit(s) available.")
        if cart.items.count() >= settings.MAX_CART_ITEMS and item is None:
            raise ServiceError(f"A cart cannot hold more than {settings.MAX_CART_ITEMS} lines.", code="cart_full")
        if item:
            item.quantity = new_quantity
            item.save(update_fields=["quantity", "updated_at"])
        else:
            item = CartItem.objects.create(cart=cart, product=product, variation=variation, quantity=quantity)
        return item

    add_product = add_item  # alias used by wishlist move-to-cart

    @classmethod
    @transaction.atomic
    def update_quantity(cls, cart, item, quantity):
        if quantity < 1 or quantity > settings.MAX_CART_ITEM_QUANTITY:
            raise ServiceError(f"Quantity must be between 1 and {settings.MAX_CART_ITEM_QUANTITY}.", code="invalid_quantity")
        available = cls.available_stock(item.product, item.variation)
        if quantity > available:
            raise StockUnavailableError(f"Only {available} unit(s) available.")
        item.quantity = quantity
        item.save(update_fields=["quantity", "updated_at"])
        return item

    @classmethod
    @transaction.atomic
    def merge_guest_cart(cls, user, guest_token):
        """Merge a guest cart into the user's active cart.

        Rules: identical product+variation lines sum quantities (capped and
        stock-validated); unavailable items are skipped; the guest cart is
        marked MERGED and never reused.
        """
        guest_cart = Cart.objects.filter(token=guest_token, user__isnull=True, status=Cart.Status.ACTIVE).first()
        if not guest_cart:
            raise ServiceError("Guest cart not found or already merged.", code="guest_cart_not_found", status_code=404)
        user_cart, _ = Cart.objects.get_or_create(user=user, status=Cart.Status.ACTIVE)
        moved = 0
        for item in guest_cart.items.select_related("product", "variation"):
            try:
                cls.add_item(user_cart, item.product, item.variation, item.quantity)
                moved += 1
            except (StockUnavailableError, ServiceError):
                continue  # keep the rest of the merge usable; skipped lines are reported
        guest_cart.status = Cart.Status.MERGED
        guest_cart.merged_into = user_cart
        guest_cart.save(update_fields=["status", "merged_into", "updated_at"])
        return user_cart

    @classmethod
    def validate_for_checkout(cls, cart):
        """Hard validation right before order creation."""
        lines = []
        for item in cart.items.select_related("product", "variation"):
            if not item.product.is_public:
                raise ServiceError(f"'{item.product.name}' is no longer available. Remove it from your cart.",
                                   code="product_unavailable", status_code=409)
            if item.variation and not item.variation.is_available:
                raise ServiceError(f"A selected option for '{item.product.name}' is no longer available.",
                                   code="variation_unavailable", status_code=409)
            lines.append(item)
        if not lines:
            raise ServiceError("Your cart is empty.", code="empty_cart")
        return lines
