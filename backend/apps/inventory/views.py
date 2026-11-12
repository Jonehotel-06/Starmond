"""Staff inventory management: stock in, adjustments, movement history."""
from __future__ import annotations

from apps.core.permissions import IsStaff

from apps.core.exceptions import NotFound
from apps.core.pagination import StandardResultsSetPagination
from apps.core.permissions import RequiresPermission
from apps.core.views import BaseAPIView
from apps.inventory.models import Inventory, InventoryMovement
from apps.inventory.services import InventoryService
from apps.products.models import Product, ProductVariation


def _serialise(inv: Inventory) -> dict:
    return {
        "id": str(inv.pk),
        "product_id": str(inv.product_id),
        "product_name": inv.product.name,
        "variation_id": str(inv.variation_id) if inv.variation_id else None,
        "sku": inv.variation.sku if inv.variation_id else inv.product.sku,
        "quantity_on_hand": inv.quantity_on_hand,
        "quantity_reserved": inv.quantity_reserved,
        "quantity_sold": inv.quantity_sold,
        "quantity_returned": inv.quantity_returned,
        "available_quantity": inv.available_quantity,
        "low_stock_threshold": inv.low_stock_threshold,
        "stock_status": inv.stock_status,
        "track_inventory": inv.track_inventory,
        "allow_backorder": inv.allow_backorder,
    }


class InventoryListView(BaseAPIView):
    permission_classes = [IsStaff, RequiresPermission.of("inventory.view_inventory")]

    def get(self, request):
        queryset = Inventory.objects.select_related("product", "variation").order_by(
            "quantity_on_hand"
        )
        if request.query_params.get("low") in {"1", "true"}:
            from django.db.models import F

            queryset = queryset.filter(quantity_on_hand__lte=F("low_stock_threshold"))
        if request.query_params.get("q"):
            term = request.query_params["q"]
            from django.db.models import Q

            queryset = queryset.filter(
                Q(product__name__icontains=term) | Q(product__sku__icontains=term)
                | Q(variation__sku__icontains=term)
            )
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response([_serialise(row) for row in page])


class InventoryDetailView(BaseAPIView):
    permission_classes = [IsStaff, RequiresPermission.of("inventory.view_inventory")]

    def get(self, request, inventory_id: str):
        inv = Inventory.objects.select_related("product", "variation").filter(
            pk=inventory_id
        ).first()
        if inv is None:
            raise NotFound("Inventory record not found.")
        payload = _serialise(inv)
        payload["reconcile"] = InventoryService.reconcile(inv)
        payload["movements"] = [
            {
                "type": m.movement_type,
                "quantity": m.quantity,
                "on_hand_after": m.on_hand_after,
                "reserved_after": m.reserved_after,
                "reason": m.reason,
                "created_at": m.created_at.isoformat(),
            }
            for m in inv.movements.all()[:50]
        ]
        return self.ok(payload)


class StockReceiveView(BaseAPIView):
    permission_classes = [IsStaff, RequiresPermission.of("inventory.change_inventory")]

    def post(self, request):
        inventory = Inventory.objects.filter(pk=request.data.get("inventory_id")).first()
        if inventory is None:
            raise NotFound("Inventory record not found.")
        updated = InventoryService.receive_stock(
            inventory=inventory,
            quantity=request.data.get("quantity"),
            reason=request.data.get("reason", "Stock received"),
            actor=request.user,
        )
        return self.ok(_serialise(updated), message="Stock received.")


class StockAdjustView(BaseAPIView):
    permission_classes = [IsStaff, RequiresPermission.of("inventory.change_inventory")]

    def post(self, request):
        inventory = Inventory.objects.filter(pk=request.data.get("inventory_id")).first()
        if inventory is None:
            raise NotFound("Inventory record not found.")
        updated = InventoryService.adjust_stock(
            inventory=inventory,
            new_quantity=request.data.get("new_quantity"),
            reason=request.data.get("reason", "Stock adjustment"),
            actor=request.user,
        )
        return self.ok(_serialise(updated), message="Stock adjusted.")


class StockWriteOffView(BaseAPIView):
    permission_classes = [IsStaff, RequiresPermission.of("inventory.change_inventory")]

    def post(self, request):
        inventory = Inventory.objects.filter(pk=request.data.get("inventory_id")).first()
        if inventory is None:
            raise NotFound("Inventory record not found.")
        updated = InventoryService.write_off(
            inventory=inventory,
            quantity=request.data.get("quantity"),
            reason=request.data.get("reason", "Damage"),
            actor=request.user,
        )
        return self.ok(_serialise(updated), message="Stock written off.")


class InventoryEnsureView(BaseAPIView):
    """Creates the stock row for a product or variation that lacks one."""

    permission_classes = [IsStaff, RequiresPermission.of("inventory.add_inventory")]

    def post(self, request):
        product = Product.objects.filter(pk=request.data.get("product_id")).first()
        if product is None:
            raise NotFound("Product not found.")
        variation = None
        if request.data.get("variation_id"):
            variation = ProductVariation.objects.filter(
                pk=request.data["variation_id"], product=product
            ).first()
        inventory = InventoryService.get_or_create_for(
            product, variation, opening_quantity=int(request.data.get("opening_quantity", 0) or 0)
        )
        return self.created(_serialise(inventory), message="Inventory record ready.")


class MovementHistoryView(BaseAPIView):
    permission_classes = [IsStaff, RequiresPermission.of("inventory.view_inventorymovement")]

    def get(self, request):
        queryset = InventoryMovement.objects.select_related(
            "inventory", "inventory__product"
        ).order_by("-created_at")
        if request.query_params.get("type"):
            queryset = queryset.filter(movement_type=request.query_params["type"])
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response([
            {
                "id": str(m.pk),
                "type": m.movement_type,
                "quantity": m.quantity,
                "reserved_delta": m.reserved_delta,
                "on_hand_after": m.on_hand_after,
                "reserved_after": m.reserved_after,
                "reason": m.reason,
                "reference": m.reference_id,
                "created_at": m.created_at.isoformat(),
            }
            for m in page
        ])
