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


DEFAULT_COMPANY = "Advanced Microfluidics SA"
DEFAULT_SEMESTER_COUNT = 8
CURRENCIES = ("USD", "EUR", "CHF")
CHART_COLORS = ["green", "blue", "red"]


@frappe.whitelist()
@cache_source
def get(chart_name=None, chart=None, no_cache=None):
    chart = _get_chart(chart_name, chart)
    filters = normalize_filters(frappe.parse_json(chart.filters_json or "{}"))
    rows = get_purchasing_amount_by_currency(filters)

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


def get_purchasing_amount_by_currency(filters=None):
    filters = normalize_filters(filters)
    buckets = get_empty_semester_buckets(filters.from_date, filters.to_date)

    for row in get_purchase_invoice_amount_rows(filters):
        label = get_semester_label_from_parts(row.year, row.semester)
        if label not in buckets or row.currency not in CURRENCIES:
            continue

        buckets[label]["amounts"][row.currency] += flt(row.amount)

    for bucket in buckets.values():
        for currency in CURRENCIES:
            bucket["amounts"][currency] = round(bucket["amounts"][currency], 2)

    return list(buckets.values())


def get_datasets(rows):
    return [
        {
            "name": currency,
            "values": [row["amounts"][currency] for row in rows],
        }
        for currency in CURRENCIES
    ]


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
            "amounts": get_empty_currency_amounts(),
        }
        year, semester = add_semesters(year, semester, 1)

    return buckets


def get_empty_currency_amounts():
    return {currency: 0.0 for currency in CURRENCIES}


def get_semester_index(year, semester):
    return (cint(year) * 2) + (cint(semester) - 1)


def get_purchase_invoice_amount_rows(filters):
    return frappe.db.sql(
        """
        SELECT
            YEAR(pi.posting_date) AS year,
            CASE WHEN MONTH(pi.posting_date) <= 6 THEN 1 ELSE 2 END AS semester,
            pi.currency,
            SUM(
                COALESCE(
                    NULLIF(pii.net_amount, 0),
                    NULLIF(pii.amount, 0),
                    0
                )
            ) AS amount
        FROM `tabPurchase Invoice Item` pii
        INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
        INNER JOIN `tabItem` item ON item.name = pii.item_code
        WHERE pi.docstatus = 1
            AND IFNULL(pi.is_return, 0) = 0
            AND pi.posting_date BETWEEN %(from_date)s AND %(to_date)s
            AND pi.company = %(company)s
            AND pi.currency IN %(currencies)s
            AND IFNULL(item.is_stock_item, 0) = 1
            AND IFNULL(pii.item_code, '') != ''
        GROUP BY year, semester, pi.currency
        """,
        {
            "from_date": filters.from_date,
            "to_date": filters.to_date,
            "company": filters.company,
            "currencies": CURRENCIES,
        },
        as_dict=True,
    )
