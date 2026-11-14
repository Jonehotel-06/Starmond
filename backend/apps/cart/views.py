from django.db import transaction
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import ServiceError
from services.cart_service import CartService
from services.pricing_service import PricingService

from .models import Cart
from .serializers import CartAddSerializer, CartItemSerializer, CartMergeSerializer, CartUpdateSerializer


def _cart_response(cart, request):
    summary = PricingService.price_cart(cart)
    return {
        "status": "success",
        "data": {
            "token": cart.token,
            "items": CartItemSerializer(cart.items.select_related("product", "variation", "variation__image"), many=True).data,
            "item_count": summary["item_count"],
            "subtotal": str(summary["subtotal"]),
            "currency": "NGN",
        },
    }


from drf_spectacular.utils import OpenApiTypes, extend_schema, extend_schema_view

@extend_schema_view(
    get=extend_schema(tags=["cart"], responses=OpenApiTypes.OBJECT),
    post=extend_schema(tags=["cart"], request=CartAddSerializer, responses={201: OpenApiTypes.OBJECT}),
    delete=extend_schema(tags=["cart"], request=None, responses=OpenApiTypes.OBJECT))
class CartView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        cart = CartService.get_or_create_cart(request)
        return Response(_cart_response(cart, request))

    def delete(self, request):
        cart = CartService.get_or_create_cart(request)
        cart.items.all().delete()
        return Response({"status": "success", "message": "Cart cleared."})

    def post(self, request):
        serializer = CartAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cart = CartService.get_or_create_cart(request)
        item = CartService.add_item(
            cart, serializer.validated_data["product"],
            serializer.validated_data.get("variation"),
            serializer.validated_data["quantity"])
        return Response(_cart_response(cart, request), status=status.HTTP_201_CREATED)


@extend_schema_view(
    patch=extend_schema(tags=["cart"], request=CartUpdateSerializer, responses=OpenApiTypes.OBJECT),
    delete=extend_schema(tags=["cart"], request=None, responses=OpenApiTypes.OBJECT))
class CartItemDetailView(APIView):
    permission_classes = [AllowAny]

    def _item(self, request, item_id):
        cart = CartService.get_or_create_cart(request)
        from .models import CartItem
        item = CartItem.objects.filter(pk=item_id, cart=cart).first()
        if not item:
            raise ServiceError("Cart item not found.", code="not_found", status_code=404)
        return cart, item

    def patch(self, request, item_id):
        cart, item = self._item(request, item_id)
        serializer = CartUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        CartService.update_quantity(cart, item, serializer.validated_data["quantity"])
        return Response(_cart_response(cart, request))

    def delete(self, request, item_id):
        cart, item = self._item(request, item_id)
        item.delete()
        return Response(_cart_response(cart, request))


@extend_schema(tags=["cart"], request=CartMergeSerializer, responses=OpenApiTypes.OBJECT)
class CartMergeView(APIView):
    """Authenticated customer merges a guest cart (POST /api/cart/merge/)."""
    permission_classes = [AllowAny]

    def post(self, request):
        if not request.user.is_authenticated:
            raise ServiceError("Authentication is required to merge carts.", code="authentication_required", status_code=401)
        serializer = CartMergeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            cart = CartService.merge_guest_cart(request.user, serializer.validated_data["token"])
        return Response(_cart_response(cart, request))
