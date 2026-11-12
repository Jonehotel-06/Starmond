"""Financial reporting endpoints with CSV / Excel / PDF exports."""
from __future__ import annotations

from django.http import HttpResponse
from rest_framework.permissions import IsAuthenticated

from apps.core.permissions import IsStaff, RequiresPermission
from apps.core.views import BaseAPIView
from apps.reports.services import DateRange, ReportService


class ReportPermission(IsStaff):
    pass


class SalesSummaryView(BaseAPIView):
    permission_classes = [IsStaff, RequiresPermission.of("orders.view_order")]

    def get(self, request):
        period = DateRange.from_request(
            request.query_params.get("start"), request.query_params.get("end"),
            int(request.query_params.get("days", 30) or 30),
        )
        return self.ok(ReportService.sales_summary(period))


class FullReportView(BaseAPIView):
    permission_classes = [IsStaff, RequiresPermission.of("orders.view_order")]

    def get(self, request):
        period = DateRange.from_request(
            request.query_params.get("start"), request.query_params.get("end")
        )
        return self.ok(ReportService.full_report(period))


class ReportExportView(BaseAPIView):
    """
    Streams a report export.

    Every export is stamped with the period it covers so a downloaded file can
    never be mistaken for a different reporting window.
    """

    permission_classes = [IsStaff, RequiresPermission.of("orders.view_order")]

    def get(self, request, fmt: str):
        period = DateRange.from_request(
            request.query_params.get("start"), request.query_params.get("end")
        )
        from apps.audit.services import AuditService

        AuditService.record(
            action="export", entity_type="report", entity_id=fmt, actor=request.user,
            summary=f"Exported {fmt} report for {period.label}",
        )
        stamp = f"{period.start:%Y%m%d}-{period.end:%Y%m%d}"

        if fmt == "csv":
            content = ReportService.export_csv(period)
            response = HttpResponse(content, content_type="text/csv")
            response["Content-Disposition"] = f'attachment; filename="starmond-sales-{stamp}.csv"'
            return response
        if fmt in {"xlsx", "excel"}:
            content = ReportService.export_xlsx(period)
            response = HttpResponse(
                content,
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            response["Content-Disposition"] = f'attachment; filename="starmond-sales-{stamp}.xlsx"'
            return response
        if fmt == "pdf":
            content = ReportService.export_pdf(period)
            response = HttpResponse(content, content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="starmond-sales-{stamp}.pdf"'
            return response

        from apps.core.exceptions import ValidationError

        raise ValidationError("Supported export formats are csv, xlsx and pdf.")
