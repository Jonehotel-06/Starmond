from decimal import Decimal

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.audit.services import AuditService
from apps.core.constants import Perm
from apps.core.exceptions import ServiceError
from apps.core.permissions import IsStaffWithPermission
from apps.products.models import Product, ProductVariation

from .models import Promotion
from .serializers import PromotionSerializer, PromotionValidateRequestSerializer
from .services import PromotionService


from drf_spectacular.utils import OpenApiTypes, extend_schema

@extend_schema(tags=["promotions"], request=PromotionValidateRequestSerializer, responses=OpenApiTypes.OBJECT)
class PromotionValidateView(viewsets.ViewSet):
    """POST /api/promotions/validate/ — preview eligibility for UX.
    The AUTHORITATIVE application always happens again at checkout."""
    permission_classes = [AllowAny]

    def create(self, request):
        serializer = PromotionValidateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lines, subtotal = [], Decimal('0.00')
        for raw in serializer.validated_data.get("items", []):
            product = Product.objects.filter(pk=raw.get("product_id"), status=Product.Status.ACTIVE, is_active=True).first()
            if not product:
                raise ServiceError(f"Product {raw.get('product_id')} is not available.", code="product_unavailable")
            quantity = max(1, int(raw.get("quantity", 1)))
            variation = None
            if raw.get("variation_id"):
                variation = ProductVariation.objects.filter(pk=raw["variation_id"], product=product).first()
                if not variation:
                    raise ServiceError("Invalid variation.", code="invalid_variation")
            unit_price = variation.effective_price if variation else product.effective_price
            line_total = unit_price * quantity
            subtotal += line_total
            lines.append({"product": product, "line_total": line_total})
        if not lines:
            raise ServiceError("Provide at least one item to validate a discount.", code="no_items")
        customer = request.user if request.user.is_authenticated else None
        promotion, discount = PromotionService.validate(
            serializer.validated_data["code"], lines=lines, subtotal=subtotal, customer=customer)
        return Response({"status": "success", "data": {
            "valid": True, "code": promotion.code, "name": promotion.name,
            "kind": promotion.kind, "value": str(promotion.value),
            "discount": str(discount), "subtotal": str(subtotal),
            "message": f"Discount of ₦{discount} will be applied at checkout.",
        }})


class StaffPromotionViewSet(viewsets.ModelViewSet):
    permission_classes = [IsStaffWithPermission]
    permission_codename = Perm.PROMOTIONS_MANAGE
    serializer_class = PromotionSerializer
    queryset = Promotion.objects.all()
    search_fields = ["code", "name"]
    filterset_fields = ["is_active", "kind", "scope"]

    def perform_create(self, serializer):
        promo = serializer.save()
        AuditService.log(self.request.user, "promotion.create", "Promotion", promo.pk, {"code": promo.code}, request=self.request)

    def perform_update(self, serializer):
        promo = serializer.save()
        AuditService.log(self.request.user, "promotion.update", "Promotion", promo.pk, {"code": promo.code}, request=self.request)

    def perform_destroy(self, instance):
        AuditService.log(self.request.user, "promotion.delete", "Promotion", instance.pk, {"code": instance.code}, request=self.request)
        instance.delete()
