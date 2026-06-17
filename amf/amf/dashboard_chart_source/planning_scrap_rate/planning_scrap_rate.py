from __future__ import unicode_literals

from collections import OrderedDict

import frappe
from frappe import _
from frappe.core.page.dashboard.dashboard import cache_source
from frappe.utils import cint, flt, getdate, today

from amf.amf.dashboard_chart_source.otif_by_semester.otif_by_semester import (
    add_semesters,
    get_semester,
    get_semester_end,
    get_semester_label_from_parts,
    get_semester_start,
)


DEFAULT_LIMIT = 10
DEFAULT_MODE = "semester"
DEFAULT_SEMESTER_COUNT = 8
REFERENCE_MODE = "references"
CHART_COLORS = ["red"]


@frappe.whitelist()
@cache_source
def get(chart_name=None, chart=None, no_cache=None):
    chart = _get_chart(chart_name, chart)
    filters = normalize_filters(frappe.parse_json(chart.filters_json or "{}"))

    if filters.mode == REFERENCE_MODE:
        rows = get_scrap_reference_rows(filters)
        labels = [row["label"] for row in rows]
    else:
        rows = get_scrap_rate_by_semester(filters)
        labels = [row["label"] for row in rows]

    return {
        "labels": labels,
        "datasets": [
            {
                "name": _("Scrap Rate %"),
                "values": [row["scrap_rate"] for row in rows],
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
    filters.mode = filters.get("mode") or DEFAULT_MODE
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


def get_scrap_reference_rows(filters=None):
    filters = normalize_filters(filters)
    rows = frappe.db.sql(
        """
        SELECT
            p.name,
            p.suivi_usinage,
            p.item_code,
            p.item_name,
            IFNULL(p.quantite_validee, 0) AS valid_qty,
            IFNULL(p.quantite_scrap, 0) AS scrap_qty,
            (
                IFNULL(p.quantite_scrap, 0)
                / NULLIF(IFNULL(p.quantite_validee, 0) + IFNULL(p.quantite_scrap, 0), 0)
                * 100
            ) AS scrap_rate
        FROM `tabPlanning` p
        WHERE p.docstatus = 1
            AND p.date_de_fin BETWEEN %(from_date)s AND %(to_date)s
            AND (IFNULL(p.quantite_validee, 0) + IFNULL(p.quantite_scrap, 0)) > 0
        ORDER BY scrap_rate DESC, scrap_qty DESC, valid_qty DESC
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
        row["valid_qty"] = flt(row.valid_qty)
        row["scrap_qty"] = flt(row.scrap_qty)
        row["scrap_rate"] = round(flt(row.scrap_rate), 1)
        row["label"] = get_reference_label(row)

    return rows


def get_scrap_rate_by_semester(filters=None):
    filters = normalize_filters(filters)
    buckets = get_empty_semester_buckets(filters.from_date, filters.to_date)

    for row in get_scrap_semester_rows(filters):
        label = get_semester_label_from_parts(row.year, row.semester)
        if label not in buckets:
            continue

        buckets[label]["valid_qty"] += flt(row.valid_qty)
        buckets[label]["scrap_qty"] += flt(row.scrap_qty)

    for bucket in buckets.values():
        total_qty = bucket["valid_qty"] + bucket["scrap_qty"]
        bucket["scrap_rate"] = round((bucket["scrap_qty"] / total_qty * 100), 1) if total_qty else 0.0

    return list(buckets.values())


def get_scrap_semester_rows(filters):
    return frappe.db.sql(
        """
        SELECT
            YEAR(p.date_de_fin) AS year,
            CASE WHEN MONTH(p.date_de_fin) <= 6 THEN 1 ELSE 2 END AS semester,
            SUM(IFNULL(p.quantite_validee, 0)) AS valid_qty,
            SUM(IFNULL(p.quantite_scrap, 0)) AS scrap_qty
        FROM `tabPlanning` p
        WHERE p.docstatus = 1
            AND p.date_de_fin BETWEEN %(from_date)s AND %(to_date)s
            AND (IFNULL(p.quantite_validee, 0) + IFNULL(p.quantite_scrap, 0)) > 0
        GROUP BY year, semester
        """,
        {
            "from_date": filters.from_date,
            "to_date": filters.to_date,
        },
        as_dict=True,
    )


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
            "valid_qty": 0.0,
            "scrap_qty": 0.0,
            "scrap_rate": 0.0,
        }
        year, semester = add_semesters(year, semester, 1)

    return buckets


def get_semester_index(year, semester):
    return (cint(year) * 2) + (cint(semester) - 1)


def get_reference_label(row):
    reference = row.suivi_usinage or row.name
    item_code = row.item_code or _("No Item")

    return "{0} - {1} ({2:g}/{3:g})".format(
        reference,
        item_code,
        flt(row.valid_qty),
        flt(row.scrap_qty),
    )[:80]
