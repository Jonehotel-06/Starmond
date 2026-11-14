from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.core.constants import Perm
from apps.core.permissions import IsStaffWithPermission

from .models import ShippingMethod, ShippingZone
from .serializers import ShippingMethodSerializer, ShippingZoneSerializer
from .services import ShippingService


from drf_spectacular.utils import OpenApiTypes, extend_schema

@extend_schema(tags=["shipping"], responses=OpenApiTypes.OBJECT)
class ShippingQuoteView(viewsets.ViewSet):
    """GET /api/shipping/options/?state=Lagos&subtotal=50000 — public quote."""
    permission_classes = [AllowAny]

    def list(self, request):
        state = request.query_params.get("state", "")
        from decimal import Decimal
        try:
            subtotal = Decimal(request.query_params.get("subtotal", "0"))
        except Exception:
            subtotal = Decimal("0")
        options = ShippingService.available_methods(state, subtotal)
        return Response({"status": "success", "data": options})


class ShippingZoneViewSet(viewsets.ModelViewSet):
    permission_classes = [IsStaffWithPermission]
    permission_codename = Perm.SHIPPING_MANAGE
    serializer_class = ShippingZoneSerializer
    queryset = ShippingZone.objects.all()
    pagination_class = None


class ShippingMethodViewSet(viewsets.ModelViewSet):
    permission_classes = [IsStaffWithPermission]
    permission_codename = Perm.SHIPPING_MANAGE
    serializer_class = ShippingMethodSerializer
    queryset = ShippingMethod.objects.select_related("zone").all()
    pagination_class = None
