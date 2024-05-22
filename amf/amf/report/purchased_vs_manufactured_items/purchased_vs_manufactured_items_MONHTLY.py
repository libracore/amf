# Copyright (c) 2013, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.utils import getdate

def execute(filters=None):
    columns, data = get_columns(), get_data(filters)
    return columns, data

def get_columns():
    return [
        {"fieldname": "item_group", "label": "Item Group", "fieldtype": "Data", "width": 150},
        {"fieldname": "month", "label": "Month", "fieldtype": "Data", "width": 100},
        {"fieldname": "purchased_qty", "label": "Purchased Quantity", "fieldtype": "Float", "width": 150},
        {"fieldname": "manufactured_qty", "label": "Manufactured Quantity", "fieldtype": "Float", "width": 180},
        {"fieldname": "percentage_manufactured", "label": "Percentage Manufactured Internally", "fieldtype": "Percent", "width": 200},
    ]

def get_data(filters):
    data = []
    purchased_data = get_purchased_data(filters)
    manufactured_data = get_manufactured_data(filters)
    # Combine by month
    months = sorted(set([d['month'] for d in purchased_data + manufactured_data]))
    for month in months:
        for item_group in set([d['item_group'] for d in purchased_data + manufactured_data]):
            purchased_qty = sum(d['delivered_qty'] for d in purchased_data if d['item_group'] == item_group and d['month'] == month)
            manufactured_qty = sum(d['total_manufactured_qty'] for d in manufactured_data if d['item_group'] == item_group and d['month'] == month)
            total_qty = purchased_qty + manufactured_qty
            percentage_manufactured = (manufactured_qty / total_qty * 100) if total_qty else 0
            data.append({
                "item_group": item_group,
                "month": month,
                "purchased_qty": purchased_qty,
                "manufactured_qty": manufactured_qty,
                "percentage_manufactured": percentage_manufactured,
            })
    return data

def get_purchased_data(filters):
    return _get_item_data(filters, "Purchase Receipt Item", "qty", "delivered_qty")

def get_manufactured_data(filters):
    item_groups = filters.get("item_groups", [])
    item_group_condition = "AND it.item_group IN ({})".format(", ".join(f"'{item}'" for item in item_groups)) if item_groups else ""
    
    # Adjust the following query according to your database schema
    # Ensure that 'operation' is a valid column in the `tabJob Card` or adjust accordingly
    query = f"""
        SELECT 
            it.item_group,
            CONCAT(LPAD(MONTH(jc.posting_date), 2, '0'), '-', YEAR(jc.posting_date)) as month,
            SUM(jc.total_completed_qty) AS total_manufactured_qty
        FROM 
            `tabJob Card` jc
        LEFT JOIN 
            `tabItem` it ON (jc.product_item = it.item_code OR jc.bom_no = it.default_bom)
        WHERE 
            jc.status = 'Completed'
            {item_group_condition}
            AND jc.operation = 'CNC Machining'  # Confirm this field exists or remove if not applicable
            AND jc.posting_date BETWEEN '{filters.get("start_date")}' AND '{filters.get("end_date")}'
            AND it.item_group IN ('Plug', 'Valve Seat')
        GROUP BY 
            it.item_group, MONTH(jc.posting_date), YEAR(jc.posting_date);
    """
    return frappe.db.sql(query, as_dict=1)

def _get_item_data(filters, table, field, alias, extra_conditions=""):
    item_groups = filters.get("item_groups", [])
    item_group_condition = "AND it.item_group IN ({})".format(", ".join(f"'{item}'" for item in item_groups)) if item_groups else ""
    query = f"""
        SELECT 
            it.item_group,
            CONCAT(LPAD(MONTH(pr.posting_date), 2, '0'), '-', YEAR(pr.posting_date)) as month,
            SUM(pr_item.{field}) AS {alias}
        FROM 
            `tab{table}` pr_item
        JOIN 
            `tabPurchase Receipt` pr ON pr.name = pr_item.parent
        JOIN 
            `tabItem` it ON pr_item.item_code = it.item_code
        WHERE 
            pr.posting_date BETWEEN '{filters.get("start_date")}' AND '{filters.get("end_date")}'
            {item_group_condition}
            AND pr.status != 'Cancelled'
            {extra_conditions}
            AND it.item_group IN ('Plug', 'Valve Seat')
        GROUP BY 
            it.item_group, MONTH(pr.posting_date), YEAR(pr.posting_date);
    """
    return frappe.db.sql(query, as_dict=1)
