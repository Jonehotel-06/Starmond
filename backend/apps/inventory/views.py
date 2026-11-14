import django_filters as filters
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.audit.services import AuditService
from apps.core.constants import Perm
from apps.core.permissions import IsStaffWithPermission

from .models import Inventory, InventoryMovement
from .serializers import (
    InventoryMovementSerializer,
    InventorySerializer,
    StockAdjustSerializer,
    StockReceiveSerializer,
)
from .services import InventoryService


class InventoryFilter(filters.FilterSet):
    product = filters.NumberFilter(field_name="product_id")
    low_stock = filters.BooleanFilter(method="filter_low")
    out_of_stock = filters.BooleanFilter(method="filter_out")
    search = filters.CharFilter(method="filter_search")

    class Meta:
        model = Inventory
        fields = ["product", "low_stock", "out_of_stock"]

    def filter_search(self, qs, name, value):
        from django.db.models import Q
        return qs.filter(Q(product__name__icontains=value) | Q(product__sku__icontains=value) | Q(variation__sku__icontains=value))

    def _computed(self, qs):
        # available = on_hand - reserved (evaluate in SQL for filtering)
        from django.db.models import F
        return qs.annotate(available_qty=F("on_hand") - F("reserved"))

    def filter_low(self, qs, name, value):
        from django.db.models import F
        qs = self._computed(qs)
        if not value:
            return qs
        from django.db.models.functions import Coalesce
        threshold = Coalesce("low_stock_threshold", "product__low_stock_threshold")
        return qs.filter(available_qty__gt=0, available_qty__lte=threshold)

    def filter_out(self, qs, name, value):
        qs = self._computed(qs)
        return qs.filter(available_qty__lte=0) if value else qs.filter(available_qty__gt=0)


class InventoryViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsStaffWithPermission]
    permission_codename = Perm.INVENTORY_VIEW
    serializer_class = InventorySerializer
    queryset = Inventory.objects.select_related("product", "variation").all()
    filterset_class = InventoryFilter

    def _ensure_manage(self, request):
        from apps.core.permissions import user_has_permission
        if not user_has_permission(request.user, Perm.INVENTORY_MANAGE):
            from apps.core.exceptions import ServiceError
            raise ServiceError("You lack the inventory.manage permission.", code="permission_denied", status_code=403)

    @action(detail=True, methods=["post"], url_path="adjust")
    def adjust(self, request, pk=None):
        self._ensure_manage(request)
        inventory = self.get_object()
        serializer = StockAdjustSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        inv = InventoryService.adjust(
            inventory, serializer.validated_data["delta"], performed_by=request.user,
            reason=serializer.validated_data["reason"])
        AuditService.log(request.user, "inventory.adjust", "Inventory", inv.pk,
                         {"delta": serializer.validated_data["delta"], "reason": serializer.validated_data["reason"]}, request=request)
        return Response({"status": "success", "data": InventorySerializer(inv).data})

    @action(detail=True, methods=["post"], url_path="receive")
    def receive(self, request, pk=None):
        self._ensure_manage(request)
        inventory = self.get_object()
        serializer = StockReceiveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        inv = InventoryService.receive_stock(
            inventory, serializer.validated_data["quantity"], performed_by=request.user,
            reason=serializer.validated_data["reason"])
        AuditService.log(request.user, "inventory.receive", "Inventory", inv.pk,
                         {"quantity": serializer.validated_data["quantity"]}, request=request)
        return Response({"status": "success", "data": InventorySerializer(inv).data})

    @action(detail=True, methods=["get"], url_path="movements")
    def movements(self, request, pk=None):
        inventory = self.get_object()
        qs = inventory.movements.select_related("order", "performed_by").all()[:200]
        return Response({"status": "success", "data": InventoryMovementSerializer(qs, many=True).data})


class InventoryMovementViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsStaffWithPermission]
    permission_codename = Perm.INVENTORY_VIEW
    serializer_class = InventoryMovementSerializer
    queryset = InventoryMovement.objects.select_related("product", "variation", "order", "performed_by").all()
    filterset_fields = ["movement_type", "product"]
    ordering = ["-created_at"]
