"""
Authorization primitives.

Sensitive actions are gated on *Django permissions* resolved through the
customer's configurable Role, never on hardcoded staff flags. Superusers hold
every permission implicitly.
"""
from __future__ import annotations

from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.core.exceptions import PermissionDeniedError


class IsCustomer(BasePermission):
    message = "A customer account is required for this action."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_active)


class IsVerifiedCustomer(IsCustomer):
    message = "Please verify your email address to continue."

    def has_permission(self, request, view):
        return super().has_permission(request, view) and bool(request.user.is_email_verified)


class IsStaff(BasePermission):
    message = "Staff access is required for this action."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_active and user.is_staff)


class IsSuperAdmin(BasePermission):
    message = "Super administrator access is required."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_superuser)


class IsOwnerOrStaff(BasePermission):
    """Object-level guard used for customer private records."""

    owner_field = "user"

    def has_object_permission(self, request, view, obj):
        if getattr(request.user, "is_staff", False):
            return True
        owner_field = getattr(view, "owner_field", self.owner_field)
        owner = obj
        for part in owner_field.split("__"):
            owner = getattr(owner, part, None)
            if owner is None:
                return False
        return owner == request.user


class RequiresPermission(BasePermission):
    """
    Permission-class factory keyed on a Django permission codename.

    Usage::

        permission_classes = [RequiresPermission.of("orders.change_order")]
    """

    required_permission: str | None = None

    def has_permission(self, request, view):
        required = getattr(view, "required_permission", None) or self.required_permission
        if not required:
            return True
        user = request.user
        if not (user and user.is_authenticated and user.is_active):
            return False
        return user.has_perm(required)

    @classmethod
    def of(cls, codename: str):
        return type(f"RequiresPermission[{codename}]", (cls,), {"required_permission": codename})


class ReadOnlyOrStaff(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


class HasRole(BasePermission):
    """Checks the staff member's assigned configurable role slug."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated and user.is_staff):
            return False
        allowed = getattr(view, "allowed_roles", None)
        if not allowed:
            return True
        profile = getattr(user, "staff_profile", None)
        if profile is None or profile.role_id is None:
            return user.is_superuser
        return profile.role.slug in allowed or user.is_superuser


def enforce(user, perm: str) -> None:
    """Imperative permission check for use inside service functions."""
    if not (user and user.is_authenticated and user.is_active and user.has_perm(perm)):
        raise PermissionDeniedError(f"Missing required permission: {perm}")
