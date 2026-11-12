from django.contrib import admin

from apps.refunds.models import Refund, RefundItem


class RefundItemInline(admin.TabularInline):
    model = RefundItem
    extra = 0


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ("refund_number", "order", "status", "refund_type",
                    "amount_requested", "amount_refunded", "created_at")
    list_filter = ("status", "refund_type", "reason_category")
    search_fields = ("refund_number", "order__order_number", "provider_refund_id")
    inlines = [RefundItemInline]
    readonly_fields = ("refund_number", "provider_refund_id", "provider_status",
                       "amount_refunded", "created_at")
