from django.db import transaction
from rest_framework import serializers

from apps.products.models import Product

from .models import Address, CustomerProfile, Wishlist, WishlistItem


class CustomerProfileSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    full_name = serializers.CharField(source="user.full_name")
    phone = serializers.CharField(source="user.phone", allow_blank=True)

    class Meta:
        model = CustomerProfile
        fields = ["email", "full_name", "phone", "marketing_emails", "order_update_emails", "sms_updates"]

    def update(self, instance, validated_data):
        user_data = {}
        if "user" in validated_data:
            user_data = validated_data.pop("user")
        instance = super().update(instance, validated_data)
        if user_data:
            user = instance.user
            for k, v in user_data.items():
                setattr(user, k, v)
            user.save(update_fields=list(user_data.keys()))
        return instance


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = ["public_id", "kind", "label", "full_name", "phone", "state", "city", "street",
                  "details", "instructions", "is_default", "created_at"]
        read_only_fields = ["public_id", "created_at"]

    @transaction.atomic
    def save(self, **kwargs):
        instance = super().save(**kwargs)
        if instance.is_default:
            Address.objects.filter(customer=instance.customer, kind=instance.kind, is_default=True)\
                .exclude(pk=instance.pk).update(is_default=False)
        return instance


class WishlistItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_slug = serializers.CharField(source="product.slug", read_only=True)
    main_image = serializers.SerializerMethodField()
    price = serializers.DecimalField(source="product.effective_price", max_digits=12, decimal_places=2, read_only=True)
    in_stock = serializers.BooleanField(source="product.is_in_stock", read_only=True)

    class Meta:
        model = WishlistItem
        fields = ["id", "product", "product_name", "product_slug", "main_image", "price", "in_stock", "created_at"]
        read_only_fields = ["id", "created_at"]

    def get_main_image(self, obj):
        img = obj.product.main_image
        return img.file_url if img else None

    def validate_product(self, product):
        if not product.is_public:
            raise serializers.ValidationError("Product is not available.")
        return product


class WishlistAddSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())


class StaffCustomerSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    email = serializers.EmailField()
    full_name = serializers.CharField()
    phone = serializers.CharField()
    is_email_verified = serializers.BooleanField()
    date_joined = serializers.DateTimeField()
    orders_count = serializers.IntegerField()
    total_spent = serializers.DecimalField(max_digits=14, decimal_places=2)
