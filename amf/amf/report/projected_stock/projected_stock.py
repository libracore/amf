# Copyright (c) 2013-2022, bnovate, libracore and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
import textwrap
import itertools
from frappe import _

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    chart = get_chart(data)
    
    return columns, data, None, chart
    
def get_columns():
    return [
        {'fieldname': 'date', 'fieldtype': 'Date', 'label': _('Date'), 'width': 80},
        {'fieldname': 'doctype', 'fieldtype': 'Data', 'label': _('Doctype'), 'width': 100},
        {'fieldname': 'docname', 'fieldtype': 'Data', 'label': _('Docname'), 'width': 100},
        {'fieldname': 'item_code', 'fieldtype': 'Link', 'label': _('Item code'), 'options': 'Item', 'width': 300},
        {'fieldname': 'warehouse', 'fieldtype': 'Link', 'label': _('Warehouse'), 'options': 'Warehouse', 'width': 300},
        {'fieldname': 'qty', 'fieldtype': 'Number', 'label': _('Qty'), 'width': 100}, 
        {'fieldname': 'balance', 'fieldtype': 'Number', 'label': _('Stock balance'), 'width': 100}, 
    ]
    
def get_data(filters):
    
    if not filters.item_code or not filters.warehouse:
        return None
        
    sql_query = """
SELECT 
    e.date,
    e.doctype,
    e.docname,
    e.item_code,
    i.item_name,
    e.warehouse,
    e.qty,
    ROUND(@running_total := @running_total + qty, 3) AS balance
FROM (
  (SELECT
    0 as order_prio, -- to keep stock balance as first item in list
    CURDATE() as date,
    'Stock Balance' as `doctype`,
    null as `docname`,
    b.item_code,
    b.warehouse,
    b.actual_qty as qty
  FROM `tabBin` as b
) UNION ALL (
-- Sales Order: items to sell
  SELECT
    1 as order_prio,
    soi.delivery_date as `date`,
    'Sales Order' as `doctype`,
    soi.parent as `docname`,
    soi.item_code,
    soi.warehouse,
    -(soi.qty - soi.delivered_qty) * soi.conversion_factor as qty
  FROM `tabSales Order Item` as soi
  JOIN `tabSales Order` as so ON so.name = soi.parent
  WHERE soi.delivered_qty < soi.qty
    AND soi.docstatus = 1
    AND so.status != 'Closed'
) UNION ALL (
-- Packed items: items to sell inside bundles
  SELECT
    1 as order_prio,
    soi.delivery_date as `date`,
    'Sales Order' as `doctype`,
    soi.parent as `docname`,
    pi.item_code,
    pi.warehouse,
  	ROUND(-(soi.qty - soi.delivered_qty) / soi.qty * pi.qty, 3) as qty -- soi conversion factor already calculated in packed item qty!
  FROM `tabPacked Item` as pi
  JOIN `tabSales Order` as so ON so.name = pi.parent
  JOIN `tabSales Order Item` as soi on soi.name = pi.parent_detail_docname
  WHERE soi.delivered_qty < soi.qty
    AND soi.docstatus = 1
    AND so.status != 'Closed'
) UNION ALL (
-- Purchase Order: items to receive
  SELECT    
    1 as order_prio,
    IFNULL(poi.expected_delivery_date, poi.schedule_date) as `date`,
    'Purchase Order' as `doctype`,
    poi.parent as `docname`,
    poi.item_code,
    poi.warehouse,
    (poi.qty - poi.received_qty) * poi.conversion_factor as qty
  FROM `tabPurchase Order Item` as poi
  JOIN `tabPurchase Order` as po ON po.name = poi.parent
  WHERE poi.received_qty < poi.qty
    AND poi.docstatus = 1
    AND po.status != 'Closed'
) UNION ALL (
-- Work Orders: produced items
SELECT
    1 as order_prio,
    IFNULL(wo.expected_delivery_date, CAST(wo.planned_start_date AS date)) as `date`,
    "Work Order" as `doctype`,
    wo.name as `docname`,
    wo.production_item as `item_code`,
    wo.fg_warehouse,
    wo.qty - wo.produced_qty as `qty`
FROM `tabWork Order` as wo
WHERE wo.docstatus = 1
    AND wo.qty > wo.produced_qty
    AND wo.status != 'Stopped'
) UNION ALL (
-- Work Order Items: consumed items
SELECT
    1 as order_prio,
    CAST(wo.planned_start_date AS date) as `date`,
    "Work Order" as `doctype`,
    wo.name as `docname`,
    woi.item_code as `item_code`,
    woi.source_warehouse as `warehouse`,
    -(woi.required_qty - woi.consumed_qty) as `qty`
FROM `tabWork Order Item` as woi
JOIN `tabWork Order` as wo ON woi.parent = wo.name
WHERE wo.docstatus = 1
    AND wo.qty > wo.produced_qty
    AND wo.status != 'Stopped'
)) as e -- "entries"
JOIN (SELECT @running_total := 0) r
JOIN `tabItem` as i on e.item_code = i.name
WHERE e.item_code = '{item_code}' AND e.warehouse = '{warehouse}'
ORDER BY order_prio, date ASC

    """.format(item_code=filters.item_code, warehouse=filters.warehouse)
    
    data = frappe.db.sql(sql_query, as_dict=True)
    
    for row in data:
        if row['doctype'] in ('Purchase Order', 'Sales Order', 'Work Order'):
            row['docname'] = """<a href="/desk#Form/{doctype}/{docname}">{docname}</a>""".format(doctype=row['doctype'], docname=row['docname'])

    return data


def get_chart(data):
    
    if data is None:
        return None
    
    dates = [it['date'] for it in data]
    balance = [it['balance'] for it in data]
    
    initial_stock = [ it['qty'] if it['doctype'] == 'Stock Balance' else 0 for it in data ]
    purchases = [ it['qty'] if it['doctype'] == 'Purchase Order' else 0 for it in data ]
    sales = [ it['qty'] if it['doctype'] == 'Sales Order' else 0 for it in data ]
    produced = [ it['qty'] if it['doctype'] == 'Work Order' else 0 for it in data ]
    
    chart = {
        "data": {
            "labels": dates,
            "datasets": [{
                "name": "Initial Stock",
                "values": initial_stock,
                "chartType": "bar",
            }, {
                "name": "Purchases",
                "values": purchases,
                "chartType": "bar",
            }, {
                "name": "Sales",
                "values": sales,
                "chartType": "bar",
            }, {
                "name": "Production",
                "values": produced,
                "chartType": "bar",
            }, {
                "name": "Balance",
                "values": balance,
                "chartType": "line",
            }],
            "yMarkers": [{
                "label": "Stockout",
                "value": 0,
                "options": { "labelPos": 'left' }
            }],
        },
        "type": 'axis-mixed',
        "barOptions": {
            "stacked": True,
            "spaceRatio": 0.1,
        },

        "title": "Projected stock balance",
    }
    return chart
            
    
        
    
