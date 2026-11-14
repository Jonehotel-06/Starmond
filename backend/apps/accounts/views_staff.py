"""Staff & RBAC administration APIs (owner / staff.manage permission)."""
from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.audit.services import AuditService
from apps.core.constants import Perm
from apps.core.permissions import IsStaffWithPermission

from .models import Permission, Role, StaffProfile, User
from .serializers import (
    PermissionSerializer,
    RoleSerializer,
    StaffCreateSerializer,
    StaffProfileSerializer,
)


class PermissionViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsStaffWithPermission]
    serializer_class = PermissionSerializer
    queryset = Permission.objects.all()
    pagination_class = None


class RoleViewSet(viewsets.ModelViewSet):
    permission_classes = [IsStaffWithPermission]
    permission_codename = Perm.STAFF_MANAGE
    serializer_class = RoleSerializer
    queryset = Role.objects.prefetch_related("permissions").all()

    def destroy(self, request, *args, **kwargs):
        role = self.get_object()
        if role.is_system:
            return Response(
                {"status": "error", "error": {"code": "system_role", "message": "System roles cannot be deleted.", "fields": None}},
                status=status.HTTP_409_CONFLICT,
            )
        if role.staff_profiles.filter(is_active=True).exists():
            return Response(
                {"status": "error", "error": {"code": "role_in_use", "message": "Role has active staff assigned.", "fields": None}},
                status=status.HTTP_409_CONFLICT,
            )
        AuditService.log(request.user, "staff.role.delete", "Role", role.pk, {"name": role.name}, request=request)
        return super().destroy(request, *args, **kwargs)

    def perform_create(self, serializer):
        role = serializer.save()
        AuditService.log(self.request.user, "staff.role.create", "Role", role.pk, {"name": role.name}, request=self.request)

    def perform_update(self, serializer):
        role = serializer.save()
        AuditService.log(self.request.user, "staff.role.update", "Role", role.pk, {"name": role.name}, request=self.request)


class StaffViewSet(viewsets.ModelViewSet):
    permission_classes = [IsStaffWithPermission]
    permission_codename = Perm.STAFF_MANAGE
    serializer_class = StaffProfileSerializer
    queryset = StaffProfile.objects.select_related("user", "role").all()
    http_method_names = ["get", "post", "patch", "delete"]

    def get_serializer_class(self):
        if self.action == "create":
            return StaffCreateSerializer
        return StaffProfileSerializer

    def create(self, request, *args, **kwargs):
        serializer = StaffCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            profile = serializer.save()
        AuditService.log(
            request.user, "staff.create", "StaffProfile", profile.pk,
            {"email": profile.user.email, "role": profile.role.name if profile.role else None},
            request=request,
        )
        return Response(StaffProfileSerializer(profile).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        profile = self.get_object()
        if profile.user == request.user:
            return Response(
                {"status": "error", "error": {"code": "self_deactivate", "message": "You cannot deactivate your own staff account here.", "fields": None}},
                status=400,
            )
        profile.is_active = False
        profile.save(update_fields=["is_active"])
        AuditService.log(request.user, "staff.deactivate", "StaffProfile", profile.pk, {}, request=request)
        return Response({"status": "success", "message": "Staff account deactivated."})

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        profile = self.get_object()
        profile.is_active = True
        profile.save(update_fields=["is_active"])
        AuditService.log(request.user, "staff.activate", "StaffProfile", profile.pk, {}, request=request)
        return Response({"status": "success", "message": "Staff account activated."})

    def perform_destroy(self, instance):
        AuditService.log(self.request.user, "staff.delete", "StaffProfile", instance.pk, {"email": instance.user.email}, request=self.request)
        instance.delete()
