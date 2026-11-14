from django.contrib import admin
from .models import Payment, PaymentWebhookEvent

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ["reference", "order", "amount", "currency", "status", "channel", "verified_at"]
    list_filter = ["status", "provider"]
    search_fields = ["reference", "provider_reference", "order__reference"]

@admin.register(PaymentWebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ["provider_event_id", "event_type", "processed", "signature_valid", "received_at"]
    list_filter = ["event_type", "processed"]
