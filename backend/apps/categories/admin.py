from django.contrib import admin

from apps.categories.models import Category


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "path", "depth", "parent", "status", "is_featured", "position")
    list_filter = ("status", "is_active", "is_featured", "depth")
    search_fields = ("name", "slug", "path")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("path", "depth", "published_at")
