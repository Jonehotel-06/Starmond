from rest_framework import serializers

from .models import Enquiry, NewsletterSubscriber, Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "kind", "title", "body", "link", "is_read", "created_at"]


class NewsletterSubscribeSerializer(serializers.Serializer):
    email = serializers.EmailField()


class EnquiryCreateSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    subject = serializers.CharField(max_length=200)
    message = serializers.CharField(max_length=4000)
    order_reference = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")


class EnquirySerializer(serializers.ModelSerializer):
    handled_by_email = serializers.CharField(source="handled_by.email", read_only=True, default=None)
    order_reference = serializers.CharField(source="related_order.reference", read_only=True, default=None)

    class Meta:
        model = Enquiry
        fields = ["id", "full_name", "email", "phone", "subject", "message", "status",
                  "handled_by_email", "response_note", "order_reference", "created_at"]


class NewsletterSubscriberSerializer(serializers.ModelSerializer):
    class Meta:
        model = NewsletterSubscriber
        fields = ["id", "email", "is_active", "source", "unsubscribed_at", "created_at"]
