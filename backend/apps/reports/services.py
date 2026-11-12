"""
ReportService — accurate, auditable financial reporting (Section 22).

Invariants:

* **Unpaid orders are never counted as revenue.** Realised revenue is derived
  from *verified successful payments*, not from order totals.
* A payment contributes exactly once — the ``Payment`` row is the unit of
  financial truth, and refunds are subtracted from it.
* Discounts, shipping income and taxes are reported separately so gross and net
  sales can be reconciled to the naira.
"""
from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncDate, TruncMonth
from django.utils import timezone

from apps.core.utils import money
from apps.orders.models import Order, OrderItem
from apps.payments.models import Payment
from apps.refunds.models import Refund

logger = logging.getLogger("apps.reports")

ZERO = Decimal("0.00")


def _sum(queryset, field_name: str) -> Decimal:
    return money(
        queryset.aggregate(
            total=Coalesce(Sum(field_name), Value(ZERO), output_field=DecimalField())
        )["total"]
    )


@dataclass
class DateRange:
    start: datetime
    end: datetime

    @classmethod
    def from_request(cls, start: str | None = None, end: str | None = None,
                     default_days: int = 30) -> "DateRange":
        tz = timezone.get_current_timezone()
        end_date = _parse_date(end) or timezone.localdate()
        start_date = _parse_date(start) or (end_date - timedelta(days=default_days - 1))
        if start_date > end_date:
            start_date, end_date = end_date, start_date
        return cls(
            start=timezone.make_aware(datetime.combine(start_date, time.min), tz),
            end=timezone.make_aware(datetime.combine(end_date, time.max), tz),
        )

    @property
    def label(self) -> str:
        return f"{self.start:%d %b %Y} – {self.end:%d %b %Y}"

    def as_dict(self) -> dict:
        return {"start": self.start.date().isoformat(), "end": self.end.date().isoformat(),
                "label": self.label}


def _parse_date(value) -> date | None:
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        return None


class ReportService:
    # ------------------------------------------------------------------
    # Headline sales report
    # ------------------------------------------------------------------
    @staticmethod
    def sales_summary(period: DateRange) -> dict:
        """
        The canonical sales report.

        ``gross_sales`` counts every order placed in the window (including
        unpaid ones, for pipeline visibility) while ``net_sales`` and
        ``realised_revenue`` count only verified money.
        """
        orders_in_range = Order.objects.filter(created_at__range=(period.start, period.end))
        paid_orders = orders_in_range.filter(
            payment_status__in=[
                Order.PaymentStatus.PAID,
                Order.PaymentStatus.PARTIALLY_REFUNDED,
                Order.PaymentStatus.REFUNDED,
            ]
        )

        successful_payments = Payment.objects.filter(
            status__in=[
                Payment.Status.SUCCESS, Payment.Status.PARTIALLY_REFUNDED, Payment.Status.REFUNDED,
            ],
            is_verified=True,
            paid_at__range=(period.start, period.end),
        )
        pending_payments = Payment.objects.filter(
            status__in=[Payment.Status.INITIALIZED, Payment.Status.PENDING],
            created_at__range=(period.start, period.end),
        )
        failed_payments = Payment.objects.filter(
            status=Payment.Status.FAILED,
            created_at__range=(period.start, period.end),
        )
        completed_refunds = Refund.objects.filter(
            status=Refund.Status.COMPLETED,
            completed_at__range=(period.start, period.end),
        )

        gross_merchandise = _sum(paid_orders, "subtotal")
        discounts = _sum(paid_orders, "discount_total")
        shipping_income = _sum(paid_orders, "shipping_total")
        tax_collected = _sum(paid_orders, "tax_total")
        refunds_total = _sum(completed_refunds, "amount_refunded")

        # Revenue is measured from payments so it can never double-count an order.
        collected = _sum(successful_payments, "amount_verified")
        net_sales = money(collected - refunds_total)

        paid_count = paid_orders.count()
        total_orders = orders_in_range.count()

        return {
            "period": period.as_dict(),
            "currency": "NGN",
            "orders": {
                "total_placed": total_orders,
                "paid": paid_count,
                "pending_payment": orders_in_range.filter(
                    status=Order.Status.PENDING_PAYMENT
                ).count(),
                "cancelled": orders_in_range.filter(status=Order.Status.CANCELLED).count(),
                "expired": orders_in_range.filter(status=Order.Status.EXPIRED).count(),
                "completed": orders_in_range.filter(status=Order.Status.COMPLETED).count(),
                "conversion_rate_percent": round((paid_count / total_orders) * 100, 2)
                if total_orders else 0.0,
            },
            "sales": {
                # Gross = merchandise value of paid orders, before discounts.
                "gross_sales": str(money(gross_merchandise + shipping_income + tax_collected)),
                "merchandise_value": str(gross_merchandise),
                "discounts_given": str(discounts),
                "net_sales": str(net_sales),
                "product_revenue": str(money(gross_merchandise - discounts)),
                "shipping_revenue": str(shipping_income),
                "tax_collected": str(tax_collected),
                "refunds": str(refunds_total),
                "total_collected": str(collected),
            },
            "payments": {
                "successful_count": successful_payments.count(),
                "successful_amount": str(collected),
                "pending_count": pending_payments.count(),
                "pending_amount": str(_sum(pending_payments, "amount")),
                "failed_count": failed_payments.count(),
                "failed_amount": str(_sum(failed_payments, "amount")),
            },
            "averages": {
                "average_order_value": str(
                    money(_sum(paid_orders, "grand_total") / paid_count) if paid_count else ZERO
                ),
                "average_items_per_order": round(
                    (
                        sum(o.item_count for o in paid_orders.prefetch_related("items")) / paid_count
                    ) if paid_count else 0.0,
                    2,
                ),
            },
            "data_integrity": ReportService.integrity_checks(period),
        }

    # ------------------------------------------------------------------
    # Integrity
    # ------------------------------------------------------------------
    @staticmethod
    def integrity_checks(period: DateRange) -> dict:
        """
        Cross-checks that payment totals agree with order totals.

        Surfaced on the dashboard so a discrepancy is visible, not buried.
        """
        paid_orders = Order.objects.filter(
            payment_status__in=[
                Order.PaymentStatus.PAID,
                Order.PaymentStatus.PARTIALLY_REFUNDED,
                Order.PaymentStatus.REFUNDED,
            ],
            paid_at__range=(period.start, period.end),
        )
        discrepancies = []
        for order in paid_orders.iterator():
            verified = _sum(
                order.payments.filter(is_verified=True,
                                      status__in=[Payment.Status.SUCCESS,
                                                  Payment.Status.PARTIALLY_REFUNDED,
                                                  Payment.Status.REFUNDED]),
                "amount_verified",
            )
            if verified != money(order.amount_paid):
                discrepancies.append(
                    {
                        "order_number": order.order_number,
                        "order_amount_paid": str(money(order.amount_paid)),
                        "verified_payments_total": str(verified),
                        "difference": str(money(verified - money(order.amount_paid))),
                    }
                )
        return {
            "checked_orders": paid_orders.count(),
            "discrepancies": discrepancies[:50],
            "discrepancy_count": len(discrepancies),
            "healthy": not discrepancies,
        }

    # ------------------------------------------------------------------
    # Breakdowns
    # ------------------------------------------------------------------
    @staticmethod
    def product_sales(period: DateRange, limit: int = 50) -> list[dict]:
        rows = (
            OrderItem.objects.filter(
                order__paid_at__range=(period.start, period.end),
                order__payment_status__in=[
                    Order.PaymentStatus.PAID, Order.PaymentStatus.PARTIALLY_REFUNDED,
                    Order.PaymentStatus.REFUNDED,
                ],
            )
            .values("product_id", "product_name", "sku")
            .annotate(
                units=Coalesce(Sum("quantity"), Value(0)),
                revenue=Coalesce(Sum("line_total"), Value(ZERO), output_field=DecimalField()),
                refunded_units=Coalesce(Sum("refunded_quantity"), Value(0)),
            )
            .order_by("-revenue")[:limit]
        )
        return [
            {
                "product_id": str(row["product_id"]),
                "product_name": row["product_name"],
                "sku": row["sku"],
                "units_sold": row["units"],
                "refunded_units": row["refunded_units"],
                "revenue": str(money(row["revenue"])),
            }
            for row in rows
        ]

    @staticmethod
    def best_sellers(period: DateRange, limit: int = 10) -> list[dict]:
        return ReportService.product_sales(period, limit=limit)

    @staticmethod
    def category_sales(period: DateRange, limit: int = 50) -> list[dict]:
        rows = (
            OrderItem.objects.filter(
                order__paid_at__range=(period.start, period.end),
                order__payment_status__in=[
                    Order.PaymentStatus.PAID, Order.PaymentStatus.PARTIALLY_REFUNDED,
                    Order.PaymentStatus.REFUNDED,
                ],
            )
            .values("category_name")
            .annotate(
                units=Coalesce(Sum("quantity"), Value(0)),
                revenue=Coalesce(Sum("line_total"), Value(ZERO), output_field=DecimalField()),
            )
            .order_by("-revenue")[:limit]
        )
        return [
            {
                "category": row["category_name"] or "Uncategorised",
                "units_sold": row["units"],
                "revenue": str(money(row["revenue"])),
            }
            for row in rows
        ]

    @staticmethod
    def daily_series(period: DateRange) -> list[dict]:
        rows = (
            Order.objects.filter(
                paid_at__range=(period.start, period.end),
                payment_status__in=[
                    Order.PaymentStatus.PAID, Order.PaymentStatus.PARTIALLY_REFUNDED,
                    Order.PaymentStatus.REFUNDED,
                ],
            )
            .annotate(day=TruncDate("paid_at"))
            .values("day")
            .annotate(
                orders=Count("id"),
                revenue=Coalesce(Sum("grand_total"), Value(ZERO), output_field=DecimalField()),
            )
            .order_by("day")
        )
        return [
            {"date": row["day"].isoformat(), "orders": row["orders"], "revenue": str(money(row["revenue"]))}
            for row in rows
        ]

    @staticmethod
    def monthly_series(period: DateRange) -> list[dict]:
        rows = (
            Order.objects.filter(
                paid_at__range=(period.start, period.end),
                payment_status__in=[
                    Order.PaymentStatus.PAID, Order.PaymentStatus.PARTIALLY_REFUNDED,
                    Order.PaymentStatus.REFUNDED,
                ],
            )
            .annotate(month=TruncMonth("paid_at"))
            .values("month")
            .annotate(
                orders=Count("id"),
                revenue=Coalesce(Sum("grand_total"), Value(ZERO), output_field=DecimalField()),
                refunds=Coalesce(Sum("amount_refunded"), Value(ZERO), output_field=DecimalField()),
            )
            .order_by("month")
        )
        return [
            {
                "month": row["month"].strftime("%Y-%m"),
                "orders": row["orders"],
                "revenue": str(money(row["revenue"])),
                "refunds": str(money(row["refunds"])),
            }
            for row in rows
        ]

    @staticmethod
    def payment_method_breakdown(period: DateRange) -> list[dict]:
        rows = (
            Payment.objects.filter(is_verified=True, paid_at__range=(period.start, period.end))
            .values("channel")
            .annotate(
                count=Count("id"),
                amount=Coalesce(Sum("amount_verified"), Value(ZERO), output_field=DecimalField()),
            )
            .order_by("-amount")
        )
        return [
            {"channel": row["channel"] or "unknown", "count": row["count"],
             "amount": str(money(row["amount"]))}
            for row in rows
        ]

    @staticmethod
    def refund_report(period: DateRange) -> dict:
        completed = Refund.objects.filter(
            status=Refund.Status.COMPLETED, completed_at__range=(period.start, period.end)
        )
        open_refunds = Refund.objects.filter(
            status__in=[Refund.Status.REQUESTED, Refund.Status.UNDER_REVIEW,
                        Refund.Status.APPROVED, Refund.Status.PROCESSING]
        )
        return {
            "completed_count": completed.count(),
            "completed_amount": str(_sum(completed, "amount_refunded")),
            "pending_count": open_refunds.count(),
            "pending_amount": str(_sum(open_refunds, "amount_requested")),
            "rejection_rate_percent": round(
                (
                    Refund.objects.filter(status=Refund.Status.REJECTED,
                                          created_at__range=(period.start, period.end)).count()
                    / max(Refund.objects.filter(created_at__range=(period.start, period.end)).count(), 1)
                ) * 100,
                2,
            ),
        }

    @staticmethod
    def full_report(period: DateRange) -> dict:
        return {
            "period": period.as_dict(),
            "summary": ReportService.sales_summary(period),
            "daily": ReportService.daily_series(period),
            "monthly": ReportService.monthly_series(period),
            "top_products": ReportService.product_sales(period, limit=20),
            "categories": ReportService.category_sales(period, limit=20),
            "payment_methods": ReportService.payment_method_breakdown(period),
            "refunds": ReportService.refund_report(period),
        }

    # ------------------------------------------------------------------
    # Exports
    # ------------------------------------------------------------------
    @staticmethod
    def export_csv(period: DateRange) -> str:
        report = ReportService.sales_summary(period)
        buffer = io.StringIO()
        writer = csv.writer(buffer)

        writer.writerow(["STARMOND TECHNOLOGY LIMITED — Sales Report"])
        writer.writerow(["Period", period.label])
        writer.writerow(["Generated", timezone.now().isoformat()])
        writer.writerow([])
        writer.writerow(["Metric", "Value"])
        for key, value in report["sales"].items():
            writer.writerow([key.replace("_", " ").title(), value])
        writer.writerow([])
        writer.writerow(["Orders", ""])
        for key, value in report["orders"].items():
            writer.writerow([key.replace("_", " ").title(), value])
        writer.writerow([])
        writer.writerow(["Payments", ""])
        for key, value in report["payments"].items():
            writer.writerow([key.replace("_", " ").title(), value])
        writer.writerow([])
        writer.writerow(["Product", "SKU", "Units sold", "Refunded units", "Revenue (NGN)"])
        for row in ReportService.product_sales(period, limit=500):
            writer.writerow([row["product_name"], row["sku"], row["units_sold"],
                             row["refunded_units"], row["revenue"]])
        return buffer.getvalue()

    @staticmethod
    def export_xlsx(period: DateRange) -> bytes:
        from openpyxl import Workbook
        from openpyxl.styles import Font

        report = ReportService.sales_summary(period)
        workbook = Workbook()

        summary = workbook.active
        summary.title = "Summary"
        summary.append(["STARMOND TECHNOLOGY LIMITED — Sales Report"])
        summary.append(["Period", period.label])
        summary.append([])
        summary.append(["Metric", "Value"])
        for header in summary[4]:
            header.font = Font(bold=True)
        for key, value in {**report["sales"], **report["orders"], **report["payments"]}.items():
            summary.append([key.replace("_", " ").title(), value])

        products = workbook.create_sheet("Product sales")
        products.append(["Product", "SKU", "Units sold", "Refunded units", "Revenue (NGN)"])
        for cell in products[1]:
            cell.font = Font(bold=True)
        for row in ReportService.product_sales(period, limit=1000):
            products.append([row["product_name"], row["sku"], row["units_sold"],
                             row["refunded_units"], float(row["revenue"])])

        categories = workbook.create_sheet("Category sales")
        categories.append(["Category", "Units sold", "Revenue (NGN)"])
        for cell in categories[1]:
            cell.font = Font(bold=True)
        for row in ReportService.category_sales(period, limit=500):
            categories.append([row["category"], row["units_sold"], float(row["revenue"])])

        daily = workbook.create_sheet("Daily")
        daily.append(["Date", "Orders", "Revenue (NGN)"])
        for cell in daily[1]:
            cell.font = Font(bold=True)
        for row in ReportService.daily_series(period):
            daily.append([row["date"], row["orders"], float(row["revenue"])])

        for sheet in workbook.worksheets:
            for column in sheet.columns:
                width = max((len(str(c.value)) if c.value is not None else 0) for c in column) + 3
                sheet.column_dimensions[column[0].column_letter].width = min(width, 48)

        buffer = io.BytesIO()
        workbook.save(buffer)
        return buffer.getvalue()

    @staticmethod
    def export_pdf(period: DateRange) -> bytes:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
        )

        report = ReportService.sales_summary(period)
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm,
            leftMargin=16 * mm, rightMargin=16 * mm,
            title=f"Sales report {period.label}",
        )
        styles = getSampleStyleSheet()
        story = [
            Paragraph("STARMOND TECHNOLOGY LIMITED", styles["Title"]),
            Paragraph(f"Sales report — {period.label}", styles["Heading2"]),
            Spacer(1, 8),
        ]

        def table_from(mapping: dict, title: str):
            rows = [["Metric", "Value"]] + [
                [key.replace("_", " ").title(), str(value)] for key, value in mapping.items()
            ]
            table = Table(rows, colWidths=[95 * mm, 70 * mm], hAlign="LEFT")
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b1f3a")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d6dae1")),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f7f9")]),
                    ]
                )
            )
            story.extend([Paragraph(title, styles["Heading3"]), table, Spacer(1, 10)])

        table_from(report["sales"], "Revenue")
        table_from(report["orders"], "Orders")
        table_from(report["payments"], "Payments")

        top = ReportService.product_sales(period, limit=15)
        if top:
            rows = [["Product", "SKU", "Units", "Revenue (NGN)"]] + [
                [row["product_name"][:48], row["sku"], str(row["units_sold"]), row["revenue"]]
                for row in top
            ]
            table = Table(rows, colWidths=[75 * mm, 35 * mm, 20 * mm, 35 * mm], hAlign="LEFT")
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b1f3a")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 8),
                        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d6dae1")),
                    ]
                )
            )
            story.extend([Paragraph("Top products", styles["Heading3"]), table])

        story.append(Spacer(1, 12))
        story.append(
            Paragraph(
                "Revenue is recognised only from verified successful payments. "
                "Unpaid orders are excluded from all revenue figures.",
                styles["Italic"],
            )
        )
        doc.build(story)
        return buffer.getvalue()
