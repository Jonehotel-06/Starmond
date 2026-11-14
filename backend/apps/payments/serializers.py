from rest_framework import serializers

from .models import Payment, PaymentWebhookEvent


class PaymentSerializer(serializers.ModelSerializer):
    order_reference = serializers.CharField(source="order.reference", read_only=True)
    order_total = serializers.DecimalField(source="order.total_amount", max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = Payment
        fields = ["id", "reference", "order", "order_reference", "order_total", "provider",
                  "provider_reference", "amount", "currency", "status", "channel",
                  "authorization_url", "access_code", "initialized_at", "verified_at",
                  "failure_reason", "created_at"]
        read_only_fields = fields


class PaymentInitializeSerializer(serializers.Serializer):
    order_reference = serializers.CharField(max_length=32)
    guest_token = serializers.CharField(max_length=255, required=False, allow_blank=True,
                                        help_text="Required for guest orders (issued at checkout).")


class PaymentVerifySerializer(serializers.Serializer):
    reference = serializers.CharField(max_length=120, help_text="Paystack/provider reference returned at initialization.")
    guest_token = serializers.CharField(max_length=255, required=False, allow_blank=True)


class WebhookEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentWebhookEvent
        fields = ["id", "provider_event_id", "event_type", "processed", "outcome", "error",
                  "signature_valid", "received_at", "processed_at"]
