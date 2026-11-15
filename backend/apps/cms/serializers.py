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


def _public_media_url(key):
    """Storage key → public URL (keys are written by the media upload API)."""
    if not key:
        return None
    from apps.media.services import MediaService
    return MediaService.public_url(key)


class HomepageSectionSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    def get_image_url(self, obj):
        return _public_media_url(obj.image_key)

    class Meta:
        model = HomepageSection
        fields = ["id", "kind", "title", "subtitle", "config", "image_key", "image_url", "display_order",
                  "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]


class BannerSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    def get_image_url(self, obj):
        return _public_media_url(obj.image_key)

    class Meta:
        model = Banner
        fields = ["id", "title", "subtitle", "image_key", "image_url", "link_url", "placement",
                  "starts_at", "ends_at", "display_order", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]
