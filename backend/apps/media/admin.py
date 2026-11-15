from django.contrib import admin

from .models import MediaAsset


@admin.register(MediaAsset)
class MediaAssetAdmin(admin.ModelAdmin):
    list_display = ("original_name", "kind", "visibility", "status", "size_bytes", "created_at")
    list_filter = ("kind", "visibility", "status")
    search_fields = ("original_name", "alt_text")
    readonly_fields = ("public_id", "object_key", "thumbnail_key", "mime_type", "size_bytes", "width", "height")
