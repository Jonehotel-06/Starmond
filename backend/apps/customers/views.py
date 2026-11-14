from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Address, CustomerProfile, Wishlist, WishlistItem
from .serializers import (
    AddressSerializer,
    CustomerProfileSerializer,
    WishlistAddSerializer,
    WishlistItemSerializer,
)


class ProfileView(RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CustomerProfileSerializer

    def get_object(self):
        profile, _ = CustomerProfile.objects.get_or_create(user=self.request.user)
        return profile


class AddressViewSet(viewsets.ModelViewSet):
    """Customers manage ONLY their own addresses (enforced server-side)."""
    permission_classes = [IsAuthenticated]
    serializer_class = AddressSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False) or not getattr(self.request, "user", None) or not self.request.user.is_authenticated:
            return Address.objects.none()
        return Address.objects.filter(customer=self.request.user)

    def perform_create(self, serializer):
        serializer.save(customer=self.request.user)

    def list(self, request, *args, **kwargs):
        data = self.get_serializer(self.get_queryset(), many=True).data
        return Response({"status": "success", "data": data})

    def retrieve(self, request, *args, **kwargs):
        return Response({"status": "success", "data": self.get_serializer(self.get_object()).data})

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response({"status": "success", "data": serializer.data}, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"status": "success", "data": serializer.data})

    def destroy(self, request, *args, **kwargs):
        self.get_object().delete()
        return Response({"status": "success", "message": "Address deleted."})


from drf_spectacular.utils import OpenApiTypes, extend_schema, extend_schema_view

@extend_schema_view(
    list=extend_schema(tags=["customers"], responses=OpenApiTypes.OBJECT),
    create=extend_schema(tags=["customers"], request=WishlistAddSerializer, responses=OpenApiTypes.OBJECT),
    remove=extend_schema(tags=["customers"], request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT),
    move_to_cart=extend_schema(tags=["customers"], request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT))
class WishlistViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def _wishlist(self, request):
        wl, _ = Wishlist.objects.get_or_create(customer=request.user)
        return wl

    def list(self, request):
        wl = self._wishlist(request)
        items = WishlistItem.objects.filter(wishlist=wl).select_related("product__category")
        return Response({"status": "success", "data": WishlistItemSerializer(items, many=True).data})

    def create(self, request):
        serializer = WishlistAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        wl = self._wishlist(request)
        item, created = WishlistItem.objects.get_or_create(wishlist=wl, product=serializer.validated_data["product"])
        return Response(
            {"status": "success", "message": "Added." if created else "Already in wishlist.", "data": WishlistItemSerializer(item).data},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], url_path="remove")
    def remove(self, request):
        product_id = request.data.get("product")
        wl = self._wishlist(request)
        WishlistItem.objects.filter(wishlist=wl, product_id=product_id).delete()
        return Response({"status": "success", "message": "Removed from wishlist."})

    @action(detail=False, methods=["post"], url_path="move-to-cart")
    def move_to_cart(self, request):
        from services.cart_service import CartService
        product_id = request.data.get("product")
        wl = self._wishlist(request)
        item = WishlistItem.objects.filter(wishlist=wl, product_id=product_id).select_related("product").first()
        if not item:
            return Response({"status": "error", "error": {"code": "not_found", "message": "Wishlist item not found.", "fields": None}}, status=404)
        cart = CartService.get_or_create_cart(request)
        CartService.add_item(cart, item.product, None, 1)
        item.delete()
        return Response({"status": "success", "message": "Moved to cart."})
