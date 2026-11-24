"""Desk endpoints for the AMF Sales Analytics page."""

import csv
import io
from datetime import date
from decimal import Decimal

import frappe
from frappe import _
from frappe.permissions import can_export
from frappe.utils import cint, now_datetime, nowdate
from frappe.utils.xlsxutils import make_xlsx

from amf.amf.sales_analytics.access import Access
from amf.amf.sales_analytics.definitions import COMPANY, Filters
from amf.amf.sales_analytics.service import DETAILS, SalesAnalytics, detail_columns, public_row
from amf.amf.sales_analytics.sources import DELIVERY, INVOICE, LEDGER, ORDER, Sources

EXPORT_SOURCES = {
    "item_net": (INVOICE,), "revenue": (INVOICE,), "shipping": (INVOICE,), "card_charges": (INVOICE,),
    "gross": (INVOICE,), "vat": (INVOICE,), "order_intake": (ORDER,), "order_items": (ORDER,), "order_changes": (ORDER,),
    "undelivered": (ORDER,), "overdue": (ORDER,), "held_shipping": (ORDER,),
    "unbilled": (ORDER, INVOICE, DELIVERY), "delivered_unbilled": (DELIVERY, INVOICE, ORDER),
    "dated_billing": (ORDER, INVOICE, DELIVERY, "Sales Analytics Billing"), "unscheduled_billing": (ORDER, INVOICE, DELIVERY),
    "reconciliation": (INVOICE, LEDGER),
}
GROUPS = {"customer", "item_code", "item_group"}
MAX_EXPORT_ROWS = 50000


def request_access():
    if frappe.session.user == "Guest":
        raise frappe.PermissionError(_("You must sign in to Sales Analytics."))
    if not cint(frappe.conf.get("sales_analytics_enabled", 1)):
        raise frappe.PermissionError(_("Sales Analytics is disabled for this site."))
    return Access()


def service(values):
    access = request_access()
    try:
        filters = Filters(frappe.parse_json(values) if values else {}, nowdate())
    except (ValueError, TypeError, AttributeError) as exc:
        frappe.throw(_(str(exc)))
    return SalesAnalytics(Sources(access, filters), filters)


def fetch_records(analytics, metric, period, group, value, sort, direction):
    if metric not in DETAILS:
        frappe.throw(_("Unknown sales metric."))
    if group and (group not in GROUPS or not isinstance(value, str) or len(value) > 140):
        frappe.throw(_("Invalid sales breakdown."))
    if period and (not isinstance(period, str) or len(period) > 32):
        frappe.throw(_("Invalid sales period."))
    columns = detail_columns(metric)
    allowed = {column["key"] for column in columns}
    if sort and sort not in allowed:
        frappe.throw(_("Invalid sales sort field."))
    if direction not in ("asc", "desc"):
        frappe.throw(_("Invalid sales sort direction."))
    rows = analytics.records(metric, period, group, value)
    if rows is None:
        raise frappe.PermissionError(_("This metric is unavailable in the selected scope."))
    sort = sort or next((key for key in ("date", "billing_date", "shipping_month", "document") if key in allowed), "source")
    ordered = sorted(rows, key=lambda row: (str(row.get("document") or ""), str(row.get("line") or "")))
    populated = [row for row in ordered if row.get(sort) is not None]
    populated.sort(key=lambda row: row[sort], reverse=direction == "desc")
    return columns, populated + [row for row in ordered if row.get(sort) is None]


@frappe.whitelist(methods=["POST"])
def get_dashboard(filters=None):
    analytics = service(filters)
    result = analytics.summary()
    result.update(company=COMPANY, refreshed_at=now_datetime())
    return result


@frappe.whitelist(methods=["POST"])
def get_details(metric, filters=None, period=None, group=None, value=None, sort=None, direction="desc", start=0, limit=25):
    analytics = service(filters)
    columns, rows = fetch_records(analytics, metric, period, group, value, sort, direction)
    offset = max(0, cint(start))
    size = min(100, max(1, cint(limit)))
    return {
        "columns": columns, "rows": [public_row(row, columns) for row in rows[offset:offset + size]],
        "total": len(rows), "start": offset, "limit": size, "refreshed_at": now_datetime(),
    }


@frappe.whitelist(methods=["POST"])
def search_items(text, limit=15):
    access = request_access()
    if not isinstance(text, str):
        return []
    text = text.strip()
    if not 2 <= len(text) <= 140:
        return []
    return access.search_items(text, max(1, min(30, cint(limit))))


def export_cell(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
        return "'" + value
    return value


@frappe.whitelist(methods=["POST"])
def export_details(metric, file_format, filters=None, period=None, group=None, value=None, sort=None, direction="desc"):
    analytics = service(filters)
    if file_format not in ("xlsx", "csv"):
        frappe.throw(_("Choose Excel or CSV."))
    columns, rows = fetch_records(analytics, metric, period, group, value, sort, direction)
    required = set(EXPORT_SOURCES.get(metric, ()))
    required.update(row["source"] for row in rows if row.get("source") in (ORDER, INVOICE, DELIVERY, LEDGER))
    for doctype in required:
        if doctype != "Sales Analytics Billing" or rows:
            can_export(doctype, raise_exception=True)
    if len(rows) > MAX_EXPORT_ROWS:
        frappe.throw(_("Narrow the reporting range before exporting."))
    values = [[_(column["label"]) for column in columns]]
    for row in rows:
        cleaned = public_row(row, columns, rounded=False)
        values.append([export_cell(cleaned[column["key"]]) for column in columns])
    if file_format == "xlsx":
        data = make_xlsx(values, _("Sales Analytics")).getvalue()
    else:
        body = io.StringIO(newline="")
        csv.writer(body).writerows(values)
        data = body.getvalue().encode("utf-8-sig")
    frappe.response.update({
        "filename": "sales-{}.{}".format(metric.replace("_", "-"), file_format),
        "filecontent": data, "type": "binary",
    })
