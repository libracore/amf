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


DEFAULT_SEMESTER_COUNT = 8
PROCESS_INVOLVED = "Packaging & Shipping"
ISSUE_STATUSES = ("Open", "Closed")
CHART_COLORS = ["red"]


@frappe.whitelist()
@cache_source
def get(chart_name=None, chart=None, no_cache=None):
    chart = _get_chart(chart_name, chart)
    filters = normalize_filters(frappe.parse_json(chart.filters_json or "{}"))
    rows = get_packaging_and_shipping_issues_by_semester(filters)

    return {
        "labels": [row["label"] for row in rows],
        "datasets": [
            {
                "name": _("Packaging and Shipping Issues"),
                "values": [row["issue_count"] for row in rows],
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


def get_packaging_and_shipping_issues_by_semester(filters=None):
    filters = normalize_filters(filters)
    buckets = get_empty_semester_buckets(filters.from_date, filters.to_date)

    for row in get_issue_rows(filters):
        label = get_semester_label_from_parts(row.year, row.semester)
        if label not in buckets:
            continue

        buckets[label]["issue_count"] += cint(row.issue_count)

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
            "issue_count": 0,
        }
        year, semester = add_semesters(year, semester, 1)

    return buckets


def get_semester_index(year, semester):
    return (cint(year) * 2) + (cint(semester) - 1)


def get_issue_rows(filters):
    return frappe.db.sql(
        """
        SELECT
            YEAR(COALESCE(issue.opening_date, DATE(issue.creation))) AS year,
            CASE
                WHEN MONTH(COALESCE(issue.opening_date, DATE(issue.creation))) <= 6 THEN 1
                ELSE 2
            END AS semester,
            COUNT(issue.name) AS issue_count
        FROM `tabIssue` issue
        WHERE COALESCE(issue.opening_date, DATE(issue.creation)) BETWEEN %(from_date)s AND %(to_date)s
            AND issue.process_involved = %(process_involved)s
            AND issue.status IN %(issue_statuses)s
        GROUP BY year, semester
        """,
        {
            "from_date": filters.from_date,
            "to_date": filters.to_date,
            "process_involved": PROCESS_INVOLVED,
            "issue_statuses": ISSUE_STATUSES,
        },
        as_dict=True,
    )
