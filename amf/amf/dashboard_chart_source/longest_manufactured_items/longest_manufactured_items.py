from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.core.page.dashboard.dashboard import cache_source
from frappe.utils import cint, flt, getdate, today

from amf.amf.dashboard_chart_source.otif_by_semester.otif_by_semester import (
    add_semesters,
    get_semester,
    get_semester_start,
)


DEFAULT_LIMIT = 10
DEFAULT_SEMESTER_COUNT = 1
CHART_COLORS = ["orange"]


@frappe.whitelist()
@cache_source
def get(chart_name=None, chart=None, no_cache=None):
    chart = _get_chart(chart_name, chart)
    filters = normalize_filters(frappe.parse_json(chart.filters_json or "{}"))
    rows = get_longest_manufactured_items(filters)

    return {
        "labels": [row["label"] for row in rows],
        "datasets": [
            {
                "name": _("Minutes per Part"),
                "values": [row["minutes_per_part"] for row in rows],
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
    filters.limit = max(1, cint(filters.get("limit") or DEFAULT_LIMIT))
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


def get_longest_manufactured_items(filters=None):
    filters = normalize_filters(filters)
    rows = frappe.db.sql(
        """
        SELECT
            timer.item_code,
            timer.item_name,
            SUM(timer.total_duration) AS total_duration,
            SUM(timer.quantity) AS quantity,
            COUNT(timer.name) AS timer_count,
            (SUM(timer.total_duration) / SUM(timer.quantity) / 60) AS minutes_per_part
        FROM (
            SELECT
                tp.name,
                COALESCE(NULLIF(tp.item_code, ''), wo.production_item) AS item_code,
                item.item_name,
                tp.total_duration,
                COALESCE(
                    NULLIF(CAST(tp.quantity AS DECIMAL(18, 6)), 0),
                    NULLIF(wo.produced_qty, 0),
                    NULLIF(wo.qty, 0),
                    0
                ) AS quantity,
                COALESCE(MAX(timer_row.stop_time), tp.modified) AS completion_datetime
            FROM `tabTimer Production` tp
            LEFT JOIN `tabWork Order` wo ON wo.name = tp.work_order
            LEFT JOIN `tabItem` item
                ON item.name = COALESCE(NULLIF(tp.item_code, ''), wo.production_item)
            LEFT JOIN `tabWork Order Timer Table` timer_row
                ON timer_row.parent = tp.name
                AND timer_row.parenttype = 'Timer Production'
                AND timer_row.parentfield = 'sessions_list'
            WHERE tp.status = 'FINISHED'
                AND IFNULL(tp.total_duration, 0) > 0
            GROUP BY tp.name
        ) timer
        WHERE DATE(timer.completion_datetime) BETWEEN %(from_date)s AND %(to_date)s
            AND IFNULL(timer.item_code, '') != ''
            AND timer.quantity > 0
        GROUP BY timer.item_code, timer.item_name
        HAVING SUM(timer.quantity) > 0
        ORDER BY minutes_per_part DESC
        LIMIT %(limit)s
        """,
        {
            "from_date": filters.from_date,
            "to_date": filters.to_date,
            "limit": filters.limit,
        },
        as_dict=True,
    )

    for row in rows:
        row["minutes_per_part"] = round(flt(row.minutes_per_part), 1)
        row["label"] = get_item_label(row)

    return rows


def get_item_label(row):
    label = row.item_code or _("Unknown Item")
    if row.item_name and row.item_name != row.item_code:
        label = "{0} - {1}".format(label, row.item_name)

    return label[:80]
