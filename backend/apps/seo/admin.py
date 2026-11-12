from django.contrib import admin

from apps.seo.models import Redirect, SEOSetting


@admin.register(SEOSetting)
class SEOSettingAdmin(admin.ModelAdmin):
    list_display = ("path", "title", "robots", "is_active")
    list_filter = ("robots", "is_active")
    search_fields = ("path", "title")


@admin.register(Redirect)
class RedirectAdmin(admin.ModelAdmin):
    list_display = ("from_path", "to_path", "status_code", "is_active", "hit_count")
    search_fields = ("from_path", "to_path")
