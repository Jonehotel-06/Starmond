"""Public promotion validation plus staff promotion management."""
from __future__ import annotations

from rest_framework.permissions import AllowAny
from rest_framework.throttling import ScopedRateThrottle

from apps.cart.services import CartService
from apps.core.permissions import RequiresPermission
from apps.core.views import BaseAPIView
from apps.orders.checkout import CheckoutService
from apps.promotions.models import Promotion
from apps.promotions.serializers import PromotionSerializer
from apps.promotions.services import PromotionService


class PromotionValidateView(BaseAPIView):
    """
    Validates a code against the live basket without applying it.

    Returns the authoritative discount, or an explanation, so the cart UI can
    tell the customer exactly why a code did not work.
    """

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "user"

    def post(self, request):
        cart = CartService.get_for_request(request, create=False)
        codes = request.data.get("promo_codes") or ([request.data["code"]] if request.data.get("code") else [])
        customer = request.user if request.user.is_authenticated else None
        payload = CheckoutService.preview(
            cart=cart,
            product_id=request.data.get("product_id"),
            variation_id=request.data.get("variation_id"),
            quantity=request.data.get("quantity", 1),
            state=request.data.get("state", ""),
            city=request.data.get("city", ""),
            promo_codes=codes,
            customer=customer,
        )
        return self.ok(payload)


class PublicPromotionListView(BaseAPIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "anon"

    def get(self, request):
        rows = PromotionService.active_public_promotions()
        return self.ok(PromotionSerializer(rows, many=True).data)


class StaffPromotionView(BaseAPIView):
    permission_classes = [RequiresPermission.of("promotions.change_promotion")]

    def get(self, request):
        from apps.core.pagination import StandardResultsSetPagination

        queryset = Promotion.objects.order_by("-created_at")
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(PromotionSerializer(page, many=True).data)

    def post(self, request):
        serializer = PromotionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        promotion = serializer.save()
        promotion.full_clean()
        return self.created(PromotionSerializer(promotion).data, message="Promotion created.")
