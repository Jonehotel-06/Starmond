import django_filters as filters
from rest_framework import mixins, viewsets

from apps.core.constants import Perm
from apps.core.permissions import IsStaffWithPermission

from .models import EmailLog
from .serializers import EmailLogSerializer


class EmailLogFilter(filters.FilterSet):
    date_from = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")

    class Meta:
        model = EmailLog
        fields = ["status", "template_key", "recipient"]


class StaffEmailLogViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Email delivery logs. Message bodies are NOT exposed here (privacy)."""
    permission_classes = [IsStaffWithPermission]
    permission_codename = Perm.NOTIFICATIONS_MANAGE
    serializer_class = EmailLogSerializer
    queryset = EmailLog.objects.select_related("related_order").all()
    filterset_class = EmailLogFilter
    search_fields = ["recipient", "subject"]
    ordering = ["-created_at"]
