from rest_framework import serializers

from .models import ShippingMethod, ShippingZone


class ShippingZoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShippingZone
        fields = ["id", "name", "states", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_states(self, value):
        if not isinstance(value, list) or not all(isinstance(s, str) for s in value):
            raise serializers.ValidationError("States must be a list of strings.")
        return value


class ShippingMethodSerializer(serializers.ModelSerializer):
    zone_name = serializers.CharField(source="zone.name", read_only=True, default=None)
    estimated_delivery = serializers.CharField(read_only=True)

    class Meta:
        model = ShippingMethod
        fields = ["id", "name", "kind", "zone", "zone_name", "fee", "free_above_amount",
                  "min_days", "max_days", "is_active", "display_order", "pickup_address",
                  "estimated_delivery", "created_at"]
        read_only_fields = ["id", "created_at"]
