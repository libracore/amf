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

		sales_order_item = frappe.get_doc('Sales Order Item', i['sales_order_item'])
		if not sales_order_item.delivery_date:
			frappe.throw(_("Please set delivery date against item {0} in the Sales Order {1}").format(i['item_code'], sales_order))
		delivery_date = sales_order_item.delivery_date

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
