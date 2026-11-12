from django.contrib import admin

from apps.inventory.models import Inventory, InventoryMovement, InventoryReservation


@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = ("product", "variation", "quantity_on_hand", "quantity_reserved",
                    "available_quantity", "low_stock_threshold", "track_inventory")
    list_filter = ("track_inventory", "allow_backorder")
    search_fields = ("product__name", "product__sku", "variation__sku")
    readonly_fields = ("quantity_reserved", "quantity_sold", "quantity_returned")


@admin.register(InventoryMovement)
class InventoryMovementAdmin(admin.ModelAdmin):
    list_display = ("inventory", "movement_type", "quantity", "reserved_delta",
                    "on_hand_after", "created_at")
    list_filter = ("movement_type", "direction")
    search_fields = ("reason", "reference_id")
    readonly_fields = [f.name for f in InventoryMovement._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(InventoryReservation)
class InventoryReservationAdmin(admin.ModelAdmin):
    list_display = ("inventory", "quantity", "status", "expires_at", "reference")
    list_filter = ("status",)
    readonly_fields = [f.name for f in InventoryReservation._meta.fields]
