from __future__ import unicode_literals

from collections import OrderedDict

import frappe
from frappe import _
from frappe.core.page.dashboard.dashboard import cache_source
from frappe.utils import cint, getdate, today

from amf.amf.dashboard_chart_source.otif_by_semester.otif_by_semester import (
    add_semesters,
    get_semester,
    get_semester_end,
    get_semester_label_from_parts,
    get_semester_start,
)
from amf.amf.report.inventory_turnover.inventory_turnover import (
    calculate_inventory_turnover_ratio,
    extract_cogs,
    extract_inventory_data,
)


DEFAULT_COMPANY = "Advanced Microfluidics SA"
DEFAULT_SEMESTER_COUNT = 8
CHART_COLORS = ["green"]


@frappe.whitelist()
@cache_source
def get(chart_name=None, chart=None, no_cache=None):
    chart = _get_chart(chart_name, chart)
    filters = normalize_filters(frappe.parse_json(chart.filters_json or "{}"))
    rows = get_inventory_turnover_by_semester(filters)

    return {
        "labels": [row["label"] for row in rows],
        "datasets": [
            {
                "name": _("Inventory Turnover"),
                "values": [row["inventory_turnover_ratio"] for row in rows],
            }
        ],
        "colors": CHART_COLORS,
    }


def _get_chart(chart_name=None, chart=None):
    if chart_name:
        return frappe.get_doc("Dashboard Chart", chart_name)

    if hasattr(chart, "doctype"):
        return chart

    if isinstance(chart, dict):
        return frappe._dict(chart)

    return frappe._dict(frappe.parse_json(chart))


def normalize_filters(filters=None):
    filters = frappe._dict(filters or {})
    filters.semester_count = max(1, cint(filters.get("semester_count") or DEFAULT_SEMESTER_COUNT))
    filters.company = filters.get("company") or DEFAULT_COMPANY
    filters.to_date = getdate(filters.get("to_date") or today())

    if filters.get("from_date"):
        filters.from_date = getdate(filters.from_date)
    else:
        year, semester = get_semester(filters.to_date)
        start_year, start_semester = add_semesters(year, semester, -(filters.semester_count - 1))
        filters.from_date = get_semester_start(start_year, start_semester)

    if filters.from_date > filters.to_date:
        frappe.throw(_("From Date cannot be after To Date"))

    return filters


def get_inventory_turnover_by_semester(filters=None):
    filters = normalize_filters(filters)
    buckets = get_empty_semester_buckets(filters.from_date, filters.to_date)

    for bucket in buckets.values():
        period_from_date = max(bucket["from_date"], filters.from_date)
        period_to_date = min(bucket["to_date"], filters.to_date)
        cogs = extract_cogs(period_from_date, period_to_date, filters.company)
        opening_inventory, closing_inventory = extract_inventory_data(
            period_from_date,
            period_to_date,
            filters.company,
        )
        bucket["cogs"] = cogs
        bucket["opening_inventory"] = opening_inventory
        bucket["closing_inventory"] = closing_inventory
        bucket["inventory_turnover_ratio"] = round(
            calculate_inventory_turnover_ratio(cogs, opening_inventory, closing_inventory),
            2,
        )

    return list(buckets.values())


def get_empty_semester_buckets(from_date, to_date):
    buckets = OrderedDict()
    year, semester = get_semester(from_date)
    end_year, end_semester = get_semester(to_date)
    end_index = get_semester_index(end_year, end_semester)

    while get_semester_index(year, semester) <= end_index:
        label = get_semester_label_from_parts(year, semester)
        buckets[label] = {
            "label": label,
            "year": year,
            "semester": semester,
            "from_date": get_semester_start(year, semester),
            "to_date": get_semester_end(year, semester),
            "cogs": 0.0,
            "opening_inventory": 0.0,
            "closing_inventory": 0.0,
            "inventory_turnover_ratio": 0.0,
        }
        year, semester = add_semesters(year, semester, 1)

    return buckets


def get_semester_index(year, semester):
    return (cint(year) * 2) + (cint(semester) - 1)
