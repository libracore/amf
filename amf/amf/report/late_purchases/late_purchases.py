# Copyright (c) 2022, bNovate, libracore and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _


def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    
    return columns, data

def get_columns():
    return [
        {'fieldname': 'purchase_order', 'fieldtype': 'Link', 'label': _('PO'), 'options': 'Purchase Order', 'width': 80},
        {'fieldname': 'supplier', 'fieldtype': 'Link', 'label': _('Supplier'), 'options': 'Supplier', 'width': 80},
        {'fieldname': 'expected_delivery_date', 'fieldtype': 'Date', 'label': _('Expected date'), 'width': 80},
        {'fieldname': 'item_code', 'fieldtype': 'Link', 'label': _('Sold item'), 'options': 'Item', 'width': 200},
        {'fieldname': 'qty', 'fieldtype': 'Int', 'label': _('Qty total'), 'width': 100}, 
        {'fieldname': 'remaining_qty', 'fieldtype': 'Int', 'label': _('Qty to Receive'), 'width': 100},
        {'fieldname': 'owner', 'fieldtype': 'Data', 'label': _('Contact'), 'width': 200},
    ]
      
    
def get_data(filters):
    extra_filters = ""
    if filters.contact:
        extra_filters += "AND po.owner = '{}'\n".format(filters.contact)
    if filters.only_stock_items:
        extra_filters += "AND it.is_stock_item = {}\n".format(filters.only_stock_items)

    sql_query = """
SELECT 
    po.name as purchase_order,
    po.supplier,
    poi.item_code, 
    poi.item_name,
    poi.description,
    poi.qty, 
    (poi.qty - poi.received_qty) as remaining_qty,
    IFNULL(poi.expected_delivery_date, poi.schedule_date) as expected_delivery_date,
    po.owner
FROM `tabPurchase Order` as po
    JOIN `tabPurchase Order Item` as poi ON po.name = poi.parent
    JOIN `tabItem` as it ON poi.item_code = it.name
WHERE poi.received_qty < poi.qty
    AND IFNULL(poi.expected_delivery_date, poi.schedule_date) <= CURRENT_DATE()
    AND po.docstatus = 1
    AND po.status != 'Closed'
    {extra_filters}
ORDER BY IFNULL(poi.expected_delivery_date, poi.schedule_date) DESC
    ;
    """.format(extra_filters=extra_filters)

    data = frappe.db.sql(sql_query, as_dict=True)
    return data
