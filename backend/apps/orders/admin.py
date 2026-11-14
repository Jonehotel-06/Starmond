from django.contrib import admin
from .models import Order, OrderItem, OrderStatusLog

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ["product_name", "sku", "variation_label", "unit_price", "quantity", "line_total"]

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["reference", "contact_email", "status", "payment_status", "total_amount", "placed_at"]
    list_filter = ["status", "payment_status"]
    search_fields = ["reference", "contact_email", "contact_full_name"]
    inlines = [OrderItemInline]
    readonly_fields = ["reference", "subtotal_amount", "discount_amount", "shipping_fee", "total_amount"]

admin.site.register(OrderStatusLog)
