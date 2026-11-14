from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import AuditService
from apps.core.constants import Perm
from apps.core.permissions import IsStaffWithPermission, user_has_permission
from services.report_service import ReportService, resolve_range

from .exports import export_response


def _params(request):
    return resolve_range(request.query_params.get("range", "month"),
                         request.query_params.get("date_from"),
                         request.query_params.get("date_to"))


def _fmt(request):
    return request.query_params.get("format", "json")


def _check(request, view):
    if not user_has_permission(request.user, Perm.REPORTS_VIEW):
        from apps.core.exceptions import ServiceError
        raise ServiceError("You lack the reports.view permission.", code="permission_denied", status_code=403)


from drf_spectacular.utils import OpenApiTypes, extend_schema

@extend_schema(tags=["reports"], responses=OpenApiTypes.OBJECT)
class SalesReportView(APIView):
    """GET /api/reports/sales/?range=month&format=csv|xlsx|pdf"""
    permission_classes = [IsStaffWithPermission]
    permission_codename = Perm.REPORTS_VIEW

    def get(self, request):
        start, end = _params(request)
        summary = ReportService.financial_summary(start, end)
        trend = ReportService.sales_by_day(start, end)
        if _fmt(request) != "json":
            rows = [{"date": t["date"], "revenue": t["revenue"], "payments": t["payments"]} for t in trend]
            rows.insert(0, {"date": "SUMMARY", "revenue": summary["collected_revenue"], "payments": summary["orders_paid"]})
            AuditService.log(request.user, "report.export", "Report", "sales", {"format": _fmt(request)}, request=request)
            return export_response(rows, ["date", "revenue", "payments"], _fmt(request),
                                   f"starmond-sales-{start.date()}-{end.date()}.{_fmt(request)}",
                                   "Sales Report")
        return Response({"status": "success", "data": {"summary": summary, "trend": trend}})


@extend_schema(tags=["reports"], responses=OpenApiTypes.OBJECT)
class CategoryReportView(APIView):
    permission_classes = [IsStaffWithPermission]
    permission_codename = Perm.REPORTS_VIEW

    def get(self, request):
        start, end = _params(request)
        rows = ReportService.sales_by_category(start, end)
        if _fmt(request) != "json":
            AuditService.log(request.user, "report.export", "Report", "categories", {"format": _fmt(request)}, request=request)
            return export_response(rows, ["category", "revenue", "units"], _fmt(request),
                                   f"starmond-sales-by-category.{_fmt(request)}", "Sales by Category")
        return Response({"status": "success", "data": rows})


@extend_schema(tags=["reports"], responses=OpenApiTypes.OBJECT)
class ProductReportView(APIView):
    permission_classes = [IsStaffWithPermission]
    permission_codename = Perm.REPORTS_VIEW

    def get(self, request):
        start, end = _params(request)
        rows = ReportService.best_selling_products(start, end, limit=200)
        if _fmt(request) != "json":
            AuditService.log(request.user, "report.export", "Report", "products", {"format": _fmt(request)}, request=request)
            return export_response(rows, ["sku", "name", "units", "revenue"], _fmt(request),
                                   f"starmond-best-selling-products.{_fmt(request)}", "Best-Selling Products")
        return Response({"status": "success", "data": rows})


@extend_schema(tags=["reports"], responses=OpenApiTypes.OBJECT)
class PaymentsReportView(APIView):
    permission_classes = [IsStaffWithPermission]
    permission_codename = Perm.FINANCE_VIEW

    def get(self, request):
        start, end = _params(request)
        rows = ReportService.payment_ledger(start, end)
        headers = ["reference", "order_reference", "provider_reference", "amount", "currency",
                   "status", "channel", "initialized_at", "verified_at"]
        if _fmt(request) != "json":
            AuditService.log(request.user, "report.export", "Report", "payments", {"format": _fmt(request)}, request=request)
            return export_response(rows, headers, _fmt(request),
                                   f"starmond-payment-ledger.{_fmt(request)}", "Payment Ledger")
        return Response({"status": "success", "data": rows})


@extend_schema(tags=["reports"], responses=OpenApiTypes.OBJECT)
class RefundsReportView(APIView):
    permission_classes = [IsStaffWithPermission]
    permission_codename = Perm.FINANCE_VIEW

    def get(self, request):
        start, end = _params(request)
        rows = ReportService.refund_ledger(start, end)
        headers = ["reference", "order_reference", "requested_amount", "approved_amount", "status", "processed_at"]
        if _fmt(request) != "json":
            AuditService.log(request.user, "report.export", "Report", "refunds", {"format": _fmt(request)}, request=request)
            return export_response(rows, headers, _fmt(request),
                                   f"starmond-refund-ledger.{_fmt(request)}", "Refund Ledger")
        return Response({"status": "success", "data": rows})


@extend_schema(tags=["reports"], responses=OpenApiTypes.OBJECT)
class OrdersReportView(APIView):
    permission_classes = [IsStaffWithPermission]
    permission_codename = Perm.REPORTS_VIEW

    def get(self, request):
        start, end = _params(request)
        from apps.orders.models import Order
        qs = Order.objects.filter(placed_at__gte=start, placed_at__lt=end).select_related("customer")
        rows = [{
            "reference": o.reference, "date": o.placed_at.date().isoformat(), "customer": o.contact_email,
            "status": o.status, "payment_status": o.payment_status, "subtotal": str(o.subtotal_amount),
            "discount": str(o.discount_amount), "shipping": str(o.shipping_fee), "total": str(o.total_amount),
        } for o in qs[:5000]]
        headers = ["reference", "date", "customer", "status", "payment_status", "subtotal", "discount", "shipping", "total"]
        if _fmt(request) != "json":
            AuditService.log(request.user, "report.export", "Report", "orders", {"format": _fmt(request)}, request=request)
            return export_response(rows, headers, _fmt(request),
                                   f"starmond-orders.{_fmt(request)}", "Orders Report")
        return Response({"status": "success", "data": rows})
