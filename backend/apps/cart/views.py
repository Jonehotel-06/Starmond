"""Cart endpoints — fully server-authoritative."""
from __future__ import annotations

from rest_framework.permissions import AllowAny
from rest_framework.throttling import ScopedRateThrottle

from apps.cart.services import CartService
from apps.core.views import BaseAPIView
from apps.shipping.services import ShippingService


class CartView(BaseAPIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "anon"

    def get(self, request):
        cart = CartService.get_for_request(request)
        payload = CartService.summary(
            cart,
            shipping_state=request.query_params.get("state", ""),
            shipping_city=request.query_params.get("city", ""),
            shipping_method_code=request.query_params.get("method") or None,
        )
        payload["eligible_states"] = ShippingService.eligible_states()
        payload["shipping_options"] = (
            ShippingService.options_for(
                state=request.query_params.get("state", ""),
                city=request.query_params.get("city", ""),
                subtotal=payload["subtotal"],
            )
            if request.query_params.get("state") else []
        )
        return self.ok(payload)

    def delete(self, request):
        cart = CartService.get_for_request(request)
        CartService.clear(cart)
        return self.ok(CartService.summary(cart), message="Cart cleared.")


class CartItemView(BaseAPIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "user"

    def post(self, request):
        cart = CartService.get_for_request(request)
        item = CartService.add_item(
            cart,
            product_id=request.data.get("product_id"),
            variation_id=request.data.get("variation_id") or None,
            quantity=request.data.get("quantity", 1),
            custom_order_details=request.data.get("custom_order_details") or None,
            replace=bool(request.data.get("replace")),
        )
        payload = CartService.summary(cart)
        payload["added_item_id"] = str(item.pk)
        return self.created(payload, message="Item added to cart.")

    def patch(self, request, item_id: str):
        cart = CartService.get_for_request(request)
        CartService.update_item(cart, item_id=item_id, quantity=request.data.get("quantity"))
        return self.ok(CartService.summary(cart), message="Cart updated.")

    def delete(self, request, item_id: str):
        cart = CartService.get_for_request(request)
        CartService.remove_item(cart, item_id=item_id)
        return self.ok(CartService.summary(cart), message="Item removed from cart.")


class CartPromotionView(BaseAPIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "user"

    def post(self, request):
        cart = CartService.get_for_request(request)
        CartService.apply_code(cart, request.data.get("code", ""))
        return self.ok(CartService.summary(cart), message="Discount code applied.")

    def delete(self, request, code: str):
        cart = CartService.get_for_request(request)
        CartService.remove_code(cart, code)
        return self.ok(CartService.summary(cart), message="Discount code removed.")


class CartMergeView(BaseAPIView):
    """Explicit merge for clients that sign in without a session cookie."""

    def post(self, request):
        cart, info = CartService.merge_guest_cart(request, request.user)
        return self.ok(CartService.summary(cart), message="Carts merged.", merge=info)
