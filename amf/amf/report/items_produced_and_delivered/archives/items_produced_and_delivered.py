from __future__ import unicode_literals
import frappe
from frappe import _

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    return [
        _("Item Group") + ":Link/Item Group:200",
        _("Quarter") + ":Data:100",
        _("Items Produced") + ":Int:150",
        _("Items Delivered") + ":Int:150",
    ]

def get_data(filters):
    data = frappe.db.sql("""
        SELECT
            item.item_group,
            CONCAT(YEAR(dn.posting_date), '-Q', QUARTER(dn.posting_date)) as quarter,
            SUM(prd.fg_completed_qty) as items_produced,
            SUM(dni.qty) as items_delivered
        FROM `tabDelivery Note Item` dni
        JOIN `tabDelivery Note` dn ON dni.parent = dn.name
        JOIN `tabItem` item ON dni.item_code = item.item_code
        JOIN `tabWork Order` pro ON item.item_code = pro.production_item
        JOIN `tabStock Entry` prd ON pro.name = prd.work_order
        WHERE dn.docstatus = 1
        AND (dn.posting_date BETWEEN %s AND %s)
        GROUP BY item.item_group, quarter
        ORDER BY item.item_group, quarter
    """, (filters.get("from_date"), filters.get("to_date")), as_dict=1)

    return data
