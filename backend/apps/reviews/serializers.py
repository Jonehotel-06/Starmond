from rest_framework import serializers

from apps.reviews.models import Review


class ReviewSerializer(serializers.ModelSerializer):
    reviewer_name = serializers.CharField(read_only=True)
    author_is_self = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = ["id", "rating", "title", "comment", "reviewer_name", "author_is_self",
                  "is_verified_purchase", "is_approved", "moderation_status", "helpful_count",
                  "staff_reply", "replied_at", "created_at"]
        read_only_fields = ["id", "reviewer_name", "author_is_self", "is_verified_purchase",
                            "is_approved", "moderation_status", "helpful_count", "created_at"]

    def get_author_is_self(self, obj):
        request = self.context.get("request")
        return bool(request and request.user.is_authenticated and obj.user_id == request.user.pk)


class ReviewCreateSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    rating = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(min_length=10, max_length=4000)
    title = serializers.CharField(max_length=150, required=False, allow_blank=True)
    order_item_id = serializers.UUIDField(required=False, allow_null=True)
