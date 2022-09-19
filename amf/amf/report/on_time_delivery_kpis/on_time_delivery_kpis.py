# Copyright (c) 2013, libracore and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _


def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    message = "No message"
    chart = get_chart(filters)
    
    return columns, data, message, chart

def get_columns():
    return [
        {'fieldname': 'DN', 'fieldtype': 'Link', 'label': _('DN'), 'options': 'Delivery Note', 'width': 100},
        {'fieldname': 'SO', 'fieldtype': 'Link', 'label': _('SO'), 'options': 'Sales Order', 'width': 100},
        {'fieldname': 'customer', 'fieldtype': 'Link', 'label': _('Customer'), 'options': 'Customer', 'width': 80},
        {'fieldname': 'customer_name', 'fieldtype': 'Data', 'label': _('Customer Name'), 'width': 150},
        {'fieldname': 'item_code', 'fieldtype': 'Link', 'label': _('Item code'), 'options': 'Item', 'width': 200},
        # {'fieldname': 'item_name', 'fieldtype': 'Data', 'label': _('Item name'), 'width': 200},
        {'fieldname': 'item_group', 'fieldtype': 'Data', 'label': _('Item group'), 'width': 200},
        {'fieldname': 'planned_date', 'fieldtype': 'Date', 'label': _('Planned date'), 'width': 100},
        {'fieldname': 'shipped_date', 'fieldtype': 'Date', 'label': _('Shipped date'), 'width': 100},
        {'fieldname': 'delay', 'fieldtype': 'Int', 'label': _('Delay'), 'width': 50},         
        {'fieldname': '0d', 'fieldtype': 'Int', 'label': _('On time'), 'width': 50},
        {'fieldname': '2d', 'fieldtype': 'Int', 'label': _('1-2d'), 'width': 50},
        {'fieldname': '1w', 'fieldtype': 'Int', 'label': _('3-7d'), 'width': 50},
        {'fieldname': '>1w', 'fieldtype': 'Int', 'label': _('>7d'), 'width': 50},
    ]
    
def get_data(filters):
    
    extra_filters = ""
    if filters.item_group:
        extra_filters = """ AND i.item_group = "{}" """.format(filters.item_group)
    sql_query = """
SELECT
	dn.name as "DN",
    dni.against_sales_order as "SO",
    dn.customer as "customer",
    dn.customer_name as "customer_name",
    dni.item_code as "item_code",
    i.item_name as "item_name",
    i.item_group as "item_group",
    soi.delivery_date as "planned_date",
    dn.posting_date as "shipped_date",
    DATEDIFF(dn.posting_date, soi.delivery_date) as "delay",
    DATEDIFF(dn.posting_date, soi.delivery_date) <= 0 as "0d",
    DATEDIFF(dn.posting_date, soi.delivery_date) > 0 AND DATEDIFF(dn.posting_date, soi.delivery_date) <= 2 as "2d",
    DATEDIFF(dn.posting_date, soi.delivery_date) > 2 AND DATEDIFF(dn.posting_date, soi.delivery_date) <= 7 as "1w",
    DATEDIFF(dn.posting_date, soi.delivery_date) > 7 as ">1w",
    LEFT(CONVERT(soi.delivery_date, CHAR), 7) as "month"
FROM `tabDelivery Note Item` AS dni
JOIN `tabDelivery Note` AS dn ON dni.parent = dn.name
JOIN `tabItem` AS i ON dni.item_code = i.name
JOIN `tabSales Order Item` AS soi ON dni.so_detail = soi.name

WHERE dni.item_code NOT RLIKE '^Di-'
    AND dni.item_code NOT RLIKE '^ENC-'
    AND dn.docstatus = 1
    AND soi.delivery_date BETWEEN "{from_date}" AND "{to_date}"
    {extra_filters}

ORDER BY dn.posting_date DESC
    """.format(from_date=filters.from_date, to_date=filters.to_date, extra_filters=extra_filters)

    data = frappe.db.sql(sql_query, as_dict=True)
    return data

def get_chart(filters):    
   
    extra_filters = ""
    if filters.item_group:
        extra_filters = """ AND i.item_group = "{}" """.format(filters.item_group)
        
    sql_query = """
SELECT
	`month`,
    ROUND( SUM(`0d`) / COUNT(*) * 100 , 1) as "0d",
    ROUND( SUM(`2d`) / COUNT(*) * 100 , 1) as "2d",
    ROUND( SUM(`1w`) / COUNT(*) * 100 , 1) as "1w",
    ROUND( SUM(`>1w`) / COUNT(*) * 100 , 1) as ">1w",
    COUNT(*) as "Line items"
FROM (
  SELECT
	dn.name as "DN",
    dni.against_sales_order as "SO",
    dn.customer as "Customer",
    dn.customer_name as "Customer Name",
    dni.item_code as "Item Code",
    i.item_name as "Item Name",
    i.item_group as "Item Group",
    soi.delivery_date as "Planned Date",
    dn.posting_date as "Shipped Date",
    DATEDIFF(dn.posting_date, soi.delivery_date) as "Delay",
    DATEDIFF(dn.posting_date, soi.delivery_date) <= 0 as "0d",
    DATEDIFF(dn.posting_date, soi.delivery_date) > 0 AND DATEDIFF(dn.posting_date, soi.delivery_date) <= 2 as "2d",
    DATEDIFF(dn.posting_date, soi.delivery_date) > 2 AND DATEDIFF(dn.posting_date, soi.delivery_date) <= 7 as "1w",
    DATEDIFF(dn.posting_date, soi.delivery_date) > 7 as ">1w",
    LEFT(CONVERT(soi.delivery_date, CHAR), 7) as "month"
  FROM `tabDelivery Note Item` AS dni
  JOIN `tabDelivery Note` AS dn ON dni.parent = dn.name
  JOIN `tabItem` AS i ON dni.item_code = i.name
  JOIN `tabSales Order Item` AS soi ON dni.so_detail = soi.name

  WHERE dni.item_code NOT RLIKE '^Di-'
    AND dni.item_code NOT RLIKE '^ENC-'
    AND dn.docstatus = 1
    AND soi.delivery_date BETWEEN "{from_date}" AND "{to_date}"
    {extra_filters}
) as sd -- shipping delays

GROUP BY `Month`
ORDER BY `Month` ASC
    """.format(from_date=filters.from_date, to_date=filters.to_date, extra_filters=extra_filters)
    
    data = frappe.db.sql(sql_query, as_dict=True)
    
    months = [row['month'] for row in data]
    percent_0d = [row['0d'] for row in data]
    percent_2d = [row['2d'] for row in data]
    percent_1w = [row['1w'] for row in data]
    percent_1wp = [row['>1w'] for row in data]

    
    chart = {
        "data": {
            "labels": months,
            "datasets": [{
                "name": "on time",
                "values": percent_0d,
            }, {
                "name": "1-2 day",
                "values": percent_2d,
            }, {
                "name": "3-7 day",
                "values": percent_1w,
            }, {
                "name": ">7 day",
                "values": percent_1wp,
            }],
        },
        "type": 'bar',
        "barOptions": {
            "stacked": True,
            "spaceRatio": 0.1,
        },
        "axisOptions": {
            "xIsSeries": True,
            "shortenYAxisNumbers": True
        },
        "title": "Percentage of on-time delivery",
        "height": 400,
    }
    return chart
