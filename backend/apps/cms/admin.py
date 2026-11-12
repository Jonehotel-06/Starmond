from django.contrib import admin

from apps.cms.models import Banner, BusinessSetting, ContentPage, StoreLocation


@admin.register(BusinessSetting)
class BusinessSettingAdmin(admin.ModelAdmin):
    list_display = ("key", "label", "value", "value_type", "group", "is_public")
    list_filter = ("group", "value_type", "is_public")
    search_fields = ("key", "label", "value")


@admin.register(ContentPage)
class ContentPageAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "status", "show_in_footer", "updated_at")
    list_filter = ("status", "show_in_footer", "noindex")
    prepopulated_fields = {"slug": ("title",)}


@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = ("title", "is_active", "position", "starts_at", "ends_at")


@admin.register(StoreLocation)
class StoreLocationAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "state", "is_pickup_point", "is_active")
