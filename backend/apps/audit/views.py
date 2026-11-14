import django_filters as filters
from rest_framework import mixins, viewsets

from apps.core.constants import Perm
from apps.core.permissions import IsStaffWithPermission

from .models import AuditLog
from .serializers import AuditLogSerializer


class AuditLogFilter(filters.FilterSet):
    action = filters.CharFilter(lookup_expr="icontains")
    entity_type = filters.CharFilter(lookup_expr="exact")
    entity_id = filters.CharFilter(lookup_expr="exact")
    date_from = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    date_to = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = AuditLog
        fields = ["action", "entity_type", "entity_id", "date_from", "date_to"]


class AuditLogViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsStaffWithPermission]
    permission_codename = Perm.AUDIT_VIEW
    serializer_class = AuditLogSerializer
    queryset = AuditLog.objects.select_related("actor").all()
    filterset_class = AuditLogFilter
    ordering = ["-created_at"]
