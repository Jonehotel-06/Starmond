"""Saved addresses and wishlist — strictly scoped to the authenticated customer."""
from __future__ import annotations

from rest_framework.permissions import IsAuthenticated

from apps.core.exceptions import ConflictError, NotFound
from apps.core.pagination import StandardResultsSetPagination
from apps.core.views import BaseAPIView
from apps.customers.models import Address, Wishlist, WishlistItem
from apps.customers.serializers import AddressSerializer, WishlistItemSerializer
from apps.products.models import Product, ProductVariation


class AddressListCreateView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = Address.objects.filter(user=request.user)
        return self.ok(AddressSerializer(rows, many=True).data)

    def post(self, request):
        serializer = AddressSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        address = serializer.save(user=request.user)
        if not Address.objects.filter(user=request.user).exclude(pk=address.pk).exists():
            address.is_default = True
            address.save(update_fields=["is_default"])
        return self.created(AddressSerializer(address).data, message="Address saved.")


class AddressDetailView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def _get(self, request, address_id):
        address = Address.objects.filter(pk=address_id, user=request.user).first()
        if address is None:
            raise NotFound("Address not found.")
        return address

    def get(self, request, address_id):
        return self.ok(AddressSerializer(self._get(request, address_id)).data)

    def patch(self, request, address_id):
        address = self._get(request, address_id)
        serializer = AddressSerializer(address, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return self.ok(AddressSerializer(address).data, message="Address updated.")

    def delete(self, request, address_id):
        address = self._get(request, address_id)
        address.delete()
        return self.ok(message="Address removed.")


class WishlistView(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        wishlist, _ = Wishlist.objects.get_or_create(user=request.user)
        items = wishlist.items.select_related("product", "variation").order_by("-created_at")
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(items, request, view=self)
        return paginator.get_paginated_response(WishlistItemSerializer(page, many=True).data)

    def post(self, request):
        wishlist, _ = Wishlist.objects.get_or_create(user=request.user)
        product = Product.objects.public().filter(pk=request.data.get("product_id")).first()
        if product is None:
            raise NotFound("Product not found.")
        variation = None
        if request.data.get("variation_id"):
            variation = ProductVariation.objects.filter(
                pk=request.data["variation_id"], product=product
            ).first()
        item, created = WishlistItem.objects.get_or_create(
            wishlist=wishlist, product=product, defaults={"variation": variation}
        )
        if not created:
            return self.ok(WishlistItemSerializer(item).data, message="Already in your wishlist.")
        return self.created(WishlistItemSerializer(item).data, message="Added to your wishlist.")

    def delete(self, request):
        item_id = request.data.get("item_id") or request.query_params.get("item_id")
        deleted, _ = WishlistItem.objects.filter(
            pk=item_id, wishlist__user=request.user
        ).delete()
        if not deleted:
            raise NotFound("That item is not in your wishlist.")
        return self.ok(message="Removed from your wishlist.")
