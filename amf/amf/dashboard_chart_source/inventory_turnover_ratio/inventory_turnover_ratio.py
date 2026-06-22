from __future__ import unicode_literals

from collections import OrderedDict

import frappe
from frappe import _
from frappe.core.page.dashboard.dashboard import cache_source
from frappe.utils import add_days, cint, cstr, flt, getdate, today

from amf.amf.dashboard_chart_source.otif_by_semester.otif_by_semester import (
    add_semesters,
    get_semester,
    get_semester_end,
    get_semester_label_from_parts,
    get_semester_start,
)


DEFAULT_COMPANY = "Advanced Microfluidics SA"
DEFAULT_SEMESTER_COUNT = 8

PRODUCT_RANGES = OrderedDict([
    ("RVM", {"account_number": "4003", "color": "red"}),
    ("Valve Head", {"account_number": "4009", "color": "yellow"}),
    ("SPM", {"account_number": "4002", "color": "blue"}),
    ("LSP", {"account_number": "4001", "color": "orange"}),
    ("UFM", {"account_number": "4000", "color": "green"}),
])
RANGE_BY_ACCOUNT_NUMBER = {
    values["account_number"]: product_range
    for product_range, values in PRODUCT_RANGES.items()
}


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
                "name": product_range,
                "values": [row["ranges"][product_range]["turnover"] for row in rows],
            }
            for product_range in PRODUCT_RANGES
        ],
        "colors": [values["color"] for values in PRODUCT_RANGES.values()],
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
    snapshots = get_inventory_snapshots(filters, buckets)

    for bucket in buckets.values():
        period_from_date = max(bucket["from_date"], filters.from_date)
        period_to_date = min(bucket["to_date"], filters.to_date)
        opening_date = getdate(add_days(period_from_date, -1))

        for product_range in PRODUCT_RANGES:
            bucket["ranges"][product_range]["opening_inventory"] = snapshots[opening_date][product_range]
            bucket["ranges"][product_range]["closing_inventory"] = snapshots[period_to_date][product_range]

    for row in get_cogs_rows(filters):
        label = get_semester_label_from_parts(row.year, row.semester)
        product_range = RANGE_BY_ACCOUNT_NUMBER.get(cstr(row.account_number))
        if label in buckets and product_range:
            buckets[label]["ranges"][product_range]["cogs"] += flt(row.cogs)

    for bucket in buckets.values():
        calculate_turnover(bucket)

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
            "ranges": get_empty_range_data(),
        }
        year, semester = add_semesters(year, semester, 1)

    return buckets


def get_empty_range_data():
    return {
        product_range: {
            "cogs": 0.0,
            "opening_inventory": 0.0,
            "closing_inventory": 0.0,
            "average_inventory": 0.0,
            "turnover": 0.0,
        }
        for product_range in PRODUCT_RANGES
    }


def get_semester_index(year, semester):
    return (cint(year) * 2) + (cint(semester) - 1)


def get_cogs_rows(filters):
    return frappe.db.sql(
        """
        SELECT
            account.account_number,
            YEAR(gl.posting_date) AS year,
            CASE WHEN MONTH(gl.posting_date) <= 6 THEN 1 ELSE 2 END AS semester,
            SUM(IFNULL(gl.debit, 0) - IFNULL(gl.credit, 0)) AS cogs
        FROM `tabGL Entry` gl
        INNER JOIN `tabAccount` account ON account.name = gl.account
        WHERE gl.company = %(company)s
            AND account.company = %(company)s
            AND gl.posting_date BETWEEN %(from_date)s AND %(to_date)s
            AND account.account_number IN %(account_numbers)s
        GROUP BY account.account_number, year, semester
        """,
        {
            "company": filters.company,
            "from_date": filters.from_date,
            "to_date": filters.to_date,
            "account_numbers": get_account_numbers(),
        },
        as_dict=True,
    )


def get_inventory_snapshots(filters, buckets):
    snapshot_dates = set()
    for bucket in buckets.values():
        period_from_date = max(bucket["from_date"], filters.from_date)
        period_to_date = min(bucket["to_date"], filters.to_date)
        snapshot_dates.add(getdate(add_days(period_from_date, -1)))
        snapshot_dates.add(period_to_date)

    daily_rows = get_inventory_movement_rows(filters)
    balances = {product_range: 0.0 for product_range in PRODUCT_RANGES}
    snapshots = {}
    row_index = 0

    for snapshot_date in sorted(snapshot_dates):
        while row_index < len(daily_rows) and getdate(daily_rows[row_index].posting_date) <= snapshot_date:
            row = daily_rows[row_index]
            product_range = RANGE_BY_ACCOUNT_NUMBER.get(cstr(row.account_number))
            if product_range:
                balances[product_range] += flt(row.stock_value_difference)
            row_index += 1

        snapshots[snapshot_date] = balances.copy()

    return snapshots


def get_inventory_movement_rows(filters):
    return frappe.db.sql(
        """
        SELECT
            sle.posting_date,
            account.account_number,
            SUM(IFNULL(sle.stock_value_difference, 0)) AS stock_value_difference
        FROM `tabStock Ledger Entry` sle
        INNER JOIN (
            SELECT
                parent AS item_code,
                MAX(expense_account) AS expense_account
            FROM `tabItem Default`
            WHERE parenttype = 'Item'
                AND company = %(company)s
            GROUP BY parent
        ) item_default ON item_default.item_code = sle.item_code
        INNER JOIN `tabAccount` account
            ON account.name = item_default.expense_account
            AND account.company = %(company)s
        WHERE sle.docstatus < 2
            AND sle.company = %(company)s
            AND sle.posting_date <= %(to_date)s
            AND account.account_number IN %(account_numbers)s
        GROUP BY sle.posting_date, account.account_number
        ORDER BY sle.posting_date, account.account_number
        """,
        {
            "company": filters.company,
            "to_date": filters.to_date,
            "account_numbers": get_account_numbers(),
        },
        as_dict=True,
    )


def get_account_numbers():
    return tuple(values["account_number"] for values in PRODUCT_RANGES.values())


def calculate_turnover(bucket):
    for product_range in PRODUCT_RANGES:
        data = bucket["ranges"][product_range]
        data["average_inventory"] = (
            data["opening_inventory"] + data["closing_inventory"]
        ) / 2.0
        data["turnover"] = round(
            data["cogs"] / data["average_inventory"],
            2,
        ) if data["average_inventory"] else 0.0
