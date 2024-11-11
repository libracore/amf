# Copyright (c) 2013, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _

def execute(filters=None):
    columns, data = [], []
    columns = get_columns()
    data = get_data(filters, columns)
    return columns, data

def get_columns():
    return [
        {
            "label": _("Item Code"),
            "fieldname": "item_code",
            "fieldtype": "Link",
            "options": "Item",
            "width": 250
        },
        {
            "label": _("Item Name"),
            "fieldname": "item_name",
            "fieldtype": "Data",
            "width": 100
        },
        {
            "label": _("Item Group"),
            "fieldname": "item_group",
            "fieldtype": "Data",
            "width": 150
        },
        {
            "label": _("Warehouse"),
            "fieldname": "warehouse",
            "fieldtype": "Link",
            "options": "Warehouse",
            "width": 200
        },
        {
            "label": _("Stock Available"),
            "fieldname": "stock_available",
            "fieldtype": "Float",
            "width": 150
        },
        {
            "label": _("Reserved Qty"),
            "fieldname": "reserved_qty",
            "fieldtype": "Float",
            "width": 150
        },
        {
            "label": _("Projected Qty"),
            "fieldname": "projected_qty",
            "fieldtype": "Float",
            "width": 150
        },
        {
            "label": _("Selling Price"),
            "fieldname": "last_selling_price",
            "fieldtype": "Currency",
            "width": 150
        },
    ]

def get_data(filters, columns):
    item_price_qty_data = []
    item_price_qty_data = get_item_qty_data(filters)
    return item_price_qty_data

def get_item_qty_data(filters):
    conditions = ""
    if filters.get("item_code"):
        conditions += "WHERE i.item_code = %(item_code)s"
    if filters.get("item_name"):
        conditions += " AND i.item_name = %(item_name)s" if conditions else "WHERE i.item_name = %(item_name)s"

    # Exclusion conditions for specific warehouses
    if conditions:
        conditions += " AND b.warehouse NOT LIKE '%%OLD%%' AND b.warehouse != 'Demo Device - AMF21' AND b.warehouse != 'Scrap - AMF21' AND i.disabled = 0"
    else:
        conditions = "WHERE b.warehouse NOT LIKE '%%OLD%%' AND b.warehouse != 'Demo Device - AMF21' AND b.warehouse != 'Scrap - AMF21' AND i.disabled = 0"

    # Query modified to include reserved_qty and projected_qty
    item_results = frappe.db.sql("""
        SELECT 
            i.item_code, 
            i.item_name, 
            i.item_group,
            b.warehouse, 
            b.actual_qty as stock_available, 
            b.reserved_qty as reserved_qty,
            b.projected_qty as projected_qty,
            MAX(soi.rate) as last_selling_price
        FROM `tabItem` i
        LEFT JOIN `tabBin` b ON i.item_code = b.item_code
        LEFT JOIN `tabSales Order Item` soi ON i.item_code = soi.item_code
        LEFT JOIN `tabSales Order` so ON soi.parent = so.name
        {conditions}
        GROUP BY i.item_code, b.warehouse
        ORDER BY i.item_code ASC
    """.format(conditions=conditions), filters, as_dict=1)

    return item_results
