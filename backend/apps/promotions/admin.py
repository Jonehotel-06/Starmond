from django.contrib import admin

from apps.promotions.models import Promotion, PromotionUsage


@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "promotion_type", "value", "is_active",
                    "starts_at", "ends_at", "usage_limit_total")
    list_filter = ("promotion_type", "is_active", "is_automatic", "is_stackable")
    search_fields = ("name", "code")
    filter_horizontal = ("categories", "products")


@admin.register(PromotionUsage)
class PromotionUsageAdmin(admin.ModelAdmin):
    list_display = ("promotion", "order", "customer_email", "discount_amount", "created_at")
    readonly_fields = [f.name for f in PromotionUsage._meta.fields]

    def has_add_permission(self, request):
        return False
