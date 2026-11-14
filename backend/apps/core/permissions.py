"""Role-based access control for staff APIs.

Superusers (the business owner) bypass all checks. Staff users are checked
against the permission codenames attached to their role. Permission checks are
ALWAYS enforced server-side; frontend visibility is irrelevant.
"""
from rest_framework.permissions import BasePermission

from .constants import Perm


def get_staff_profile(user):
    return getattr(user, "staff_profile", None)


def user_has_permission(user, codename):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    profile = get_staff_profile(user)
    if not profile or not profile.is_active or not profile.role:
        return False
    return profile.role.permissions.filter(codename=codename).exists()


class IsStaffWithPermission(BasePermission):
    """DRF permission bound to a codename via `permission_codename` on the view."""

    def has_permission(self, request, view):
        codename = getattr(view, "permission_codename", None)
        if codename is None:
            return request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser)
        return user_has_permission(request.user, codename)


class IsAdminUser(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_superuser)


def require(codename):
    """Helper to build a permission class for a specific codename."""
    return type(f"Requires_{codename.replace('.', '_')}", (IsStaffWithPermission,), {"permission_codename_static": codename})


SAFE_METHODS_PERM_MAP = {
    "GET": None,
}
