from __future__ import unicode_literals

from collections import OrderedDict

import frappe
from frappe import _
from frappe.core.page.dashboard.dashboard import cache_source
from frappe.utils import cint, getdate, today

from amf.amf.report.on_time_delivery_kpis.on_time_delivery_kpis import get_data as get_otd_rows


DEFAULT_SEMESTER_COUNT = 8


@frappe.whitelist()
@cache_source
def get(chart_name=None, chart=None, no_cache=None):
    chart = _get_chart(chart_name, chart)
    filters = normalize_filters(frappe.parse_json(chart.filters_json or "{}"))
    rows = get_otif_by_semester(filters)

    return {
        "labels": [row["label"] for row in rows],
        "datasets": [
            {
                "name": _("OTIF %"),
                "values": [row["otif"] for row in rows],
            }
        ],
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

    filters.include_rd = cint(filters.get("include_rd"))
    return filters


def get_otif_by_semester(filters=None):
    filters = normalize_filters(filters)
    buckets = get_empty_semester_buckets(filters.from_date, filters.to_date)
    report_rows = get_otd_rows(frappe._dict({
        "from_date": filters.from_date,
        "to_date": filters.to_date,
        "item_group": filters.get("item_group"),
        "include_rd": filters.include_rd,
    }))

    for row in report_rows:
        planned_date = row.get("planned_date")
        if not planned_date:
            continue

        label = get_semester_label(planned_date)
        if label not in buckets:
            continue

        buckets[label]["total"] += 1
        buckets[label]["on_time"] += cint(row.get("0d"))

    for bucket in buckets.values():
        bucket["otif"] = round(bucket["on_time"] * 100.0 / bucket["total"], 1) if bucket["total"] else 0

    return list(buckets.values())


def get_empty_semester_buckets(from_date, to_date):
    buckets = OrderedDict()

    for year, semester in iter_semesters(from_date, to_date):
        label = get_semester_label_from_parts(year, semester)
        buckets[label] = {
            "label": label,
            "year": year,
            "semester": semester,
            "from_date": get_semester_start(year, semester),
            "to_date": get_semester_end(year, semester),
            "on_time": 0,
            "total": 0,
            "otif": 0,
        }

    return buckets


def iter_semesters(from_date, to_date):
    year, semester = get_semester(from_date)
    end_year, end_semester = get_semester(to_date)
    end_index = get_semester_index(end_year, end_semester)

    while get_semester_index(year, semester) <= end_index:
        yield year, semester
        year, semester = add_semesters(year, semester, 1)


def get_semester(date):
    date = getdate(date)
    return date.year, 1 if date.month <= 6 else 2


def add_semesters(year, semester, offset):
    index = get_semester_index(year, semester) + offset
    return index // 2, (index % 2) + 1


def get_semester_index(year, semester):
    return (cint(year) * 2) + (cint(semester) - 1)


def get_semester_start(year, semester):
    month = 1 if cint(semester) == 1 else 7
    return getdate("{0}-{1:02d}-01".format(cint(year), month))


def get_semester_end(year, semester):
    month_day = "06-30" if cint(semester) == 1 else "12-31"
    return getdate("{0}-{1}".format(cint(year), month_day))


def get_semester_label(date):
    return get_semester_label_from_parts(*get_semester(date))


def get_semester_label_from_parts(year, semester):
    return "{0} S{1}".format(cint(year), cint(semester))
