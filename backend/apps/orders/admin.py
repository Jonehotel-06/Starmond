from django.contrib import admin

from apps.orders.models import Order, OrderActivity, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("product_name", "sku", "unit_price", "quantity", "line_total")
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("order_number", "customer", "status", "payment_status", "grand_total", "created_at")
    list_filter = ("status", "payment_status", "channel", "shipping_state")
    search_fields = ("order_number", "guest_email", "shipping_full_name", "customer__email")
    date_hierarchy = "created_at"
    inlines = [OrderItemInline]
    readonly_fields = [
        "order_number", "subtotal", "discount_total", "shipping_total", "tax_total",
        "grand_total", "amount_paid", "amount_refunded", "created_at", "updated_at",
    ]

    def has_add_permission(self, request):
        # Orders may only be created through the checkout service.
        return False


@admin.register(OrderActivity)
class OrderActivityAdmin(admin.ModelAdmin):
    list_display = ("order", "event", "message", "actor_label", "created_at")
    list_filter = ("event",)
    search_fields = ("order__order_number", "message")
    readonly_fields = [f.name for f in OrderActivity._meta.fields]

    def has_add_permission(self, request):
        return False
