# -*- coding: utf-8 -*-
# Copyright (c) 2024, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import time
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
                valve_material = material_map.get(
                    valve_material_code, 'Unknown')
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
def get_last_item_code():
    """
    Fetch the last three digits from items in the 'Valve Seat', 'Valve Head', and 'Plug' item groups
    and return the highest three-digit number.
    """
    # Define the relevant item groups

    # if code_body:
    item_groups = ['Product', 'Valve Head', 'Valve Seat', 'Plug']
    # Query to find all item codes in the specified item groups
    items = frappe.db.sql("""
            SELECT item_code
            FROM `tabItem`
            WHERE item_group IN (%s, %s, %s, %s)
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
                print(last_digits)
                highest_digit_number = last_digits

    # Return the highest two-digit number found, or throw an error if none found
    if highest_digit_number is not None:
        return highest_digit_number+1
    else:
        frappe.throw(
            "No valid two-digit item codes found in the specified groups.")

# ==============================================================================
# 1. MAIN ENTRY POINT (ROUTER)
# This is the only function you need to call from the client-side.
# It decides which workflow to run based on the 'group'.
# ==============================================================================

@frappe.whitelist()
def create_item_from_doc(doc, group=None):
    """
    Acts as a router to initiate the correct creation workflow.

    :param doc: The source document (dict or JSON string).
    :param group: The type of item to create ('plug', 'seat', or 'head').
    """
    if isinstance(doc, str):
        doc = frappe.parse_json(doc)

    if group in ['plug', 'seat']:
        # Workflow for creating a simple component and its sub-assembly.
        return _create_simple_component_and_assembly(doc, group)
    elif group == 'head':
        # Special workflow for creating the final Valve Head assembly from other sub-assemblies.
        return _create_final_valve_head_assembly(doc)
    else:
        frappe.throw(_("Invalid item group specified: {0}").format(group))


# ==============================================================================
# 2. WORKFLOW ORCHESTRATORS
# Each function here manages a complete, multi-step process.
# ==============================================================================

def _create_simple_component_and_assembly(doc, group):
    """
    Orchestrator for simple parts:
    1. Prepares data for a component (e.g., Plug) and its sub-assembly.
    2. Creates the component Item.
    3. Creates the sub-assembly Item.
    4. Creates a BOM for the sub-assembly.
    """
    component_data, asm_data, bom_materials = _prepare_simple_component_data(doc, group)

    # Create the two items first.
    component_item_code = _create_item_if_not_exists(component_data)
    asm_item_code = _create_item_if_not_exists(asm_data)

    # Create the BOM for the sub-assembly.
    _create_bom_for_assembly(asm_item_code, bom_materials)

    frappe.msgprint(_("Successfully created {0} and Sub-Assembly {1}.").format(component_item_code, asm_item_code))
    return asm_item_code


def _create_final_valve_head_assembly(doc):
    """
    Special orchestrator for the Valve Head:
    1. Prepares data for the final assembly.
    2. Creates the final assembly Item.
    3. Creates a BOM using other sub-assemblies as materials.
    """
    # Note: This workflow assumes the plug and seat sub-assemblies already exist.
    # You should ensure they are created before calling this.
    final_assembly_data, bom_materials = _prepare_valve_head_data(doc)

    # Create the final Valve Head Item.
    final_assembly_code = _create_item_if_not_exists(final_assembly_data)

    # Create the BOM for the final assembly.
    _create_bom_for_assembly(final_assembly_code, bom_materials)

    frappe.msgprint(_("Successfully created Final Assembly {0}.").format(final_assembly_code))
    return final_assembly_code


# ==============================================================================
# 3. DATA PREPARATION HELPERS (FACTORIES)
# Each function is responsible for gathering and structuring data for one workflow.
# ==============================================================================

def _prepare_simple_component_data(doc, group):
    """Prepares data dictionaries for a simple component and its assembly."""
    if group == 'plug':
        base_name = doc.get('plug_name')
        base_code = doc.get('plug_code')
        item_group = "Plug"
        valuation_rate = 20
        bom_materials = [
            {"item_code": base_code, "qty": 1},
            {"item_code": "SPL.3013", "qty": doc.get('plug_acc', 0)}
        ]
    else: # group == 'seat'
        base_name = doc.get('seat_name')
        base_code = doc.get('seat_code')
        item_group = "Valve Seat"
        valuation_rate = 60
        bom_materials = [
            {"item_code": base_code, "qty": 1},
            {"item_code": "SPL.3039", "qty": doc.get('seat_acc', 0)}
        ]

    if not all([base_name, base_code]):
        frappe.throw(_("Name and Code are required for {0}.").format(group))

    component_data = {
        "item_code": base_code,
        "item_name": base_name,
        "item_group": item_group,
        "item_type": "Component",
        "valuation_rate": valuation_rate,
        "reference_code": doc.get(f'{group}_rnd'),
        "tag_raw_mat": doc.get(f'{group}_mat'),
    }

    # Assembly code is derived by setting the second digit to '1'
    assembly_item_code = base_code[0] + '1' + base_code[2:]
    asm_data = {
        "item_code": assembly_item_code,
        "item_name": f"{base_name}",
        "item_group": item_group,
        "item_type": "Sub-Assembly",
        "reference_code": f"{doc.get(f'{group}_rnd')}.ASM",
    }

    return component_data, asm_data, bom_materials


def _prepare_valve_head_data(doc):
    """Prepares data for the final Valve Head assembly."""
    head_name = doc.get('head_name')
    head_code = doc.get('head_code')
    plug_code = doc.get('plug_code')
    seat_code = doc.get('seat_code')

    if not all([head_name, head_code, plug_code, seat_code]):
        frappe.throw(_("Head, Plug, and Seat codes are required to build the Valve Head."))

    # CRITICAL: The BOM must use the SUB-ASSEMBLY codes, not the base component codes.
    plug_assembly_code = plug_code[0] + '1' + plug_code[2:]
    seat_assembly_code = seat_code[0] + '1' + seat_code[2:]

    final_assembly_data = {
        "item_code": head_code,
        "item_name": head_name,
        "item_group": "Valve Head",
        "item_type": "Finished Good", # Or "Assembly", depending on your setup
        "reference_code": doc.get('head_rnd'),
        "description": doc.get('head_description'),
    }

    bom_materials = [
        {"item_code": plug_assembly_code, "qty": 1},
        {"item_code": seat_assembly_code, "qty": 1}
    ]

    return final_assembly_data, bom_materials


# ==============================================================================
# 4. GENERIC, REUSABLE ACTION HELPERS
# These functions perform single, well-defined tasks.
# ==============================================================================

def _create_item_if_not_exists(item_data):
    """Creates an Item if it doesn't already exist. Safe and reusable."""
    item_code = item_data.get("item_code")
    if frappe.db.exists("Item", item_code):
        return item_code

    try:
        item_doc = frappe.get_doc({
            "doctype": "Item",
            "stock_uom": "Nos",
            "default_material_request_type": "Manufacture",
            "is_stock_item": 1,
            "has_batch_no": 1,
            **item_data  # Merge the specific item data
        })
        item_doc.insert(ignore_permissions=True)
        item_doc.save()
        frappe.db.commit()
        return item_doc.name
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"Item Creation Failed for {item_code}")
        frappe.throw(_("Error creating item {0}: {1}").format(item_code, e))


def _create_bom_for_assembly(assembly_code, materials):
    """Creates a BOM in Draft state. Does not submit."""
    for material in materials:
        while not frappe.db.exists("Item", {"name": material.get("item_code")}):
            frappe.db.commit()
    
    if frappe.db.exists("BOM", {"item": assembly_code}):
        return

    try:
        bom_doc = frappe.new_doc("BOM")
        bom_doc.item = assembly_code
        bom_doc.is_active = 1
        bom_doc.is_default = 1
        bom_doc.quantity = 1
        bom_doc.company = frappe.get_cached_value('User', frappe.session.user, 'company')

        for material in materials:
            if material.get('qty'): # Only add materials with a quantity > 0
                bom_doc.append("items", {
                    "item_code": material.get("item_code"),
                    "qty": material.get("qty")
                })

        bom_doc.insert(ignore_permissions=True)
        bom_doc.save()
        bom_doc.submit()
        frappe.db.commit() # Commit the transaction after the final step.
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"BOM Creation Failed for {assembly_code}")
        frappe.throw(_("Error creating BOM for {0}: {1}").format(assembly_code, e))
        
