from rest_framework import serializers

from .models import MediaAsset
from .services import MediaService


class MediaAssetSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    key = serializers.SerializerMethodField()

    class Meta:
        model = MediaAsset
        fields = ["id", "public_id", "kind", "visibility", "status", "original_name", "mime_type",
                  "size_bytes", "width", "height", "alt_text", "url", "thumbnail_url", "key",
                  "related_object_type", "related_object_id", "created_at"]
        read_only_fields = ["id", "public_id", "kind", "visibility", "status", "original_name", "mime_type",
                            "size_bytes", "width", "height", "url", "thumbnail_url", "created_at"]

    def _absolute(self, url):
        request = self.context.get("request")
        if url and request is not None and url.startswith("/"):
            return request.build_absolute_uri(url)
        return url or ""

    def get_key(self, obj) -> str:
        """Storage key for PUBLIC assets — the value CMS `*_key` fields expect.
        Private (customer reference) assets never expose their key."""
        return obj.object_key if obj.visibility == MediaAsset.Visibility.PUBLIC else ""

    def get_url(self, obj) -> str:
        return self._absolute(MediaService.asset_url(obj))

    def get_thumbnail_url(self, obj) -> str:
        return self._absolute(MediaService.asset_url(obj, thumbnail=True))
