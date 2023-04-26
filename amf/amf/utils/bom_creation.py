from __future__ import unicode_literals
import frappe
import json
import frappe.utils
from frappe.utils import cstr, flt, getdate, cint, nowdate, add_days, get_link_to_form
from frappe import _

@frappe.whitelist()
def get_wo_items(sales_order, for_raw_material_request=0):
    '''Returns items with BOM that already do not have a linked work order'''
    sales_order = frappe.get_doc('Sales Order', sales_order)
    items = []
    for table in [sales_order.items, sales_order.packed_items]:
        for i in table:
            bom = get_default_bom_item(i.item_code)
            request_type = get_request_type(i.item_code)
            print(f"Request type: {request_type}")
            stock_qty = i.qty if i.doctype == 'Packed Item' else i.stock_qty
            if not for_raw_material_request:
                total_work_order_qty = flt(frappe.db.sql('''select sum(qty) from `tabWork Order`
                    where production_item=%s and sales_order=%s and sales_order_item = %s and docstatus<2''', (i.item_code, sales_order.name, i.name))[0][0])
                pending_qty = stock_qty - total_work_order_qty
            else:
                pending_qty = stock_qty

            if pending_qty and request_type == 'Manufacture':
                items.append(dict(
                    name= i.name,
                    item_code= i.item_code,
                    description= i.description,
                    bom = bom,
                    warehouse = i.warehouse,
                    pending_qty = pending_qty,
                    required_qty = pending_qty if for_raw_material_request else 0,
                    sales_order_item = i.name
                ))
    return items

def get_default_bom_item(item_code):
	bom = frappe.get_all('BOM', dict(item=item_code, is_active=True),
			order_by='is_default desc')
	bom = bom[0].name if bom else None

	return bom

def get_request_type(item_code):
    item = frappe.get_doc('Item', item_code)
    request_type = item.default_material_request_type if item.default_material_request_type else None

    return request_type
