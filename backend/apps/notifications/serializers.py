from rest_framework import serializers

from apps.notifications.models import Enquiry, Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "notification_type", "title", "message", "action_url",
                  "is_read", "read_at", "created_at"]


class NewsletterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    name = serializers.CharField(max_length=150, required=False, allow_blank=True)


class EnquirySerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    subject = serializers.CharField(max_length=200)
    message = serializers.CharField(min_length=10, max_length=5000)
    phone = serializers.CharField(max_length=16, required=False, allow_blank=True)
    order_number = serializers.CharField(max_length=32, required=False, allow_blank=True)


class StaffEnquirySerializer(serializers.ModelSerializer):
    class Meta:
        model = Enquiry
        fields = ["id", "name", "email", "phone", "subject", "message", "status",
                  "order_number", "staff_response", "created_at"]
