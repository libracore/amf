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
ITEM_CODE_PATTERN = r"^(10|20)[0-9]{4}$"

ITEM_FAMILIES = OrderedDict([
    ("plugs", {"prefix": "10", "label": _("Plugs")}),
    ("valve_seats", {"prefix": "20", "label": _("Valve Seats")}),
])

SOURCES = ("internal", "external")
CHART_COLORS = ["blue", "red", "yellow", "green"]


@frappe.whitelist()
@cache_source
def get(chart_name=None, chart=None, no_cache=None):
    chart = _get_chart(chart_name, chart)
    filters = normalize_filters(frappe.parse_json(chart.filters_json or "{}"))
    rows = get_external_vs_internal_by_semester(filters)

    return {
        "labels": [row["label"] for row in rows],
        "datasets": get_datasets(rows),
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


def get_external_vs_internal_by_semester(filters=None):
    filters = normalize_filters(filters)
    buckets = get_empty_semester_buckets(filters.from_date, filters.to_date)

    add_source_quantities(
        buckets,
        get_internal_machining_rows(filters),
        source="internal",
    )
    add_source_quantities(
        buckets,
        get_external_purchase_receipt_rows(filters),
        source="external",
    )
    add_ratios(buckets)

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
            "families": get_empty_family_data(),
        }
        year, semester = add_semesters(year, semester, 1)

    return buckets


def get_empty_family_data():
    return {
        family: {
            "internal": 0.0,
            "external": 0.0,
            "total": 0.0,
            "internal_ratio": 0.0,
            "external_ratio": 0.0,
        }
        for family in ITEM_FAMILIES
    }


def get_semester_index(year, semester):
    return (cint(year) * 2) + (cint(semester) - 1)


def get_internal_machining_rows(filters):
    return frappe.db.sql(
        """
        SELECT
            YEAR(p.date_de_fin) AS year,
            CASE WHEN MONTH(p.date_de_fin) <= 6 THEN 1 ELSE 2 END AS semester,
            CASE
                WHEN LEFT(p.item_code, 2) = '10' THEN 'plugs'
                ELSE 'valve_seats'
            END AS family,
            SUM(p.quantite_validee) AS qty
        FROM `tabPlanning` p
        WHERE p.docstatus = 1
            AND DATE(p.date_de_fin) BETWEEN %(from_date)s AND %(to_date)s
            AND p.item_code REGEXP %(item_code_pattern)s
            AND IFNULL(p.quantite_validee, 0) > 0
        GROUP BY year, semester, family
        """,
        {
            "from_date": filters.from_date,
            "to_date": filters.to_date,
            "item_code_pattern": ITEM_CODE_PATTERN,
        },
        as_dict=True,
    )


def get_external_purchase_receipt_rows(filters):
    return frappe.db.sql(
        """
        SELECT
            YEAR(pr.posting_date) AS year,
            CASE WHEN MONTH(pr.posting_date) <= 6 THEN 1 ELSE 2 END AS semester,
            CASE
                WHEN LEFT(pri.item_code, 2) = '10' THEN 'plugs'
                ELSE 'valve_seats'
            END AS family,
            SUM(pri.qty) AS qty
        FROM `tabPurchase Receipt Item` pri
        INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
        WHERE pr.docstatus = 1
            AND IFNULL(pr.is_return, 0) = 0
            AND pr.posting_date BETWEEN %(from_date)s AND %(to_date)s
            AND pri.item_code REGEXP %(item_code_pattern)s
            AND IFNULL(pri.qty, 0) > 0
        GROUP BY year, semester, family
        """,
        {
            "from_date": filters.from_date,
            "to_date": filters.to_date,
            "item_code_pattern": ITEM_CODE_PATTERN,
        },
        as_dict=True,
    )


def add_source_quantities(buckets, rows, source):
    for row in rows:
        label = get_semester_label_from_parts(row.year, row.semester)
        family = row.family
        if label not in buckets or family not in buckets[label]["families"]:
            continue

        buckets[label]["families"][family][source] += flt(row.qty)


def add_ratios(buckets):
    for bucket in buckets.values():
        for values in bucket["families"].values():
            values["total"] = values["internal"] + values["external"]
            if not values["total"]:
                continue

            values["internal_ratio"] = round(values["internal"] * 100.0 / values["total"], 1)
            values["external_ratio"] = round(values["external"] * 100.0 / values["total"], 1)


def get_datasets(rows):
    datasets = []
    source_labels = {
        "internal": _("Internal"),
        "external": _("External"),
    }

    for family, family_meta in ITEM_FAMILIES.items():
        for source in SOURCES:
            datasets.append({
                "name": _("{0} {1} %").format(family_meta["label"], source_labels[source]),
                "values": [
                    row["families"][family]["{0}_ratio".format(source)]
                    for row in rows
                ],
            })

    return datasets
