from django.contrib import admin

from apps.payments.models import Payment, PaymentWebhookEvent


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("reference", "order", "status", "amount", "currency", "is_verified", "paid_at")
    list_filter = ("status", "is_verified", "provider", "channel")
    search_fields = ("reference", "provider_reference", "order__order_number")
    readonly_fields = [f.name for f in Payment._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PaymentWebhookEvent)
class PaymentWebhookEventAdmin(admin.ModelAdmin):
    list_display = ("event_type", "transaction_reference", "processing_status",
                    "signature_valid", "created_at")
    list_filter = ("event_type", "processing_status", "signature_valid")
    search_fields = ("event_key", "transaction_reference")
    readonly_fields = [f.name for f in PaymentWebhookEvent._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
