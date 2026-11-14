"""Report export builders: CSV, Excel (openpyxl), PDF (reportlab)."""
import csv
import io


def to_csv(rows, headers):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers)
    for row in rows:
        writer.writerow([row.get(h, "") for h in headers])
    return buffer.getvalue()


def to_xlsx(rows, headers, sheet_name="Report"):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name[:31]
    ws.append(headers)
    for row in rows:
        ws.append([row.get(h, "") for h in headers])
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def to_pdf(rows, headers, title="STARMOND TECHNOLOGY LIMITED — Report"):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), title=title)
    styles = getSampleStyleSheet()
    elements = [Paragraph(title, styles["Title"]), Spacer(1, 12)]
    data = [headers] + [[str(row.get(h, ""))[:60] for h in headers] for row in rows]
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b1f3a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f5f7")]),
    ]))
    elements.append(table)
    doc.build(elements)
    return buffer.getvalue()


def export_response(rows, headers, fmt, filename, title):
    from django.http import HttpResponse
    fmt = (fmt or "json").lower()
    if fmt == "csv":
        response = HttpResponse(to_csv(rows, headers), content_type="text/csv; charset=utf-8")
    elif fmt in ("xlsx", "excel"):
        response = HttpResponse(to_xlsx(rows, headers),
                                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    elif fmt == "pdf":
        response = HttpResponse(to_pdf(rows, headers, title=title), content_type="application/pdf")
    else:
        from rest_framework.response import Response as JsonResponse
        return JsonResponse({"status": "success", "data": {"headers": headers, "rows": rows}})
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
