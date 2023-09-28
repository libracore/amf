from erpnext.stock.doctype.stock_entry.stock_entry import get_additional_costs
import frappe
from frappe.utils.data import flt

@frappe.whitelist()
def make_stock_entry(work_order_id, serial_no_id=None):
	print("Creating New Stock Entry.")
	purpose = 'Manufacture'
	work_order = frappe.get_doc("Work Order", work_order_id)
	
	if not frappe.db.get_value("Warehouse", work_order.wip_warehouse, "is_group") \
			and not work_order.skip_transfer:
		wip_warehouse = work_order.wip_warehouse
	else:
		wip_warehouse = None

	stock_entry = frappe.new_doc("Stock Entry")
	stock_entry.purpose = purpose
	stock_entry.work_order = work_order_id
	stock_entry.company = work_order.company
	stock_entry.from_bom = 1
	stock_entry.bom_no = work_order.bom_no
	stock_entry.use_multi_level_bom = work_order.use_multi_level_bom
	stock_entry.fg_completed_qty = 1
	if work_order.bom_no:
		stock_entry.inspection_required = frappe.db.get_value('BOM', work_order.bom_no, 'inspection_required')

	if purpose=="Material Transfer for Manufacture":
		stock_entry.to_warehouse = wip_warehouse
		stock_entry.project = work_order.project
	else:
		stock_entry.from_warehouse = wip_warehouse
		stock_entry.to_warehouse = work_order.fg_warehouse
		stock_entry.project = work_order.project
		if purpose=="Manufacture":
			additional_costs = get_additional_costs(work_order, fg_qty=stock_entry.fg_completed_qty)
			stock_entry.set("additional_costs", additional_costs)

	stock_entry.set_stock_entry_type()
	stock_entry.get_items()

	# Fetch the BOM
	bom = frappe.get_doc("BOM", stock_entry.bom_no)

    # Loop through each item in the BOM and multiply its quantity by fg_completed_qty
	bom_item_quantities = {}
	for item in bom.items:
		bom_item_quantities[item.item_code] = item.qty * stock_entry.fg_completed_qty
		print(bom_item_quantities[item.item_code])

	# Loop through each item in the Stock Entry and update its quantity based on the BOM
	for item in stock_entry.items:
		if item.item_code in bom_item_quantities:
			# Note: Using Frappe's flt function to handle float precision
			item.qty = flt(bom_item_quantities[item.item_code])
			item.transfer_qty = flt(item.qty * item.conversion_factor)

	# Add these lines after stock_entry.get_items()
	last_item_idx = len(stock_entry.items) - 1  # Index of the last item
	last_item = stock_entry.items[last_item_idx]

	# Check if has_serial_no is set to 1 for the last item
	if frappe.db.get_value("Item", last_item.item_code, "has_serial_no") == 1:
		last_item.serial_no = serial_no_id  # Set the serial number for the last item

	# Commit changes
	stock_entry.save()
	stock_entry.submit()

	#stock_entry.insert()
	return stock_entry