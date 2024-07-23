from __future__ import unicode_literals
from amf.amf.utils.stock_summary import get_stock
from amf.amf.utils.utilities import commit_database
import frappe
import json
import frappe.utils
from frappe import _
import tkinter as tk
from tkinter import messagebox

@frappe.whitelist()
def make_work_orders(items, sales_order, company, project=None):
    '''Make Work Orders against the given Sales Order for the given `items`'''
    items = json.loads(items).get('items')
    out = []

    for i in items:
        if not i.get("bom"):
            frappe.throw(_("Please select BOM against item {0}").format(i.get("item_code")))
        if not i.get("pending_qty"):
            frappe.throw(_("Please select Qty against item {0}").format(i.get("item_code")))
        if not i.get("simple_description"):
            i["simple_description"] = ''

        sales_order_item = frappe.get_doc('Sales Order Item', i['sales_order_item'])
        if not sales_order_item.delivery_date:
            frappe.throw(_("Please set delivery date against item {0} in the Sales Order {1}").format(i['item_code'], sales_order))
        delivery_date = sales_order_item.delivery_date

        # Check if the quantity in items is greater than the sales order quantity
        if i['pending_qty'] > sales_order_item.qty:
            remaining_qty = i['pending_qty'] - sales_order_item.qty

            # Create a work order with sales order quantity
            work_order = frappe.get_doc(dict(
                doctype='Work Order',
                production_item=i['item_code'],
                bom_no=i.get('bom'),
                qty=sales_order_item.qty,
                company=company,
                sales_order=sales_order,
                sales_order_item=i['sales_order_item'],
                project=project,
                fg_warehouse=i['warehouse'],
                description=i['description'],
                destination=i['destination'],
                simple_description=i['simple_description'],
                p_e_d=delivery_date
            )).insert()
            work_order.set_work_order_operations()
            work_order.save()
            work_order.submit()
            out.append(work_order)

            # Create another work order with the remaining quantity
            work_order_remaining = frappe.get_doc(dict(
                doctype='Work Order',
                production_item=i['item_code'],
                bom_no=i.get('bom'),
                qty=remaining_qty,
                company=company,
                sales_order_item=i['sales_order_item'],
                project=project,
                fg_warehouse=i['warehouse'],
                description=i['description'],
                destination=i['destination'],
                simple_description=i['simple_description'],
                p_e_d=delivery_date
            )).insert()
            work_order_remaining.set_work_order_operations()
            work_order_remaining.save()
            work_order_remaining.submit()
            out.append(work_order_remaining)

        else:
            # If pending_qty is less than or equal to sales order quantity, create a single work order
            work_order = frappe.get_doc(dict(
                doctype='Work Order',
                production_item=i['item_code'],
                bom_no=i.get('bom'),
                qty=i['pending_qty'],
                company=company,
                sales_order=sales_order,
                sales_order_item=i['sales_order_item'],
                project=project,
                fg_warehouse=i['warehouse'],
                description=i['description'],
                destination=i['destination'],
                simple_description=i['simple_description'],
                p_e_d=delivery_date
            )).insert()
            work_order.set_work_order_operations()
            work_order.save()
            work_order.submit()
            out.append(work_order)

    return [p.name for p in out]

@frappe.whitelist()
def check_and_create_work_orders(work_order, method=None):
    work_order_doc = frappe.get_doc('Work Order', work_order.name)
    print(work_order_doc)
    if work_order_doc.sales_order:
        sales_order = work_order_doc.sales_order
    else:
        sales_order = None
    required_qty_dict = {rqd_item.item_code: rqd_item.required_qty for rqd_item in work_order_doc.required_items}
    bom_items = frappe.get_all('BOM Item', filters={'parent': work_order_doc.bom_no}, fields=['item_code', 'qty'])
    missing_items = []

    for item in bom_items:
        print(item)
        stock_qty = get_stock(item['item_code'])
        total_qty = sum(stock['actual_qty'] for stock in stock_qty)
        print(stock_qty, total_qty)
         # Use the required_qty from the required_items
        required_qty = required_qty_dict.get(item['item_code'], 0)
        if total_qty < required_qty*item['qty']:
            qty_rqd = required_qty*item['qty']-total_qty
            if frappe.db.exists('BOM', {'item': item['item_code'], 'is_active': 1, 'is_default': 1}):
                missing_items.append({'item_code': item['item_code'], 'qty': qty_rqd})
    
    print("missing items:", missing_items)
    if missing_items:
        create_work_orders_for_missing_items(missing_items, sales_order)

    return {'missing_items': missing_items}

@frappe.whitelist()
def create_work_orders_for_missing_items(missing_items, sales_order=None):
    work_orders = []
    for item in missing_items:
        item_code = item['item_code']
        qty = item['qty']
        
        bom = frappe.get_value('BOM', {'item': item_code, 'is_active': 1, 'is_default': 1}, 'name')
        
        if bom:
            wo = make_work_order(item_code, sales_order, qty, bom)
            wo.submit()
            work_orders.append(wo.name)
            commit_database()
    print(work_orders)
    return work_orders

def make_work_order(item_code, sales_order=None, qty=1, bom_no=None):
    '''Make a single Work Order for the given item'''
    if not bom_no:
        frappe.throw(_("Please select BOM for item {0}").format(item_code))
    if not qty:
        frappe.throw(_("Please select Qty for item {0}").format(item_code))

    work_order = frappe.get_doc(dict(
        doctype='Work Order',
        production_item=item_code,
        bom_no=bom_no,
        qty=qty,
        company='Advanced Microfluidics SA',
        sales_order=sales_order,
        fg_warehouse='Main Stock - AMF21',  # Replace with the appropriate warehouse
        simple_description='Auto-generated Work Order from non-available stock'
    )).insert()
   
    work_order.set_work_order_operations()
    work_order.save()

    return work_order
