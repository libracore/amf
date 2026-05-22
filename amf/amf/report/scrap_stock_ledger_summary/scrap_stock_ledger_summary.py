# Copyright (c) 2026, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.utils import cint, flt


DEFAULT_SCRAP_WAREHOUSE = "Scrap - AMF21"


def execute(filters=None):
    filters = frappe._dict(filters or {})
    set_default_filters(filters)
    validate_filters(filters)

    columns = get_columns()
    data = get_data(filters)

    return columns, data


def set_default_filters(filters):
    if not filters.get("warehouse"):
        filters.warehouse = DEFAULT_SCRAP_WAREHOUSE


def validate_filters(filters):
    if not filters.get("company"):
        frappe.throw(_("Company is required"))
    if not filters.get("to_date"):
        frappe.throw(_("As Of Date is required"))
    if filters.get("warehouse") and not frappe.db.exists("Warehouse", filters.warehouse):
        frappe.throw(_("Warehouse {0} does not exist").format(filters.warehouse))


def get_columns():
    return [
        {
            "label": _("Item"),
            "fieldname": "item_code",
            "fieldtype": "Link",
            "options": "Item",
            "width": 140,
        },
        {
            "label": _("Item Name"),
            "fieldname": "item_name",
            "fieldtype": "Data",
            "width": 220,
        },
        {
            "label": _("Warehouse"),
            "fieldname": "warehouse",
            "fieldtype": "Link",
            "options": "Warehouse",
            "width": 160,
        },
        {
            "label": _("Balance Qty"),
            "fieldname": "balance_qty",
            "fieldtype": "Float",
            "width": 120,
        },
        {
            "label": _("Valuation Rate"),
            "fieldname": "valuation_rate",
            "fieldtype": "Currency",
            "options": "Company:company:default_currency",
            "width": 130,
        },
        {
            "label": _("Balance Value"),
            "fieldname": "balance_value",
            "fieldtype": "Currency",
            "options": "Company:company:default_currency",
            "width": 130,
        },
    ]


def get_data(filters):
    entries = get_stock_ledger_entries(filters)
    latest_by_item_warehouse = {}

    for entry in entries:
        key = (entry.item_code, entry.warehouse)
        latest_by_item_warehouse[key] = entry

    data = []
    float_precision = cint(frappe.db.get_default("float_precision")) or 3

    for entry in sorted(
        latest_by_item_warehouse.values(),
        key=lambda row: (row.item_code, row.warehouse),
    ):
        balance_qty = flt(entry.qty_after_transaction, float_precision)
        balance_value = flt(entry.stock_value)

        if (
            cint(filters.get("hide_empty_balances", 1))
            and not balance_qty
            and not balance_value
        ):
            continue

        data.append(
            {
                "item_code": entry.item_code,
                "item_name": entry.item_name,
                "warehouse": entry.warehouse,
                "balance_qty": balance_qty,
                "valuation_rate": flt(entry.valuation_rate),
                "balance_value": balance_value,
                "company": entry.company,
            }
        )

    return data


def get_stock_ledger_entries(filters):
    conditions = [
        "sle.company = %(company)s",
        "sle.docstatus < 2",
        "IFNULL(sle.is_cancelled, 'No') = 'No'",
        "sle.posting_date <= %(to_date)s",
    ]

    if filters.get("warehouse"):
        warehouse_condition = get_warehouse_condition(filters.warehouse)
        if warehouse_condition:
            conditions.append(warehouse_condition)

    if filters.get("item_code"):
        conditions.append("sle.item_code = %(item_code)s")

    if filters.get("brand"):
        conditions.append("item.brand = %(brand)s")

    if filters.get("item_group"):
        item_group_condition = get_item_group_condition(filters.item_group)
        if item_group_condition:
            conditions.append(item_group_condition)

    return frappe.db.sql(
        """
        SELECT
            sle.item_code,
            item.item_name,
            sle.warehouse,
            sle.qty_after_transaction,
            sle.valuation_rate,
            sle.stock_value,
            sle.company
        FROM `tabStock Ledger Entry` sle
        INNER JOIN `tabItem` item
            ON item.name = sle.item_code
        WHERE {conditions}
        ORDER BY
            sle.item_code ASC,
            sle.warehouse ASC,
            sle.posting_date ASC,
            sle.posting_time ASC,
            sle.creation ASC,
            sle.actual_qty ASC
        """.format(
            conditions=" AND ".join(conditions)
        ),
        filters,
        as_dict=1,
    )


def get_warehouse_condition(warehouse):
    warehouse_details = frappe.db.get_value(
        "Warehouse", warehouse, ["lft", "rgt"], as_dict=1
    )

    if warehouse_details:
        return """EXISTS (
            SELECT wh.name
            FROM `tabWarehouse` wh
            WHERE wh.lft >= {0}
              AND wh.rgt <= {1}
              AND sle.warehouse = wh.name
        )""".format(
            frappe.db.escape(warehouse_details.lft),
            frappe.db.escape(warehouse_details.rgt),
        )

    return ""


def get_item_group_condition(item_group):
    item_group_details = frappe.db.get_value(
        "Item Group", item_group, ["lft", "rgt"], as_dict=1
    )

    if item_group_details:
        return """EXISTS (
            SELECT ig.name
            FROM `tabItem Group` ig
            WHERE ig.lft >= {0}
              AND ig.rgt <= {1}
              AND item.item_group = ig.name
        )""".format(
            frappe.db.escape(item_group_details.lft),
            frappe.db.escape(item_group_details.rgt),
        )

    return ""
