from __future__ import unicode_literals
import frappe
import json
import frappe.utils
from frappe import _

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