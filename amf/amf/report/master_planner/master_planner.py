# Copyright (c) 2013, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    return [
        {"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 100},
        {"label": "Sales Order", "fieldname": "sales_order", "fieldtype": "Link", "options": "Sales Order", "width": 100},
        {"label": "Customer", "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 250},
        {"label": "Qty", "fieldname": "quantity", "fieldtype": "Data", "width": 75},
        {"label": "Stock Qty", "fieldname": "stock_qty", "fieldtype": "Data", "width": 75},
        {"label": "Item Code", "fieldname": "item_code", "fieldtype": "Data", "width": 120},
        {"label": "Item Name", "fieldname": "item_name", "fieldtype": "Data", "width": 250},
        {"label": "Shipping Date", "fieldname": "shipping_date", "fieldtype": "Date", "width": 100},
        {"label": "Work Order", "fieldname": "work_orders", "fieldtype": "HTML", "width": 250},
        {"label": "Delivery Note", "fieldname": "delivery_notes", "fieldtype": "HTML", "width": 250},
    ]

def get_data(filters):
    conditions = ""
    if filters.get("from_date"):
        conditions += " AND so.transaction_date >= %(from_date)s"
    if filters.get("to_date"):
        conditions += " AND so.transaction_date <= %(to_date)s"
    if filters.get("customer"):
        conditions += " AND so.customer = %(customer)s"
    # Fetch data grouped by item_code
    data = frappe.db.sql(f"""
        SELECT
            so.status AS status,
            soi.parent AS sales_order,
            so.customer_name AS customer,
            soi.delivery_date AS shipping_date,
            soi.item_code AS item_code,
            soi.item_name AS item_name,
            soi.qty AS quantity,
            GROUP_CONCAT(DISTINCT wo.name) AS work_orders,
            GROUP_CONCAT(DISTINCT dn.name) AS delivery_notes
        FROM
            `tabSales Order Item` soi
        INNER JOIN
            `tabSales Order` so ON soi.parent = so.name
        LEFT JOIN
            `tabWork Order` wo ON wo.sales_order = so.name AND wo.production_item = soi.item_code
        LEFT JOIN
            `tabDelivery Note Item` dni ON dni.against_sales_order = so.name AND dni.item_code = soi.item_code
        LEFT JOIN
            `tabDelivery Note` dn ON dn.name = dni.parent
        WHERE
            so.docstatus IN (0, 1) AND  wo.docstatus IN (0, 1) AND  dn.docstatus IN (0, 1)
            {conditions}
        GROUP BY
            soi.name
        ORDER BY
            soi.delivery_date ASC
    """, filters, as_dict=True)
    
    # Extract unique item codes from the data
    item_codes = [row['item_code'] for row in data]
    unique_item_codes = list(set(item_codes))
    
    # Fetch total stock quantities for these item codes from `tabBin`
    if unique_item_codes:
        placeholders = ', '.join(['%s'] * len(unique_item_codes))
        query = f"""
            SELECT item_code, SUM(actual_qty) as stock_qty
            FROM `tabBin`
            WHERE item_code IN ({placeholders}) AND (warehouse = "Assemblies - AMF21" || warehouse = "Main Stock - AMF21")
            GROUP BY item_code
        """
        stock_qtys = frappe.db.sql(query, tuple(unique_item_codes), as_dict=True)
    else:
        stock_qtys = []

    # Create a dictionary for quick lookup of stock quantities
    stock_qty_dict = {row['item_code']: row['stock_qty'] for row in stock_qtys}
    
    # Assign colors to Sales Orders
    colors_list = ['#e6f7ff', '#fff7e6', '#e6ffe6', '#ffe6f2', '#f0e6ff']
    sales_order_colors = {}
    color_index = 0

    # For each item, fetch related Work Orders and Delivery Notes
    for row in data:
        sales_order = row['sales_order']
        if sales_order not in sales_order_colors:
            # Assign next color
            sales_order_colors[sales_order] = colors_list[color_index % len(colors_list)]
            color_index += 1
        # Assign the color to the row
        row['_style'] = 'background-color: {}'.format(sales_order_colors[sales_order])
        
        # Create clickable link for Item Code
        item_code = row['item_code']
        row['stock_qty'] = stock_qty_dict.get(item_code, 0)
        row['item_code'] = f'<a href="/desk#Form/Item/{item_code}">{item_code}</a>'
        
        # Create clickable links for Work Orders
        if row.get('work_orders'):
            work_order_names = row['work_orders'].split(',')
            work_order_links = [f'<a href="/desk#Form/Work Order/{wo.strip()}">{wo.strip()}</a>' for wo in work_order_names]
            row['work_orders'] = ' / '.join(work_order_links)
        
        # Create clickable links for Delivery Notes
        if row.get('delivery_notes'):
            delivery_note_names = row['delivery_notes'].split(',')
            delivery_note_links = [f'<a href="/desk#Form/Delivery Note/{dn.strip()}">{dn.strip()}</a>' for dn in delivery_note_names]
            row['delivery_notes'] = ' / '.join(delivery_note_links)
        
    return data
