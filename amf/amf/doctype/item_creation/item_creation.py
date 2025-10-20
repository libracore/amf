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

SYRINGE_MAP = {
    "2": {"code": "702000", "rnd"  : "S-50-P",    "qty" : 50  },
    "3": {"code": "703000", "rnd"  : "S-100-P",   "qty" : 100 },
    "4": {"code": "704000", "rnd"  : "S-100-U",   "qty" : 100 },
    "5": {"code": "705000", "rnd"  : "S-250-P",   "qty" : 250 },
    "8": {"code": "708000", "rnd"  : "S-500-P",   "qty" : 500 },
    "9": {"code": "709000", "rnd"  : "S-500-U",   "qty" : 500 },
    "D": {"code": "70D000", "rnd"  : "S-1000-P",  "qty" : 1000},
    "E": {"code": "70E000", "rnd"  : "S-2500-P",  "qty" : 2500},   # pour Pump HV
    "F": {"code": "70F000", "rnd"  : "S-5000P",   "qty" : 5000},   # pour Pump HV
}

@frappe.whitelist()
def populate_fields(head_name):
    """
    Parses a 'head_name' string to generate related component names and a detailed description.

    Args:
        head_name (str): The input string, e.g., "V-DS-1-10-100-C-P".

    Returns:
        dict: A dictionary containing 'seat_name', 'plug_name', 'head_group', 'head_rnd', and 'head_description'.
    """
    # --- Mappings for Description Generation ---
    # These dictionaries map codes from head_name to human-readable descriptions.
    valve_type_map = {
        'D': 'Distribution',      'DS': 'Distribution/Switch',
        'B': 'Bypass',            'DA': 'Distribution/Angled',
        'O': 'On/Off',            'OS': 'On/Off-Switch',
        'SA': 'Switch/Angled',    'SL': 'Sample Loop',
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
    head_group = "Valve Head"

    if not head_name:
        return {
            "seat_name": seat_name,
            "plug_name": plug_name,
            "head_rnd": head_rnd,
            "head_description": head_description,
            "head_group": head_group,
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
        "head_group": head_group,
    }


@frappe.whitelist()
def populate_fields_from_existing_item(item_code):
    """
    Fetches item details from an existing Item document based on the provided item_code.

    Args:
        item_code (str): The code of the item to fetch.
    
    Returns:
        dict: A dictionary containing 'item_name', 'Seat_name', Plug_name', Seat_code', 'Plug_code',
             'item_group', 'reference_code', and 'description'.                                     
    """
    head_code = ""
    head_name = ""
    seat_name = ""
    plug_name = ""
    seat_code = ""
    plug_code = ""
    head_group = ""
    head_rnd = ""
    head_desc = ""

    try:
        #get the main head values
        item = frappe.get_doc('Item', item_code)
        head_code = item_code
        head_name = item.item_name
        head_group = item.item_group
        head_rnd = item.reference_code
        head_desc = item.description

        #print all head details
        print(f"Head Details - Code: {head_code}, Name: {head_name}, Group: {head_group}, RND: {head_rnd}")


        #derive expected seat and plug names
        parts = head_rnd.split('-')
        if (parts[7] ==  'HV'):
            expected_seat_name = 'SEAT-' + '-' .join(parts[1:6]) + '-HV'
        else:
            expected_seat_name = 'SEAT-' + '-' .join(parts[1:6])
        expected_plug_name = 'PLUG-' + '-' .join(parts[1:5]) + '-' + parts[6] 
        incorrect_seat  = False
        incorrect_plug  = False


        bom = frappe.get_all(
            "BOM",
            filters={
                "item": item_code,
                "is_active": 1,
                "is_default": 1
            },
            fields=["name"]
        )
        if not bom:
            frappe.msgprint(_("No active BOM found for Item: {0}").format(item_code))
            frappe.msgprint(_("Creating new BOM for Item: {0}, with expected Seat and Plug components.").format(item_code))
            incorrect_seat  = True
            incorrect_plug  = True
            seat_code = get_item_from_name(expected_seat_name)
            plug_code = get_item_from_name(expected_plug_name)

        else:
            bom_doc = frappe.get_doc("BOM", bom[0].name)

            #check head components in BOM if correct
            for item in bom_doc.items: 
                if item.item_code.startswith('210'):
                    if item.item_name == expected_seat_name:
                        seat_name = item.item_name
                        seat_code = item.item_code
                        incorrect_seat = False
                    else:
                        seat_code = get_item_from_name(expected_seat_name)
                        incorrect_seat = True

                elif item.item_code.startswith('110'):
                    if item.item_name == expected_plug_name:
                        plug_name = item.item_name
                        plug_code = item.item_code
                        incorrect_plug = False
                    else:
                        plug_code = get_item_from_name(expected_plug_name)
                        incorrect_plug = True
                else: 
                    incorrect_seat = True
                    incorrect_plug = True
                    seat_code = get_item_from_name(expected_seat_name)
                    plug_code = get_item_from_name(expected_plug_name)
        
        #create BOM if incorrect
        if incorrect_seat or incorrect_plug:
            frappe.msgprint(_("The BOM for Item: {0} does not contain the expected Seat and Plug components. Creating new BOM").format(item_code))
            bom_materials = [   {"item_code": seat_code, "qty": 1},
                                {"item_code": plug_code, "qty": 1}]
            _create_bom_for_assembly(item_code, bom_materials, check_existence = False)

        seat_name = expected_seat_name
        plug_name = expected_plug_name

        
        return {    "head_code": head_code,
                    "head_name": head_name,
                    "seat_name": seat_name,
                    "plug_name": plug_name,
                    "seat_code": seat_code,
                    "plug_code": plug_code,
                    "head_group": head_group,
                    "head_rnd": head_rnd,
                    "head_description": head_desc
    }
    except Exception as e:
        frappe.throw(f"Error fetching item details: {str(e)}")


def get_item_from_name(item_name):
    """Helper function to get item_code from item_name."""
    try:
        item_code = frappe.db.get_value(
            "Item",
            filters=[
                ["Item", "item_name", "=", item_name],
                ["Item", "disabled", "=", 0],
                ["Item", "item_code", "like", "_10%"],
            ],
            fieldname="item_code",
        )
        return item_code
    except Exception as e:
        frappe.throw(f"Failed to retrieve item code for item name {item_name}: {e}")
        return None


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

    # Variable to store the highest three-digit number
    highest_digit_number = None

    # Process each item and extract the last three digits
    for item in items:
        item_code = item[0]  # Assuming 'name' is the item code

        # Extract the last three digits from the item code (assumes the format allows this)
        last_digits = item_code[-3:]  # Take the last three characters

        # Check if the last three characters are numeric
        if last_digits.isdigit():
            last_digits = int(last_digits)

            # Compare to find the highest three-digit number
            if highest_digit_number is None or last_digits > highest_digit_number:
                print(last_digits)
                highest_digit_number = last_digits

    # Return the highest three-digit number found, or throw an error if none found
    if highest_digit_number is not None:
        return highest_digit_number+1
    else:
        frappe.throw(
            "No valid three-digit item codes found in the specified groups.")
        

@frappe.whitelist()
def get_data_for_preview(doc, group=None):
    #get data for the preview in the doctype .
    if isinstance(doc, str):
        doc = frappe.parse_json(doc)
    #stock finished goods data for a given head.
    fg_data = []
    #creation for P200-O and P201-O
    if group == 'rvm':
        for motor_info in [0, 1]:
            item_data, _ = _prepare_rvm_data(doc, motor_info)
            fg_data.append({
                "item_code": item_data["item_code"],
                "item_name": item_data["item_name"]
                })
    elif group == 'pump':
        #for motor possible code in item_code
        for motor_code in ["5", "7", "9", "B"]:
            #for syringe possible code in item_code
            for syringe_code in ["2","3","4","5","8","9","D"]:
                item_data, _ = _prepare_pump_data(doc,  motor_code, syringe_code)
                fg_data.append({
                    "item_code": item_data["item_code"],
                    "item_name": item_data["item_name"]
                    })
    elif group == 'pump_hv':
        #for motor possible code in item_code
        for motor_code in ["6", "8", "A", "C"]:
            #for syringe possible code in item_code
            for syringe_code in ["E", "F"]:
                item_data, _ = _prepare_pump_hv_data(doc, motor_code, syringe_code)
                fg_data.append({
                    "item_code": item_data["item_code"],
                    "item_name": item_data["item_name"]
                    })
    else :
        print("invalid group")
    
    return fg_data


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
    elif group == 'rvm':
        # Special workflow for creating the final RVM items.
        return _create_rvm_finished_goods(doc)
    elif group == 'pump':
        # Special workflow for creating the final pump items.
        return _create_pump_finished_goods(doc)
    elif group == 'pump_hv':
         return _create_pump_hv_finished_goods(doc)
    else:
        frappe.throw(_("Invalid item group specified: {0}").format(group))


# ==============================================================================
# 2. WORKFLOW ORCHESTRATORS
# Each function here manages a complete, multi-step process.
# ==============================================================================

def _create_simple_component_and_assembly(doc, group):
    """
    Orchestrator for simple parts:
    1. Prepares data for a component (e.g., Plug, Seat) and its sub-assembly.
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


def _create_rvm_finished_goods(doc):
    """Create RVM finished goods for a given head."""
    created_items = []
    
    #creation for P200-O and P201-O
    for motor_info in [0, 1]:
        item_data, bom_materials = _prepare_rvm_data(doc, motor_info)
        
        #create the finished goods item
        fg_code = _create_item_if_not_exists(item_data)

        #create the BOM for the new item
        _create_bom_for_assembly(fg_code, bom_materials)
        created_items.append(fg_code)
    
    frappe.msgprint("Successfully created RVM items {0}.")
    return created_items


def _create_pump_finished_goods(doc):
    """Create Pump finished goods for a given head and syringe."""
    created_items = []
    #for motor possible code in item_code
    for motor_code in ["5", "7", "9", "B"]:
        #for syringe possible code in item_code
        for syringe_code in ["2","3","4","5","8","9","D"]:
            item_data, bom_materials = _prepare_pump_data(doc,  motor_code, 
                                                                syringe_code)
            fg_code = _create_item_if_not_exists(item_data)
            _create_bom_for_assembly(fg_code, bom_materials)
            created_items.append(fg_code)
    return created_items

def _create_pump_hv_finished_goods(doc):
    """Create Pump HV finished goods for a given head and syringe."""
    created_items = []
    #for motor possible code in item_code
    for motor_code in ["6", "8", "A", "C"]:
        for syringe_code in ["E", "F"]:
            item_data, bom_materials = _prepare_pump_hv_data(doc, motor_code, syringe_code)
            fg_code = _create_item_if_not_exists(item_data)
            _create_bom_for_assembly(fg_code, bom_materials)
            created_items.append(fg_code)
    return created_items


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
        "item_type": "Sub-Assembly", 
        "reference_code": doc.get('head_rnd'),
        "description": doc.get('head_description'),
    }

    bom_materials = [
        {"item_code": plug_assembly_code, "qty": 1},
        {"item_code": seat_assembly_code, "qty": 1}
    ]

    return final_assembly_data, bom_materials


def _prepare_rvm_data(doc, motor_info):
    #Prepare data and BOM materials for RVM finished good.
    head_code = doc.get('head_code')
    head_rnd = doc.get("head_rnd")
    head_desc = doc.get("head_description")
    screw_type = doc.get("screw_type")
    cap_type = doc.get("cap_type")
    screw_quantity = doc.get("screw_quantity")
    X = motor_info

    #name creation
    item_code = f"4{X + 1}0{head_code[-3:]}"
    item_name = f"P20{X}-O/{head_rnd}"
    reference_code = f"P20{X}O{head_code}"

    bom_materials = [
        {"item_code": f"5{X + 1}1000", "qty": 1},
        {"item_code": head_code, "qty": 1},
        {"item_code": screw_type, "qty": screw_quantity},
        {"item_code": cap_type, "qty": 1}
    ]

    item_data = {
        "item_code": item_code,
        "item_name": item_name,
        "item_group": "Product",
        "item_type": "Finished Good",
        "reference_code": reference_code,
        #"valuation_rate": 100,
        "description": (
            f"RVM series – Industrial Microfluidic Rotary Valve<br>"
            f"<b>Version</b>: Fast<br>"
            f"______________________________________________________<br>"
            f"<b>Body</b>: P201-O<br>"
            f"{head_desc}<br>"
            f"______________________________________________________"
        )
    }
    return item_data, bom_materials


def _prepare_pump_data(doc, motor_code, syringe_code):
    """Prepare data and BOM materials for Pump finished good."""
    head_code = doc.get("head_code")
    head_rnd = doc.get("head_rnd")
    head_desc = doc.get("head_description")
    screw_type = doc.get("screw_type")
    screw_qty = doc.get("screw_quantity")
    X = motor_code
    if X == "5":
        M = 0
        N = "O"
    elif X == "7":
        M = 0 
        N = "L"
    elif X == "9":
        M = 1
        N = "O"
    else : 
        M = 1
        N = "L"
        
    syringe = SYRINGE_MAP.get(syringe_code)

    item_code = f"4{X}{syringe_code}{head_code[-3:]}"
    item_name = f"P1{M}0-{N}/{head_rnd}/{syringe['rnd']}"
    reference_code = f"P1{M}0{N}{head_code}{syringe['rnd'].replace('-', '')}"
    if N == "O":
        bom_materials = [
            {"item_code": f"5{X}1000", "qty": 1},
            {"item_code": syringe['code'], "qty": 1},
            {"item_code": head_code, "qty": 1},
            {"item_code": screw_type, "qty": screw_qty},
            {"item_code": "RVM.1204", "qty": -1},
        ]
        desc = (
            f"SPM series – Industrial Programmable Syringe Pump<br>"
            f"<b>Version</b>: SPM<br>"
            f"______________________________________________________<br>"
            f"<b>Body</b>: P1{M}0-O<br>"
            f"<b>Syringe</b>: {syringe['qty']} µl ({syringe['rnd']})<br>"
            f"{head_desc}<br>"
            f"______________________________________________________"
        )
    else:
        bom_materials = [
            {"item_code": f"5{X}1000", "qty": 1},
            {"item_code": syringe['code'], "qty": 1},
            {"item_code": head_code, "qty": 1},
            {"item_code": screw_type, "qty": screw_qty},
            {"item_code": "RVM.1204", "qty": -1},
            {"item_code": "C100", "qty": 1},
            {"item_code": "C101", "qty": 1},
        ]
        desc = (
            f"LSPone series – Laboratory Microfluidic Programmable Syringe Pump<br>"
            f"<b>Version</b>: LSPone<br>"
            f"______________________________________________________<br>"
            f"<b>Body</b>: P1{M}O-L<br>"
            f"<b>Syringe</b>: {syringe['qty']} µl ({syringe['rnd']})<br>"
            f"{head_desc}<br>"
            f"______________________________________________________"
        )

    item_data = {
        "item_code": item_code,
        "item_name": item_name,
        "item_group": "Product",
        "item_type": "Finished Good",
        "reference_code": reference_code,
        #"valuation_rate": 500,
        "description": desc
    }
    print(item_data["reference_code"])
    return item_data, bom_materials


def _prepare_pump_hv_data(doc, motor_code, syringe_code):
    """Prepare data and BOM materials for Pump HV finished good."""
    head_code = doc.get("head_code")
    head_rnd = doc.get("head_rnd")
    head_desc = doc.get("head_description")
    screw_type = doc.get("screw_type")
    screw_qty = doc.get("screw_qty")
    X = motor_code
    if X == "6":
        M = 0
        N = "O"
    elif X == "8":
        M = 0 
        N = "L"
    elif X == "A":
        M = 1
        N = "O"
    else : 
        M = 1
        N = "L"
    syringe = SYRINGE_MAP.get(syringe_code)

    item_code = f"4{X}{syringe_code}{head_code[-3:]}"
    item_name = f"P1{M}1-{N}/{head_rnd}/{syringe['rnd']}"
    reference_code = f"P1{M}1{N}{head_code}{syringe['rnd'].replace('-', '')}"

    if N == "O":
        bom_materials = [
            {"item_code": f"5{X}1000", "qty": 1},
            {"item_code": syringe["code"], "qty": 1},
            {"item_code": head_code, "qty": 1},
            {"item_code": screw_type, "qty": screw_qty},
            {"item_code": "RVM.1204", "qty": -1},
        ]
        desc = (
            f"SPM series – Industrial Programmable Syringe Pump<br>"
            f"<b>Version</b>: SPM<br>"
            f"______________________________________________________<br>"
            f"<b>Body</b>: P1{M}1-O<br>"
            f"<b>Syringe</b>: {syringe['qty']} ml ({syringe['rnd']})<br>"
            f"{head_desc}<br>"
            f"______________________________________________________"
        )
    else:
        bom_materials = [
            {"item_code": f"5{X}1000", "qty": 1},
            {"item_code": syringe['code'], "qty": 1},
            {"item_code": head_code, "qty": 1},
            {"item_code": screw_type, "qty": screw_qty},
            {"item_code": "RVM.1204", "qty": -1},
            {"item_code": "C100", "qty": 1},
            {"item_code": "C101", "qty": 1},
        ]
        desc = (
            f"LSPone series – Laboratory Microfluidic Programmable Syringe Pump<br>"
            f"<b>Version</b>: LSPone<br>"
            f"______________________________________________________<br>"
            f"<b>Body</b>: P1{M}1-L<br>"
            f"S<b>Syringe</b>: {syringe['qty']} ml ({syringe['rnd']})<br>"
            f"{head_desc}<br>"
            f"______________________________________________________"
        )

    item_data = {
        "item_code": item_code,
        "item_name": item_name,
        "item_group": "Product",
        "item_type": "Finished Good",
        "reference_code": reference_code,
        "valuation_rate": 500,
        "description": desc
    }
    return item_data, bom_materials


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


def _create_bom_for_assembly(assembly_code, materials, check_existence=True):
    """Creates a BOM in Draft state. Does not submit."""
    for material in materials:
        while not frappe.db.exists("Item", {"name": material.get("item_code")}):
            frappe.db.throw(_("Material item {0} does not exist. Cannot create BOM for {1}.").format(assembly_code))
    
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
        
