"""Administration dashboard data services (Section 20)."""
from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework.permissions import IsAuthenticated

from apps.core.permissions import IsStaff, RequiresPermission
from apps.core.pagination import StandardResultsSetPagination
from apps.core.views import BaseAPIView
from apps.dashboard.services import DashboardService

User = get_user_model()


class DashboardOverviewView(BaseAPIView):
    permission_classes = [IsStaff, RequiresPermission.of("orders.view_order")]

    def get(self, request):
        try:
            days = min(int(request.query_params.get("days", 30)), 365)
        except (TypeError, ValueError):
            days = 30
        return self.ok({
            "overview": DashboardService.overview(days),
            "recent_orders": DashboardService.recent_orders(10),
            "low_stock": DashboardService.low_stock_alerts(10),
            "top_products": DashboardService.top_products(days, 5),
        })


class DashboardLowStockView(BaseAPIView):
    permission_classes = [IsStaff, RequiresPermission.of("inventory.view_inventory")]

    def get(self, request):
        return self.ok({"low_stock": DashboardService.low_stock_alerts(100)})


class StaffCustomerListView(BaseAPIView):
    permission_classes = [IsStaff, RequiresPermission.of("accounts.view_user")]

    def get(self, request):
        queryset = User.objects.filter(is_staff=False).order_by("-date_joined")
        search = request.query_params.get("q")
        if search:
            from django.db.models import Q

            queryset = queryset.filter(
                Q(email__icontains=search) | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
            )
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response([
            {
                "id": str(user.pk),
                "email": user.email,
                "name": user.full_name,
                "phone": user.phone,
                "is_email_verified": user.is_email_verified,
                "order_count": getattr(getattr(user, "customer_profile", None), "order_count", 0),
                "lifetime_value": str(
                    getattr(getattr(user, "customer_profile", None), "lifetime_value", 0)
                ),
                "date_joined": user.date_joined.isoformat(),
            }
            for user in page
        ])
