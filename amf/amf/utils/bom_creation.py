from __future__ import unicode_literals
import frappe
import json
from frappe import _, _dict
from frappe.utils import cstr, flt, getdate, cint, now_datetime, add_days, get_link_to_form
from erpnext.manufacturing.doctype.bom import bom
from amf.amf.utils.stock_entry import (
    _get_or_create_log,
    update_log_entry
)

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
        # Fetch all active and default BOMs for enabled items
        query = """
            SELECT 
                bom.name, 
                bom.item 
            FROM 
                `tabBOM` AS bom
            INNER JOIN 
                `tabItem` AS item 
            ON 
                bom.item = item.name
            WHERE 
                bom.is_active = 1 AND 
                bom.is_default = 1 AND 
                item.disabled = 0
        """
        all_boms = frappe.db.sql(query, as_dict=True)
        
        for bom in all_boms:
            #print(f"Processing BOM: {bom.name} for Item: {bom.item}")
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

if __name__ == "__main__":
    # Execute the update routine
    try:
        update_boms_with_latest_versions()
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        print(traceback.format_exc())


def create_bom_for_assembly(assembly_code, materials, scraps = None, check_existence=False, log_id=None):
    """Creates a BOM in Draft state. Does not submit."""

    # 1. checking log_id
    if not log_id:
        # créer un log local si aucun log parent n’est fourni
        context = _dict(doctype="BOM", name=f"BOM Creation - {assembly_code}")
        log_id = _get_or_create_log(context)
    update_log_entry(log_id, f"[{now_datetime()}] Starting BOM creation for assembly {assembly_code}")

    # 2. validate parameter
    if not assembly_code:
        frappe.throw(_("assembly_code is required to create a BOM"))

    # 3. validate materials
    for material in materials:
        while not frappe.db.exists("Item", {"name": material.get("item_code")}):
            frappe.throw(_("Material item {0} does not exist. Cannot create BOM for {1}.").format(material.get("item_code"), assembly_code))
    
    # 4. validate scraps
    if scraps:
        for scrap in (scraps or []):
            while not frappe.db.exists("Item", {"name": scrap.get("item_code")}):
                frappe.throw(_("Scrap item {0} does not exist. Cannot create BOM for {1}.").format(scrap.get("item_code"), assembly_code))
    
    # 5. check if there is already an existing BOM for this item
    if frappe.db.exists("BOM", {"item": assembly_code}) and check_existence:
        update_log_entry(log_id, f"[{now_datetime()}] BOM already exists for assembly {assembly_code}. Skipping.")
        return

    
    try:
        # 6. creating new BOM
        bom_doc = frappe.new_doc("BOM")
        bom_doc.item = assembly_code
        bom_doc.is_active = 1
        bom_doc.is_default = 1
        bom_doc.quantity = 1
        bom_doc.company = frappe.get_cached_value('User', frappe.session.user, 'company')
        update_log_entry(log_id, f"[{now_datetime()}] Initialized BOM doc for {assembly_code}")

        # 7. add materials in BOM item table 
        for material in materials:
            material_code = material.get("item_code")
            #checking if material has a bom 
            filters = {"item": material_code, "is_active": 1, "is_default": 1}
            if frappe.db.exists("BOM", filters):
                material_bom = frappe.db.get_value("BOM", filters, "name")
            else:
                material_bom = None
            print(material_bom)
            if material.get('qty'): # Only add materials with a quantity > 0
                #print(material.get("item_code"))
                bom_doc.append("items", {
                    "item_code": material_code,
                    "qty": material.get("qty"),
                    "bom_no": material_bom
                })

        # 8. add scrap material in BOM scrap item table
        if scraps:
            for scrap in scraps:
                scrap_code = scrap.get("item_code")
                #checking if material has a bom 
                filters = {"item": scrap_code, "is_active": 1, "is_default": 1}
                if frappe.db.exists("BOM", filters):
                    scrap_bom = frappe.db.get_value("BOM", filters, "name")
                else:
                    scrap_bom = None
                #print(scrap.get("item_code"))
                if scrap.get('qty'): # Only add scraps with a quantity > 0
                    bom_doc.append("scrap_items", {
                        "item_code": scrap_code,
                        "stock_qty": scrap.get("qty"),
                        "bom_no": scrap_bom
                    })
        
        # 9 Insert, enrich scraps, save & submit
        bom_doc.insert(ignore_permissions=True)
        update_log_entry(log_id, f"[{now_datetime()}] Inserted BOM document (Draft)")

        fill_scrap_details(bom_doc)         # complète les champs des scraps (item_name, rate, etc.)
        bom_doc.save()
        bom_doc.submit()
        frappe.db.commit() # Commit the transaction after the final step.
        update_log_entry(log_id, f"[{now_datetime()}] Created and submitted BOM {bom_doc.name} for assembly {assembly_code}")

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"BOM Creation Failed for {assembly_code}")
        update_log_entry(log_id, f"[{now_datetime()}] Error creating BOM for {assembly_code}: {e}")
        frappe.throw(_("Error creating BOM for {0}: {1}").format(assembly_code, e))

    
def fill_scrap_details(bom_doc):
    """Complète automatiquement les champs des scrap_items en se basant sur get_bom_material_detail()."""
    for scrap in bom_doc.get("scrap_items") or []:
        if not scrap.item_code:
            continue

        # On utilise directement le bom_doc qu'on est en train de créer
        args = {
            "item_code": scrap.item_code,
            "item_name": scrap.item_name or "",
            "bom_no": "",
            "uom": scrap.stock_uom or "",
            "stock_qty": scrap.stock_qty or 1,
        }

        try:
            ret = bom_doc.get_bom_material_detail(args)
        except Exception as e:
            frappe.throw(f"Error in get_bom_material_detail for scrap {scrap.item_code} : {e}")
            frappe.log_error(frappe.get_traceback(), f"Error in get_bom_material_detail for scrap {scrap.item_code}")
            continue

        # On copie les champs pertinents
        for key in ["item_name", "stock_uom", "rate", "base_rate"]:
            if not scrap.get(key):
                scrap.set(key, ret.get(key))

        # Calcul du montant
        scrap.amount = (scrap.stock_qty or 0.0) * (scrap.rate or 0.0)