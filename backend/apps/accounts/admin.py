from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.accounts.models import Role, StaffProfile, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("-date_joined",)
    list_display = ("email", "full_name", "is_staff", "is_email_verified", "is_active", "date_joined")
    list_filter = ("is_staff", "is_superuser", "is_email_verified", "is_active")
    search_fields = ("email", "first_name", "last_name", "phone")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("first_name", "last_name", "phone", "gender")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Verification", {"fields": ("is_email_verified", "email_verified_at")}),
        ("Security", {"fields": ("failed_login_attempts", "locked_until", "last_login_ip")}),
    )
    readonly_fields = ("email_verified_at", "last_login_ip")
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "password1", "password2", "is_staff")}),
    )


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_system", "is_active")
    filter_horizontal = ("permissions",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "designation", "department", "is_active")
    list_filter = ("role", "department", "is_active")
    search_fields = ("user__email", "employee_code")
