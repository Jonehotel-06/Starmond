"""Staff-facing customer directory (customers.view permission)."""
from django.db.models import Count, DecimalField, Sum, Value
from django.db.models.functions import Coalesce
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.constants import Perm
from apps.core.pagination import StandardPagination
from apps.core.permissions import IsStaffWithPermission
from apps.orders.models import Order

from .models import CustomerProfile
from .serializers import StaffCustomerSerializer


from drf_spectacular.utils import OpenApiTypes, extend_schema

@extend_schema(tags=["admin-customers"], responses=StaffCustomerSerializer(many=True))
class StaffCustomerListView(APIView):
    permission_classes = [IsStaffWithPermission]
    permission_codename = Perm.CUSTOMERS_VIEW

    def get(self, request):
        qs = CustomerProfile.objects.select_related("user").all()
        search = (request.query_params.get("search") or request.query_params.get("q") or "").strip()
        if search:
            from django.db.models import Q
            qs = qs.filter(Q(user__email__icontains=search) | Q(user__full_name__icontains=search) | Q(user__phone__icontains=search))
        qs = qs.annotate(
            orders_count=Count("user__orders", distinct=True),
            total_spent=Coalesce(
                Sum("user__orders__total_amount", filter=Q_paid()),
                Value(0), output_field=DecimalField(max_digits=14, decimal_places=2),
            ),
        ).order_by("-user__date_joined")
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        data = [
            {
                "id": p.user_id, "email": p.user.email, "full_name": p.user.full_name,
                "phone": p.user.phone, "is_email_verified": p.user.is_email_verified,
                "date_joined": p.user.date_joined, "orders_count": p.orders_count,
                "total_spent": p.total_spent,
            }
            for p in page
        ]
        return paginator.get_paginated_response(StaffCustomerSerializer(data, many=True).data)


def Q_paid():
    from django.db.models import Q
    # The queryset is rooted at CustomerProfile, so orders are reached through `user`.
    return Q(user__orders__payment_status__in=[
        Order.PaymentStatus.PAID,
        Order.PaymentStatus.PARTIALLY_REFUNDED,
        Order.PaymentStatus.REFUNDED,
    ])
