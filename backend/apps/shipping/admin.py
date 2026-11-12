from django.contrib import admin

from apps.shipping.models import (
    Shipment, ShipmentEvent, ShippingArea, ShippingMethod, ShippingZone,
)


class ShippingAreaInline(admin.TabularInline):
    model = ShippingArea
    extra = 1


class ShippingMethodInline(admin.TabularInline):
    model = ShippingMethod
    extra = 1


@admin.register(ShippingZone)
class ShippingZoneAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "free_shipping_threshold", "position")
    inlines = [ShippingAreaInline, ShippingMethodInline]


class ShipmentEventInline(admin.TabularInline):
    model = ShipmentEvent
    extra = 0


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = ("tracking_reference", "order", "status", "carrier", "dispatched_at")
    list_filter = ("status", "provider")
    search_fields = ("tracking_reference", "order__order_number")
    inlines = [ShipmentEventInline]
