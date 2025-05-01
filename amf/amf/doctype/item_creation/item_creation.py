# -*- coding: utf-8 -*-
# Copyright (c) 2024, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.model.document import Document


class ItemCreation(Document):
	pass


@frappe.whitelist()
def populate_fields(head_name):
    """
    Fetch the value of 'head_name' and return the populated
    'seat_name' and 'plug_name' by extracting all characters after the first '-'.
    seat_name will exclude the last part of the string, plug_name will exclude the second-to-last part.
    """
    head_rnd = ""
    seat_name = ""
    plug_name = ""

    if head_name:
        try:
            # Extract the part after the first '-'
            parts = head_name.split('-', 1)
            if len(parts) > 1:
                # Full extracted part (everything after the first '-')
                extracted_part = parts[1]
                head_rnd = 'V-' + extracted_part
                # Split by '-' to get all sections
                sub_parts = extracted_part.split('-')

                # seat_name gets all but the last part
                seat_name = 'SEAT-' + '-'.join(sub_parts[:-1])  # Exclude the last part
                
                # plug_name gets all parts but excludes the second-to-last part
                if len(sub_parts) > 2:
                    plug_name = 'PLUG-' + '-'.join(sub_parts[:-2] + sub_parts[-1:])
                else:
                    plug_name = 'PLUG-' + '-'.join(sub_parts)  # Fallback in case fewer parts are present
            else:
                # Handle case where there is no '-' in head_name
                seat_name = head_name
                plug_name = head_name
                head_rnd = head_name
        except Exception as e:
            frappe.throw(f"Error in processing head_name: {str(e)}")

    # Return values for seat_name and plug_name
    return {
        "seat_name": seat_name,
        "plug_name": plug_name,
        "head_rnd": head_rnd
    }
    
@frappe.whitelist()
def get_last_item_code(code_body=None):
    """
    Fetch the last two digits from items in the 'Valve Seat', 'Valve Head', and 'Plug' item groups
    and return the highest two-digit number.
    """
    # Define the relevant item groups
    
    if code_body:
        item_groups = ['Product']
        # Query to find all item codes in the specified item groups
        items = frappe.db.sql("""
            SELECT item_code
            FROM `tabItem`
            WHERE item_group IN (%s)
            AND disabled = 0
            AND item_code REGEXP '^[0-9]{6}$'
        """, tuple(item_groups))
    else:
        item_groups = ['Valve Head', 'Valve Seat', 'Plug']
        # Query to find all item codes in the specified item groups
        items = frappe.db.sql("""
            SELECT item_code
            FROM `tabItem`
            WHERE item_group IN (%s, %s, %s)
            AND disabled = 0
            AND item_code REGEXP '^[0-9]{6}$'
        """, tuple(item_groups))
        
    # Variable to store the highest two-digit number
    highest_digit_number = None

    # Process each item and extract the last two digits
    for item in items:
        item_code = item[0]  # Assuming 'name' is the item code
        
        # Extract the last two digits from the item code (assumes the format allows this)
        if code_body:
            last_digits = item_code[-2:]  # Take the last two characters
        else:
            last_digits = item_code[-4:]
        
        # Check if the last two characters are numeric
        if last_digits.isdigit():
            last_digits = int(last_digits)
            
            # Compare to find the highest two-digit number
            if highest_digit_number is None or last_digits > highest_digit_number:
                highest_digit_number = last_digits

    # Return the highest two-digit number found, or throw an error if none found
    if highest_digit_number is not None:
        return highest_digit_number
    else:
        frappe.throw("No valid two-digit item codes found in the specified groups.")

@frappe.whitelist()
def create_item(doc, item_type):
    """
    Creates an item (plug, seat, valve head, or final product) based on the item_type provided.
    """
    # doc = frappe._dict(doc)  # Convert the incoming doc to a dict format
    if isinstance(doc, str):
        doc = frappe.parse_json(doc)
    
    if item_type == 'plug':
        return create_plug(doc)
    elif item_type == 'seat':
        return create_seat(doc)
    elif item_type == 'valve_head':
        return create_valve_head(doc)
    elif item_type == 'final_product':
        return create_final_product(doc)
    else:
        frappe.throw("Invalid item type. Please specify 'plug', 'seat', 'valve_head', or 'final_product'.")

def create_plug(doc):
    """
    Create (or reuse) a Plug item, then build a BOM for it
    (including 2 magnets), and create a sub-assembly record.
    """

    # 1) Validate/parse incoming doc
    if isinstance(doc, str):
        doc = frappe.parse_json(doc)

    plug_item_code = doc.get('plug_code')
    plug_name = doc.get('plug_name')
    plug_rnd = doc.get('plug_rnd')
    default_uom = 'Nos'
    opening_stock = doc.get('opening_stock', 0)

    # 2) Check if an item with that code already exists
    if plug_item_code:
        existing_item_name = frappe.db.exists("Item", {"item_code": plug_item_code})
        if existing_item_name:
            return existing_item_name

    # 3) Create a new Plug item
    new_item_doc = frappe.get_doc({
        "doctype": "Item",
        "item_code": plug_item_code,
        "item_name": plug_name,
        "reference_code": plug_rnd,             # example custom field
        "item_group": "Plug",                   # Adjust to your item group
        "item_type": "Component",               # Example custom field
        "opening_stock": opening_stock,         # Possibly your custom field
        "stock_uom": default_uom,
        "default_material_request_type": "Manufacture",
        "has_batch_no": 1,
        "is_stock_item": 1
    })
    new_item_doc.insert()
    frappe.db.commit()

    # 4) Create a BOM for the new plug (includes 2 magnets)
    create_bom(doc, 'plug')

    # 5) Create a sub-assembly record for this new plug
    create_asm(doc, 'plug')

    return new_item_doc.name

def create_bom(doc, item_type, item_code=None, default_uom='Nos'):
    """
    Creates two BOMs for a newly created item:
      1) A "component BOM" for the item itself (parent = item_code),
         containing all raw materials whose 'tag_raw_mat'
         equals the doc's 'plug_mat' or 'seat_mat' value.
      2) A "final assembly BOM" for a new item called '{item_code}-ASM'.
         That BOM includes:
           - The newly created seat/plug itself
           - Either doc.get('plug_acc') (if it's a plug)
             or 2 x "PIN" items (if it's a seat).

    :param doc:         The source doc (dictionary or JSON) with fields:
                          e.g. 'plug_mat', 'seat_mat', 'plug_acc', etc.
    :param item_type:   'plug', 'seat', etc.
    :param item_code:   The code of the newly created item (plug or seat).
                        If not provided, the function infers it from doc.
    :param default_uom: Defaults to 'Nos'.
    :return:            The name of the final assembly BOM (string).
    """

    # Convert doc from JSON string if needed
    if isinstance(doc, str):
        doc = frappe.parse_json(doc)

    # Infer item_code if not given
    if not item_code:
        if item_type == 'plug':
            item_code = doc.get('plug_code')
        elif item_type == 'seat':
            item_code = doc.get('seat_code')
        else:
            frappe.throw(_("Unknown item_type: must be 'plug' or 'seat'."))

    if not item_code:
        frappe.throw(_("No valid item code found in doc for item_type = {0}.").format(item_type))

    # 1) Create the "component BOM" for raw materials
    #
    #    We look up all Items in ERPNext that have
    #    `tag_raw_mat = doc.get('plug_mat')` or `doc.get('seat_mat')`
    #    depending on the item_type. Then we add them as children in a BOM
    #    whose parent is the newly created item itself.
    mat_field = f"{item_type}_mat"   # "plug_mat" or "seat_mat"
    raw_mat_tag_value = doc.get(mat_field)
    if raw_mat_tag_value:
        raw_materials = frappe.get_all(
            "Item",
            filters={"tag_raw_mat": raw_mat_tag_value, "item_group": 'Raw Material', "disabled": 0},
            fields=['name']
        )
    else:
        raw_materials = []
    print(raw_mat_tag_value, raw_materials)
    if raw_materials:
        for rm_item_code in raw_materials:
            print(rm_item_code)
            component_bom_doc = frappe.get_doc({
                "doctype": "BOM",
                "item": item_code,      # the newly created item is the BOM parent
                "quantity": 1,
                "is_active": 1,
                "is_default": 1,         # or True if you want
            })

            # Add each raw material to the BOM items table
            component_bom_doc.append("items", {
                    "item_code": rm_item_code.name,
                    "qty": 0.2,
                    "uom": default_uom,
                    "conversion_factor": 1.0
            })

            component_bom_doc.insert()
            component_bom_doc.submit()

    # 2) Create a "final assembly BOM":
    #
    #    - The parent item is a new or existing item code like:  <item_code>-ASM
    #    - Its child items:
    #       • The newly created seat/plug (1 pc)
    #       • If item_type == 'plug': doc.get('plug_acc') (1 pc)
    #       • If item_type == 'seat': 2 x "PIN"
    # assembly_item_code = f"{item_code}-ASM"

    # # If you need an Item record for the assembly, ensure it exists:
    # if not frappe.db.exists("Item", assembly_item_code):
    #     assembly_item = frappe.get_doc({
    #         "doctype": "Item",
    #         "item_code": assembly_item_code,
    #         "item_name": f"{item_code} Assembly",
    #         "stock_uom": default_uom,
    #         "is_stock_item": 0,        # Usually an assembly item might be non-stock or manufactured
    #         "item_group": "Assembly"   # Adjust to your environment
    #     })
    #     assembly_item.insert()

    # assembly_bom_doc = frappe.get_doc({
    #     "doctype": "BOM",
    #     "item": assembly_item_code,   # the assembly item is the BOM parent
    #     "quantity": 1,
    #     "is_active": 1,
    #     "is_default": 1
    # })

    # # Always include the newly created seat/plug
    # assembly_bom_doc.append("items", {
    #     "item_code": item_code,
    #     "qty": 1,
    #     "uom": default_uom,
    #     "conversion_factor": 1.0
    # })

    # if item_type == 'plug':
    #     plug_acc_code = doc.get('plug_acc')
    #     if plug_acc_code:
    #         assembly_bom_doc.append("items", {
    #             "item_code": plug_acc_code,
    #             "qty": 1,
    #             "uom": default_uom,
    #             "conversion_factor": 1.0
    #         })

    # elif item_type == 'seat':
    #     # Example: we hard-code two "PIN" items.
    #     # If your environment references them differently, adjust accordingly.
    #     assembly_bom_doc.append("items", {
    #         "item_code": "PIN",
    #         "qty": 2,
    #         "uom": default_uom,
    #         "conversion_factor": 1.0
    #     })

    # assembly_bom_doc.insert()
    # assembly_bom_doc.submit()

    # return assembly_bom_doc.name

def create_asm(item_code, default_uom):
    """
    Create a Sub-Assembly (or your custom doctype) for the new plug,
    referencing 2 magnets as components.
    Adjust to fit your environment if you don't have a "Sub Assembly" doctype.
    """
    asm_doc = frappe.get_doc({
        "doctype": "Sub Assembly",  # Adjust to your actual doctype name
        "title": f"Sub Assembly for {item_code}",
        "reference_item_code": item_code
    })

    # Example: record the magnets as well
    asm_doc.append("items", {
        "item_code": "MAGNET",  # same code as used in the BOM
        "qty": 2,
        "uom": default_uom
    })

    asm_doc.insert()
    asm_doc.submit()  # if your doctype requires submission

    return asm_doc.name

def create_seat(doc):
    # Logic for seat creation
    pass

def create_valve_head(doc):
    # Logic for valve head creation
    pass

def create_final_product(doc):
    # Logic for final product creation
    pass
