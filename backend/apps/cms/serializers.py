from rest_framework import serializers

from .models import Banner, HomepageSection, Page


class BusinessSettingsSerializer(serializers.Serializer):
    values = serializers.JSONField()


class PageSerializer(serializers.ModelSerializer):
    seo = serializers.SerializerMethodField()

    class Meta:
        model = Page
        fields = ["id", "title", "slug", "body", "excerpt", "is_published", "display_order",
                  "seo_title", "seo_description", "canonical_url", "seo", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_seo(self, obj):
        return obj.effective_seo()


class HomepageSectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = HomepageSection
        fields = ["id", "kind", "title", "subtitle", "config", "image_key", "display_order",
                  "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]


class BannerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Banner
        fields = ["id", "title", "subtitle", "image_key", "link_url", "placement",
                  "starts_at", "ends_at", "display_order", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]
