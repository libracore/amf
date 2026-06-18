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


AMOUNT_MODE = "amount"
QUANTITY_MODE = "quantity"
COMBINED_MODE = "combined"
DEFAULT_COMPANY = "Advanced Microfluidics SA"
DEFAULT_SEMESTER_COUNT = 8
STOCK_VALUE_COLOR = "green"
STOCK_QTY_COLOR = "blue"


@frappe.whitelist()
@cache_source
def get(chart_name=None, chart=None, no_cache=None):
    chart = _get_chart(chart_name, chart)
    filters = normalize_filters(frappe.parse_json(chart.filters_json or "{}"))
    rows = get_stock_balance_by_semester(filters)

    return {
        "labels": [row["label"] for row in rows],
        "datasets": get_datasets(rows, filters.mode),
        "colors": get_colors(filters.mode),
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
    filters.mode = filters.get("mode") or COMBINED_MODE
    if filters.mode not in (COMBINED_MODE, AMOUNT_MODE, QUANTITY_MODE):
        filters.mode = COMBINED_MODE

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


def get_datasets(rows, mode):
    datasets = []

    if mode in (COMBINED_MODE, AMOUNT_MODE):
        datasets.append({
            "name": _("Stock Balance Amount"),
            "values": [row["balance_value"] for row in rows],
        })

    if mode in (COMBINED_MODE, QUANTITY_MODE):
        datasets.append({
            "name": _("Stock Balance Qty"),
            "values": [row["balance_qty"] for row in rows],
        })

    return datasets


def get_colors(mode):
    if mode == AMOUNT_MODE:
        return [STOCK_VALUE_COLOR]
    if mode == QUANTITY_MODE:
        return [STOCK_QTY_COLOR]

    return [STOCK_VALUE_COLOR, STOCK_QTY_COLOR]


def get_stock_balance_by_semester(filters=None):
    filters = normalize_filters(filters)
    buckets = get_empty_semester_buckets(filters.from_date, filters.to_date)
    snapshots = list(buckets.values())
    balances = {}
    snapshot_index = 0

    for row in get_stock_ledger_entries(filters):
        posting_date = getdate(row.posting_date)
        while snapshot_index < len(snapshots) and posting_date > snapshots[snapshot_index]["snapshot_date"]:
            update_snapshot(snapshots[snapshot_index], balances)
            snapshot_index += 1

        apply_stock_ledger_entry(balances, row)

    while snapshot_index < len(snapshots):
        update_snapshot(snapshots[snapshot_index], balances)
        snapshot_index += 1

    return snapshots


def get_empty_semester_buckets(from_date, to_date):
    buckets = OrderedDict()
    year, semester = get_semester(from_date)
    end_year, end_semester = get_semester(to_date)
    end_index = get_semester_index(end_year, end_semester)

    while get_semester_index(year, semester) <= end_index:
        label = get_semester_label_from_parts(year, semester)
        semester_end = get_semester_end(year, semester)
        buckets[label] = {
            "label": label,
            "year": year,
            "semester": semester,
            "from_date": get_semester_start(year, semester),
            "to_date": semester_end,
            "snapshot_date": min(semester_end, to_date),
            "balance_qty": 0.0,
            "balance_value": 0.0,
        }
        year, semester = add_semesters(year, semester, 1)

    return buckets


def get_semester_index(year, semester):
    return (cint(year) * 2) + (cint(semester) - 1)


def get_stock_ledger_entries(filters):
    conditions = [
        "sle.docstatus < 2",
        "sle.posting_date <= %(to_date)s",
        "sle.company = %(company)s",
    ]
    values = {
        "to_date": filters.to_date,
        "company": filters.company,
    }

    if filters.get("warehouse"):
        warehouse_details = frappe.db.get_value(
            "Warehouse",
            filters.warehouse,
            ["lft", "rgt"],
            as_dict=True,
        )
        if warehouse_details:
            conditions.append(
                """
                EXISTS (
                    SELECT wh.name
                    FROM `tabWarehouse` wh
                    WHERE wh.lft >= %(warehouse_lft)s
                        AND wh.rgt <= %(warehouse_rgt)s
                        AND sle.warehouse = wh.name
                )
                """
            )
            values["warehouse_lft"] = warehouse_details.lft
            values["warehouse_rgt"] = warehouse_details.rgt
        else:
            conditions.append("sle.warehouse = %(warehouse)s")
            values["warehouse"] = filters.warehouse

    return frappe.db.sql(
        """
        SELECT
            sle.item_code,
            sle.warehouse,
            sle.posting_date,
            sle.posting_time,
            sle.creation,
            sle.actual_qty,
            sle.qty_after_transaction,
            sle.stock_value_difference,
            sle.voucher_type
        FROM `tabStock Ledger Entry` sle FORCE INDEX (posting_sort_index)
        WHERE {conditions}
        ORDER BY
            sle.posting_date,
            sle.posting_time,
            sle.creation,
            sle.actual_qty
        """.format(conditions=" AND ".join(conditions)),
        values,
        as_dict=True,
    )


def apply_stock_ledger_entry(balances, row):
    key = (row.item_code, row.warehouse)
    if key not in balances:
        balances[key] = {"qty": 0.0, "value": 0.0}

    if row.voucher_type == "Stock Reconciliation":
        qty_diff = flt(row.qty_after_transaction) - balances[key]["qty"]
    else:
        qty_diff = flt(row.actual_qty)

    balances[key]["qty"] += qty_diff
    balances[key]["value"] += flt(row.stock_value_difference)


def update_snapshot(bucket, balances):
    bucket["balance_qty"] = round(sum(balance["qty"] for balance in balances.values()), 3)
    bucket["balance_value"] = round(sum(balance["value"] for balance in balances.values()), 2)
