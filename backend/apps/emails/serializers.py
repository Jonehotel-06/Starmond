from rest_framework import serializers

from .models import EmailLog


class EmailLogSerializer(serializers.ModelSerializer):
    order_reference = serializers.CharField(source="related_order.reference", read_only=True, default=None)

    class Meta:
        model = EmailLog
        fields = ["id", "recipient", "template_key", "subject", "status", "order_reference",
                  "attempts", "last_error", "sent_at", "created_at"]
