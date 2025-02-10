# Copyright (c) 2013, libracore AG and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from datetime import datetime

def execute(filters=None):
    """
    Main entry point for the report. Returns columns and data based on user filters.
    """
    if not filters:
        filters = {}

    columns = get_columns()
    data = get_data(filters)

    return columns, data

def get_columns():
    """
    Define the columns displayed in the report.
    """
    return [
        {
            "label": _("Item Group"),
            "fieldname": "item_group",
            "fieldtype": "Data",
            "width": 200
        },
        {
            "label": _("Manufactured Qty"),
            "fieldname": "manufactured_qty",
            "fieldtype": "Float",
            "precision": 2,
            "width": 140
        },
        {
            "label": _("Purchased Qty"),
            "fieldname": "purchased_qty",
            "fieldtype": "Float",
            "precision": 2,
            "width": 140
        },
        {
            "label": _("Ratio (%)"),
            "fieldname": "manufactured_vs_purchased_ratio",
            "fieldtype": "Percent",
            "precision": 0,
            "width": 140
        }
    ]

def get_data(filters):
    """
    Fetches and combines manufactured and purchased quantities
    for item groups 'Plug' and 'Valve Seat' within the user-provided date range.
    """

    from_date = filters.get("from_date")
    to_date = filters.get("to_date")

    # 1) Manufactured: using Stock Entry (purpose = 'Manufacture')
    #    Filter by se.posting_date between from_date and to_date
    manufacturing_data = frappe.db.sql("""
        SELECT
            SUM(sle.actual_qty) AS manufactured_qty,
            i.item_group
        FROM
            `tabStock Ledger Entry` sle
            JOIN `tabStock Entry` se ON sle.voucher_no = se.name
            JOIN `tabItem` i ON sle.item_code = i.name
        WHERE
            -- Date filter: Last semester
            sle.posting_date BETWEEN %(from_date)s AND %(to_date)s
            -- Must be from a Stock Entry
            AND sle.voucher_type = 'Stock Entry'
            -- Only for "Manufacture" Stock Entries
            AND se.purpose = 'Manufacture'
            -- Consider only positive (incoming) stock movements
            AND sle.actual_qty > 0
            -- Filter for specific item groups
            AND i.item_group IN ('Plug', 'Valve Seat')
            -- Only include submitted stock entries
            AND se.docstatus = 1
            -- Ensure this Stock Entry has at least one "Raw Material" item in Stock Entry Detail
            AND EXISTS (
                SELECT 1
                FROM `tabStock Entry Detail` ste
                JOIN `tabItem` i2 ON ste.item_code = i2.name
                WHERE
                    ste.parent = se.name
                    AND i2.item_group = 'Raw Material'
            )
        GROUP BY
            i.item_group;
    """, {
        "from_date": from_date,
        "to_date": to_date
    }, as_dict=True)

    # 2) Purchased: using Purchase Receipt
    #    Filter by pr.posting_date between from_date and to_date
    #    And exclude warehouse = 'Scrap - AMF21'
    purchase_data = frappe.db.sql("""
        SELECT
            SUM(pri.qty) AS purchased_qty,
            i.item_group
        FROM
            `tabPurchase Receipt Item` pri
            JOIN `tabPurchase Receipt` pr ON pri.parent = pr.name
            JOIN `tabItem` i ON pri.item_code = i.name
        WHERE
            pr.docstatus = 1
            AND i.item_group IN ('Plug', 'Valve Seat')
            AND pri.warehouse != 'Scrap - AMF21'
			AND pr.posting_date BETWEEN %(from_date)s AND %(to_date)s
		GROUP BY
            pri.item_group
    """, {
        "from_date": from_date,
        "to_date": to_date
    }, as_dict=True)

    # Convert query results to dictionaries for quick lookup
    manufactured_map = {d["item_group"]: d["manufactured_qty"] for d in manufacturing_data}
    purchased_map = {d["item_group"]: d["purchased_qty"] for d in purchase_data}

    # Merge all item groups into one set
    all_item_groups = set(manufactured_map.keys()) | set(purchased_map.keys())

    # Build the final data list
    data = []
    for item_group in all_item_groups:
        manufactured_qty = manufactured_map.get(item_group, 0.0)
        purchased_qty = purchased_map.get(item_group, 0.0)
        total_qty = manufactured_qty + purchased_qty

        # Calculate ratio efficiently
        manufactured_vs_purchased_ratio = (
            (manufactured_qty * 100 / total_qty) if total_qty > 0 else 0.0
        )
        
        data.append({
            "item_group": item_group,
            "manufactured_qty": manufactured_map.get(item_group, 0.0),
            "purchased_qty": purchased_map.get(item_group, 0.0),
            "manufactured_vs_purchased_ratio": manufactured_vs_purchased_ratio
        })

    return data
