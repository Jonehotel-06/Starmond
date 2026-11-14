from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.categories.models import Category
from apps.core.constants import Perm
from apps.core.permissions import IsStaffWithPermission
from apps.orders.models import Order
from apps.orders.serializers import OrderSummarySerializer
from apps.refunds.models import Refund
from services.report_service import ReportService, resolve_range


from drf_spectacular.utils import OpenApiTypes, extend_schema

@extend_schema(tags=["dashboard"], responses=OpenApiTypes.OBJECT)
class DashboardOverviewView(APIView):
    """GET /api/dashboard/overview/?range=today|yesterday|week|month|last_month|custom
       &date_from=YYYY-MM-DD&date_to=YYYY-MM-DD

    All figures are database-driven. Realized revenue counts ONLY verified
    successful payments — never pending orders."""
    permission_classes = [IsStaffWithPermission]
    permission_codename = Perm.DASHBOARD_VIEW

    def get(self, request):
        start, end = resolve_range(request.query_params.get("range", "month"),
                                   request.query_params.get("date_from"),
                                   request.query_params.get("date_to"))
        financials = ReportService.financial_summary(start, end)
        inventory = ReportService.inventory_health()
        recent_orders = Order.objects.select_related("customer").prefetch_related("items").order_by("-placed_at")[:10]
        data = {
            "range": {"start": start.isoformat(), "end": end.isoformat()},
            "financials": financials,
            "inventory": inventory,
            "totals": {
                "total_customers": User.objects.filter(is_superuser=False, is_staff=False).count(),
                "total_categories": Category.objects.count(),
                "active_categories": Category.objects.active().count(),
                "pending_orders": Order.objects.filter(status=Order.Status.PENDING_PAYMENT).count(),
                "orders_to_fulfil": Order.objects.filter(status__in=[
                    Order.Status.PAID, Order.Status.PROCESSING, Order.Status.PACKED]).count(),
                "open_refund_requests": Refund.objects.filter(status=Refund.Status.REQUESTED).count(),
            },
            "recent_orders": OrderSummarySerializer(recent_orders, many=True).data,
            "best_sellers": ReportService.best_selling_products(start, end, limit=10),
            "sales_trend": ReportService.sales_by_day(start, end),
        }
        return Response({"status": "success", "data": data})
