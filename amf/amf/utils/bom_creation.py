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
            print("Request type: {request_type}".format(request_type=request_type))
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

@frappe.whitelist()
def get_stock_balance_for_all_warehouses(item_code):
    stock_balance = frappe.db.sql("""
        SELECT warehouse, actual_qty
        FROM `tabBin`
        WHERE item_code = %s AND warehouse not rlike 'OLD'
    """, (item_code), as_dict=1)

    return {row.warehouse: row.actual_qty for row in stock_balance}


import frappe
from frappe.model.rename_doc import rename_doc
import traceback

@frappe.whitelist()
def update_boms_with_latest_versions_enqueue():
    frappe.enqueue("amf.amf.utils.bom_creation.update_boms_with_latest_versions", queue='long', timeout=15000)
    return None

def update_boms_with_latest_versions():
    try:
        # Fetch all active and default BOMs
        all_boms = frappe.get_all('BOM', filters={'is_active': 1, 'is_default': 1}, fields=['name', 'item'])
        
        for bom in all_boms:
            print(f"Processing BOM: {bom.name} for Item: {bom.item}")
            try:
                create_new_bom_version(bom.name)
            except Exception as e:
                print(f"Error processing BOM {bom.name}: {e}")
                print(traceback.format_exc())
    except Exception as e:
        print(f"Failed to retrieve BOM list: {e}")
        print(traceback.format_exc())

def create_new_bom_version(bom_name):
    try:
        # Load the original BOM document
        original_bom = frappe.get_doc('BOM', bom_name)
        
        # Create a new draft copy of the BOM
        new_bom = frappe.copy_doc(original_bom)
        new_bom.is_active = 1
        new_bom.is_default = 0  # New version not set as default yet
        new_bom.docstatus = 0   # Set to draft

        updated = False

        # Loop through each item in the BOM
        for item in new_bom.items:
            if item.bom_no:
                # Fetch the latest active BOM for this item
                latest_bom = get_latest_bom(item.item_code)
                
                # Update to the latest BOM if it's different from the current one
                if latest_bom and latest_bom != item.bom_no:
                    print(f"Updating BOM for component: {item.item_code} - {item.bom_no} -> {latest_bom}")
                    item.bom_no = latest_bom
                    updated = True

        # Only save and submit if there were updates
        if updated:
            try:
                new_bom.insert()  # Insert as a new BOM
                new_bom.submit()  # Submit the new BOM version
                set_default_bom(new_bom.item, new_bom.name)
                print(f"New BOM {new_bom.name} created and submitted successfully.")
            except Exception as e:
                print(f"Failed to save or submit new BOM for {bom_name}: {e}")
                print(traceback.format_exc())

    except Exception as e:
        print(f"Error copying or updating BOM {bom_name}: {e}")
        print(traceback.format_exc())

def get_latest_bom(item_code):
    """Helper function to get the latest active BOM for a given item."""
    try:
        latest_bom = frappe.db.get_value('BOM', 
                                         filters={'item': item_code, 'is_active': 1, 'is_default': 1},
                                         fieldname='name',
                                         order_by='creation desc')
        return latest_bom
    except Exception as e:
        print(f"Failed to retrieve latest BOM for item {item_code}: {e}")
        print(traceback.format_exc())
        return None

def set_default_bom(item_code, bom_name):
    """Set the specified BOM as the default BOM for the item."""
    try:
        frappe.db.set_value('BOM', bom_name, 'is_default', 1)
        frappe.db.sql("""UPDATE `tabBOM` SET is_default = 0 WHERE item = %s AND name != %s""", (item_code, bom_name))
        frappe.db.commit()
    except Exception as e:
        print(f"Failed to set default BOM for item {item_code}: {e}")
        print(traceback.format_exc())

# Execute the update routine
try:
    update_boms_with_latest_versions()
except Exception as e:
    print(f"An unexpected error occurred: {e}")
    print(traceback.format_exc())
