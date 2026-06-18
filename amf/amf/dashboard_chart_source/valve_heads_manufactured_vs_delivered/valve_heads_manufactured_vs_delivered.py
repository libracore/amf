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


DEFAULT_SEMESTER_COUNT = 8
MANUFACTURED_ITEM_PATTERN = r"^30[0-9]{4}$"
DELIVERED_ITEM_PATTERN = r"^(30[0-9]{4}|4[0-9]{5})$"
DELIVERY_NOTE_STATUSES = ("Completed", "Closed", "Validated")
CHART_COLORS = ["blue", "green"]


@frappe.whitelist()
@cache_source
def get(chart_name=None, chart=None, no_cache=None):
    chart = _get_chart(chart_name, chart)
    filters = normalize_filters(frappe.parse_json(chart.filters_json or "{}"))
    rows = get_valve_heads_by_semester(filters)

    return {
        "labels": [row["label"] for row in rows],
        "datasets": [
            {
                "name": _("Manufactured Valve Heads"),
                "values": [row["manufactured_qty"] for row in rows],
            },
            {
                "name": _("Delivered Valve Heads"),
                "values": [row["delivered_qty"] for row in rows],
            },
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


def get_valve_heads_by_semester(filters=None):
    filters = normalize_filters(filters)
    buckets = get_empty_semester_buckets(filters.from_date, filters.to_date)

    add_quantities(buckets, get_manufactured_valve_head_rows(filters), "manufactured_qty")
    add_quantities(buckets, get_delivered_valve_head_rows(filters), "delivered_qty")

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
            "manufactured_qty": 0.0,
            "delivered_qty": 0.0,
        }
        year, semester = add_semesters(year, semester, 1)

    return buckets


def get_semester_index(year, semester):
    return (cint(year) * 2) + (cint(semester) - 1)


def get_manufactured_valve_head_rows(filters):
    return frappe.db.sql(
        """
        SELECT
            YEAR(se.posting_date) AS year,
            CASE WHEN MONTH(se.posting_date) <= 6 THEN 1 ELSE 2 END AS semester,
            SUM(COALESCE(NULLIF(sed.transfer_qty, 0), sed.qty, 0)) AS qty
        FROM `tabStock Entry` se
        INNER JOIN (
            SELECT parent, MAX(idx) AS max_idx
            FROM `tabStock Entry Detail`
            GROUP BY parent
        ) last_sed ON last_sed.parent = se.name
        INNER JOIN `tabStock Entry Detail` sed
            ON sed.parent = se.name
            AND sed.idx = last_sed.max_idx
        WHERE se.docstatus = 1
            AND se.purpose = 'Manufacture'
            AND se.posting_date BETWEEN %(from_date)s AND %(to_date)s
            AND IFNULL(sed.t_warehouse, '') != ''
            AND sed.item_code REGEXP %(manufactured_item_pattern)s
            AND COALESCE(NULLIF(sed.transfer_qty, 0), sed.qty, 0) > 0
        GROUP BY year, semester
        """,
        {
            "from_date": filters.from_date,
            "to_date": filters.to_date,
            "manufactured_item_pattern": MANUFACTURED_ITEM_PATTERN,
        },
        as_dict=True,
    )


def get_delivered_valve_head_rows(filters):
    return frappe.db.sql(
        """
        SELECT
            YEAR(dn.posting_date) AS year,
            CASE WHEN MONTH(dn.posting_date) <= 6 THEN 1 ELSE 2 END AS semester,
            SUM(dni.qty) AS qty
        FROM `tabDelivery Note Item` dni
        INNER JOIN `tabDelivery Note` dn ON dn.name = dni.parent
        WHERE dn.docstatus = 1
            AND dn.status IN %(delivery_note_statuses)s
            AND IFNULL(dn.is_return, 0) = 0
            AND dn.posting_date BETWEEN %(from_date)s AND %(to_date)s
            AND dni.item_code REGEXP %(delivered_item_pattern)s
            AND IFNULL(dni.qty, 0) > 0
        GROUP BY year, semester
        """,
        {
            "from_date": filters.from_date,
            "to_date": filters.to_date,
            "delivered_item_pattern": DELIVERED_ITEM_PATTERN,
            "delivery_note_statuses": DELIVERY_NOTE_STATUSES,
        },
        as_dict=True,
    )


def add_quantities(buckets, rows, fieldname):
    for row in rows:
        label = get_semester_label_from_parts(row.year, row.semester)
        if label not in buckets:
            continue

        buckets[label][fieldname] += flt(row.qty)
