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
    Parses a 'head_name' string to generate related component names and a detailed description.

    Args:
        head_name (str): The input string, e.g., "V-DS-1-10-100-C-P".

    Returns:
        dict: A dictionary containing 'seat_name', 'plug_name', 'head_rnd', and 'head_description'.
    """
    # --- Mappings for Description Generation ---
    # These dictionaries map codes from head_name to human-readable descriptions.
    valve_type_map = {
        'D': 'Distribution',      'DS': 'Distribution/Switch',
        'B': 'Bypass',            'DA': 'Distribution/Angled',
        'O': 'On/Off',            'OS': 'On/Off-Switch',
        'SA': 'Switch/Angled',     'SL': 'Sample Loop',
        'T': 'Triangle',          'M': 'Multiplexing',
        'C': 'Check'
    }
    material_map = {
        'C': 'PCTFE',             'P': 'PTFE',
        'U': 'UHMW-PE',           'V': 'Viton',
        'E': 'EPDM',              'S': 'Stainless Steel',
        'K': 'PEEK'
    }

    # --- Initialize Return Variables ---
    seat_name = ""
    plug_name = ""
    head_rnd = ""
    head_description = ""

    if not head_name:
        return {
            "seat_name": seat_name,
            "plug_name": plug_name,
            "head_rnd": head_rnd,
            "head_description": head_description,
        }

    try:
        # Check if the hyphen exists before trying to split
        if '-' in head_name:
            # Extract the part after the first hyphen
            extracted_part = head_name.split('-', 1)[1]
            head_rnd = 'V-' + extracted_part
            
            sub_parts = extracted_part.split('-')

            # --- seat_name Logic ---
            # 'SEAT-' followed by all parts except the last one.
            seat_name = 'SEAT-' + '-'.join(sub_parts[:-1])

            # --- plug_name Logic ---
            # 'PLUG-' followed by all parts except the second-to-last one.
            if len(sub_parts) > 2:
                # Combine all parts except the second-to-last
                plug_name = 'PLUG-' + '-'.join(sub_parts[:-2] + sub_parts[-1:])
            else:
                # Fallback if there aren't enough parts to exclude the second-to-last.
                plug_name = 'PLUG-' + '-'.join(sub_parts)

            # --- head_description Generation ---
            # Generate the multi-line description if the pattern is matched (at least 6 parts).
            if len(sub_parts) >= 6:
                valve_type_code = sub_parts[0]
                stages = sub_parts[1]
                ports = sub_parts[2]
                channel_code = sub_parts[3]
                valve_material_code = sub_parts[4]
                plug_material_code = sub_parts[5]

                # Look up values from maps, with a fallback for unknown codes.
                valve_type = valve_type_map.get(valve_type_code, 'Unknown')
                valve_material = material_map.get(valve_material_code, 'Unknown')
                plug_material = material_map.get(plug_material_code, 'Unknown')
                
                # Dynamically calculate Channel Size
                try:
                    # Convert the channel code to a float, divide by 100, and format as a string.
                    channel_size_value = float(channel_code) / 100
                    channel_size = f"{channel_size_value} mm"
                except (ValueError, IndexError):
                    channel_size = 'Unknown'


                head_description = (
                    f"<b>Valve Type:</b> {valve_type}<br>"
                    f"<b>Valve Head:</b> {head_name}<br>"
                    f"<b>Number of Stages:</b> {stages}<br>"
                    f"<b>Number of Ports:</b> {ports}<br>"
                    f"<b>Channel Size:</b> {channel_size}<br>"
                    f"<b>Valve Material:</b> {valve_material}<br>"
                    f"<b>Plug Material:</b> {plug_material}<br>"
                )
        else:
            # Handle cases where head_name doesn't contain a hyphen.
            seat_name = head_name
            plug_name = head_name
            head_rnd = head_name

    except Exception as e:
        # In a real scenario, you might want to log the error.
        # For a server method, throwing an error is often appropriate.
        frappe.throw(f"Error processing head_name: {str(e)}")

    # Return the final dictionary of values.
    return {
        "seat_name": seat_name,
        "plug_name": plug_name,
        "head_rnd": head_rnd,
        "head_description": head_description,
    }
    
@frappe.whitelist()
def get_last_item_code(code_body=None):
    """
    Fetch the last three digits from items in the 'Valve Seat', 'Valve Head', and 'Plug' item groups
    and return the highest three-digit number.
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
        
        # Extract the last three digits from the item code (assumes the format allows this)
        last_digits = item_code[-3:]  # Take the last three characters
        
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

# ==============================================================================
# TOP-LEVEL PUBLIC FUNCTIONS
# These are the functions you will call from your other scripts.
# ==============================================================================
@frappe.whitelist()
def create_plug_from_doc(doc):
    """
    Public-facing function to create a Plug, its Sub-Assembly, and BOM.
    :param doc: The source document (dict or JSON string).
    """
    return _create_component_and_assembly(doc, 'plug')

@frappe.whitelist()
def create_seat_from_doc(doc):
    """
    Public-facing function to create a Valve Seat, its Sub-Assembly, and BOM.
    :param doc: The source document (dict or JSON string).
    """
    return _create_component_and_assembly(doc, 'seat')


# ==============================================================================
# CORE ORCHESTRATOR
# This function manages the workflow but doesn't know the specifics of
# what kind of item it's creating.
# ==============================================================================

def _create_component_and_assembly(doc, item_category):
    """
    Main orchestrator. Creates a component, its Sub-Assembly, and a BOM.
    :param doc: The source document.
    :param item_category: A string ('plug' or 'seat') to determine which component to create.
    """
    # 1. Prepare all necessary data based on the item category.
    component_data, asm_data, bom_materials = _prepare_component_data(doc, item_category)
    if not component_data:
        return  # Stop if initial data is invalid.

    # 2. Create the main component (e.g., the Plug or Valve Seat).
    component_item_code = _create_item_if_not_exists(component_data)

    # 3. Create the Sub-Assembly for the component.
    asm_item_code = _create_item_if_not_exists(asm_data)

    # 4. Create the Bill of Materials (BOM) for the Sub-Assembly.
    _create_bom_for_assembly(asm_item_code, bom_materials)

    frappe.msgprint(_("Successfully processed {0} and its Sub-Assembly {1}.").format(component_item_code, asm_item_code))
    return asm_item_code


# ==============================================================================
# HELPER FUNCTIONS
# These functions perform the specific, repeatable actions.
# ==============================================================================

def _prepare_component_data(doc, item_category):
    """
    Data Factory: Parses the source doc and prepares data dictionaries
    based on the specified item category.
    """
    if isinstance(doc, str):
        doc = frappe.parse_json(doc)

    if item_category == 'plug':
        base_name = doc.get('plug_name')
        base_code = doc.get('plug_code')
        base_rnd = doc.get('plug_rnd')
        base_raw_mat = doc.get('plug_mat')
        base_acc = doc.get('plug_acc')
        item_group = "Plug"
        # BOM for a Plug Assembly includes the plug itself and two magnets.
        bom_materials = [
            {"item_code": base_code, "qty": 1},
            {"item_code": "SPL.3013", "qty": base_acc}  # Example magnet item code
        ]
        
    elif item_category == 'seat':
        base_name = doc.get('seat_name')
        base_code = doc.get('seat_code')
        base_rnd = doc.get('seat_rnd')
        base_raw_mat = doc.get('seat_mat')
        base_acc = doc.get('seat_acc')
        item_group = "Valve Seat"
        # BOM for a Seat Assembly might just include the seat itself.
        bom_materials = [
            {"item_code": base_code, "qty": 1},
            {"item_code": "SPL.3039", "qty": base_acc}
        ]

    else:
        frappe.throw(_("Invalid item category specified: {0}").format(item_category))
        return None, None, None

    if not base_name or not base_code:
        frappe.throw(_("Component Name and Code are required for category: {0}").format(item_category))
        return None, None, None

    # Data for the main component
    component_data = {
        "item_code": base_code,
        "item_name": base_name,
        "item_group": item_group,
        "reference_code": base_rnd, # e.g., doc.get('plug_rnd')
        "item_type": "Component",
        "tag_raw_mat": base_raw_mat   # e.g., doc.get('plug_mat')
    }

    # Data for the Sub-Assembly
    assembly_item_code = base_code[0] + '1' + base_code[2:]
    asm_data = {
        "item_code": assembly_item_code,
        "item_name": base_name,
        "item_group": item_group,
        "reference_code": f"{base_rnd}.ASM",
        "item_type": "Sub-Assembly",
    }

    return component_data, asm_data, bom_materials


def _create_item_if_not_exists(item_data):
    """
    Creates a single Item if it doesn't already exist. Generic and reusable.
    :param item_data: A dictionary containing the item's properties.
    :return: The item_code of the existing or newly created item.
    """
    item_code = item_data.get("item_code")
    if frappe.db.exists("Item", item_code):
        return item_code

    try:
        item_doc = frappe.get_doc({
            "doctype": "Item",
            "item_code": item_code,
            "item_name": item_data.get("item_name"),
            "item_group": item_data.get("item_group"),
            "item_type": item_data.get("item_type"), # Custom field
            "reference_code": item_data.get("reference_code"), # Custom field
            "tag_raw_mat": item_data.get("tag_raw_mat"), # Custom field
            "stock_uom": "Nos",
            "default_material_request_type": "Manufacture",
            "is_stock_item": 1,
            "has_batch_no": 1,
        })
        item_doc.insert(ignore_permissions=True)
        return item_doc.name
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"Item Creation Failed for {item_code}")
        frappe.throw(_("Error creating item {0}: {1}").format(item_code, e))


def _create_bom_for_assembly(assembly_code, materials):
    """
    Creates a Bill of Materials (BOM) for the given assembly item.
    """
    if frappe.db.exists("BOM", {"item": assembly_code}):
        return
    try:
        bom_doc = frappe.get_doc({
            "doctype": "BOM",
            "item": assembly_code,
            "is_active": 1,
            "is_default": 1,
            "quantity": 1,
            "items": materials
        })
        bom_doc.insert(ignore_permissions=True)
        bom_doc.submit()
        frappe.db.commit() # Commit after BOM creation as it's the last step.
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"BOM Creation Failed for {assembly_code}")
        frappe.throw(_("Error creating BOM for {0}: {1}").format(assembly_code, e))

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
        "is_stock_item": 1,
        "tag_raw_mat": doc.get('plug_mat')
    })
    new_item_doc.insert()
    frappe.db.commit()
    
    # 4) Create a sub-assembly record for this new plug
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

def create_asm(doc, group=None):
    """
    Create a Sub-Assembly (or your custom doctype) for the new plug,
    referencing 2 magnets as components.
    Adjust to fit your environment if you don't have a "Sub Assembly" doctype.
    """
    # 1) Validate/parse incoming doc
    if isinstance(doc, str):
        doc = frappe.parse_json(doc)

    plug_item_code = doc.get('plug_code') + 10000
    plug_name = doc.get('plug_name')
    plug_rnd = doc.get('plug_rnd') + '.ASM'
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
        "item_type": "Sub-Assembly",               # Example custom field
        "opening_stock": opening_stock,         # Possibly your custom field
        "stock_uom": default_uom,
        "default_material_request_type": "Manufacture",
        "has_batch_no": 1,
        "is_stock_item": 1,
        "tag_raw_mat": doc.get('plug_mat')
    })
    new_item_doc.insert()
    frappe.db.commit()
    
    # create_bom(doc, 'plug')
    
    return new_item_doc.name

def create_seat(doc):
    # Logic for seat creation
    pass

def create_valve_head(doc):
    # Logic for valve head creation
    pass

def create_final_product(doc):
    # Logic for final product creation
    pass
