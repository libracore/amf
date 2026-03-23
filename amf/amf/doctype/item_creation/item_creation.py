# -*- coding: utf-8 -*-
# Copyright (c) 2024, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import time
import frappe
from amf.amf.utils.bom_creation import create_bom_for_assembly
from frappe import _
from frappe.model.document import Document


class ItemCreation(Document):
	pass

# --- Mappings for Description Generation ---
# These dictionaries map codes from head_name to human-readable descriptions.
valve_type_map = {
    'D': 'Distribution',      'DS': 'Distribution/Switch',
    'B': 'Bypass',            'DA': 'Distribution/Angled',
    'O': 'On/Off',            'OS': 'On/Off-Switch',
    'SA': 'Switch/Angled',    'SL': 'Sample Loop',
    'T': 'Triangle',          'M' : 'Multiplexing',
    'C': 'Check',             'S' : 'Switch'
}
material_map = {
    'C': 'PCTFE',             'P': 'PTFE',
    'U': 'UHMW-PE',           'V': 'Viton',
    'E': 'EPDM',              'S': 'Stainless Steel',
    'K': 'PEEK',              'A': 'PMMA',
}

BOM_MANAGED_GROUP_ALIASES = {
    "plug": "Plug",
    "valve seat": "Valve Seat",
    "seat": "Valve Seat",
    "valve head": "Valve Head",
    "head": "Valve Head",
}

BOM_MANAGED_PREFIXES = {
    "Plug": {
        "component": "10",
        "sub-assembly": "11",
    },
    "Valve Seat": {
        "component": "20",
        "sub-assembly": "21",
    },
    "Valve Head": {
        "component": "30",
        "sub-assembly": "30",
    },
}

RESERVED_BOM_MANAGED_PREFIXES = ("10", "11", "20", "21", "30")
MIN_BOM_MANAGED_SUFFIX = 1
MAX_BOM_MANAGED_SUFFIX = 9999


def normalize_bom_managed_group(item_group):
    normalized = BOM_MANAGED_GROUP_ALIASES.get((item_group or "").strip().lower())
    if not normalized:
        raise ValueError(_("Item group must be Plug, Valve Seat, or Valve Head."))
    return normalized


def normalize_bom_managed_variant(item_group, item_type=None, has_bom=None):
    normalized_group = normalize_bom_managed_group(item_group)
    if normalized_group == "Valve Head":
        return "sub-assembly"

    if has_bom is not None:
        if isinstance(has_bom, str):
            has_bom = has_bom.strip().lower() in ("1", "true", "yes")
        return "sub-assembly" if has_bom else "component"

    normalized_item_type = (item_type or "").strip().lower().replace("_", "-")
    if normalized_item_type in ("sub-assembly", "sub assembly"):
        return "sub-assembly"

    return "component"


def get_reserved_bom_managed_codes_for_suffix(suffix):
    return ["{0}{1}".format(prefix, suffix) for prefix in RESERVED_BOM_MANAGED_PREFIXES]


def build_bom_managed_item_code(item_group, suffix, item_type=None, has_bom=None):
    normalized_group = normalize_bom_managed_group(item_group)
    variant = normalize_bom_managed_variant(normalized_group, item_type=item_type, has_bom=has_bom)
    prefix = BOM_MANAGED_PREFIXES[normalized_group][variant]
    return "{0}{1}".format(prefix, suffix)


def get_bom_managed_family_codes(suffix):
    return {
        "plug_component": build_bom_managed_item_code("Plug", suffix, item_type="Component"),
        "plug_sub_assembly": build_bom_managed_item_code("Plug", suffix, item_type="Sub-Assembly"),
        "seat_component": build_bom_managed_item_code("Valve Seat", suffix, item_type="Component"),
        "seat_sub_assembly": build_bom_managed_item_code("Valve Seat", suffix, item_type="Sub-Assembly"),
        "head": build_bom_managed_item_code("Valve Head", suffix, item_type="Sub-Assembly"),
    }


def get_next_available_bom_managed_suffix(existing_codes):
    occupied_codes = {
        item_code for item_code in (existing_codes or [])
        if item_code and len(item_code) == 6 and item_code[:2] in RESERVED_BOM_MANAGED_PREFIXES and item_code[2:].isdigit()
    }

    highest_suffix = 0
    for item_code in occupied_codes:
        highest_suffix = max(highest_suffix, int(item_code[-4:]))

    search_limit = min(MAX_BOM_MANAGED_SUFFIX, highest_suffix + 1)
    for suffix_int in range(MIN_BOM_MANAGED_SUFFIX, search_limit + 1):
        suffix = str(suffix_int).zfill(4)
        reserved_codes = get_reserved_bom_managed_codes_for_suffix(suffix)
        if not any(code in occupied_codes for code in reserved_codes):
            return suffix

    raise ValueError(_("No free 4-digit suffix is available for Plug, Valve Seat, and Valve Head item families."))


def get_existing_bom_managed_item_codes():
    rows = frappe.db.sql(
        """
        SELECT item_code
        FROM `tabItem`
        WHERE item_code REGEXP '^(10|11|20|21|30)[0-9]{4}$'
        """,
        as_dict=True,
    )
    return [row["item_code"] for row in rows]


def get_highest_bom_managed_suffix(existing_codes=None):
    occupied_codes = existing_codes or get_existing_bom_managed_item_codes()
    suffixes = [int(item_code[-4:]) for item_code in occupied_codes if item_code and item_code[-4:].isdigit()]
    return max(suffixes) if suffixes else 0


@frappe.whitelist()
def suggest_bom_managed_item_code(item_group, item_type=None, has_bom=None):
    try:
        normalized_group = normalize_bom_managed_group(item_group)
        variant = normalize_bom_managed_variant(normalized_group, item_type=item_type, has_bom=has_bom)
        suffix = get_next_available_bom_managed_suffix(get_existing_bom_managed_item_codes())
        family_codes = get_bom_managed_family_codes(suffix)
        suggested_item_type = "Sub-Assembly" if variant == "sub-assembly" else "Component"

        return {
            "item_group": normalized_group,
            "item_type": suggested_item_type if normalized_group != "Valve Head" else "Sub-Assembly",
            "family_suffix": suffix,
            "item_code": build_bom_managed_item_code(
                normalized_group,
                suffix,
                item_type=suggested_item_type,
                has_bom=has_bom,
            ),
            "family_codes": family_codes,
            "reserved_codes": get_reserved_bom_managed_codes_for_suffix(suffix),
            "rule": _(
                "The next suffix is accepted only when 10/11/20/21/30 with the same last 4 digits are all still unused."
            ),
        }
    except ValueError as exc:
        frappe.throw(str(exc))

@frappe.whitelist()
def populate_fields(head_name):
    """
    Parses a 'head_name' string to generate related component names and a detailed description.

    Args:
        head_name (str): The input string, e.g., "V-DS-1-10-100-C-P".

    Returns:
        dict: A dictionary containing 'seat_name', 'plug_name', 'head_group', 'head_rnd', 'head_description', 'seat_mat', and 'plug_mat'.
    """

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
            # divide the head_name into parts based on hyphens
            parts = head_name.split('-')
            head_rnd = 'V-' + '-'.join(parts[1:])

            # --- seat_name Logic ---
            # 'SEAT-' followed by all parts except the last one and HV if exist.
            if len(parts) > 7:
                seat_name = 'SEAT-' + '-' .join(parts[1:6]) + '-' + parts[7]
            else:
                seat_name = 'SEAT-' + '-' .join(parts[1:6])

            # --- plug_name Logic ---
            plug_name = 'PLUG-' + '-' .join(parts[1:5]) + '-' + parts[6]
           
            # --- head_description Generation ---
            # Generate the multi-line description if the pattern is matched (at least 6 parts).
            if len(parts) >= 7:
                valve_type_code = parts[1]
                stages = parts[2]
                ports = parts[3]
                channel_code = parts[4]
                valve_material_code = parts[5]
                plug_material_code = parts[6]

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
        "seat_mat": valve_material,
        "plug_mat": plug_material,
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



        #derive expected seat and plug names
        parts = head_rnd.split('-')
        if len(parts) > 7:
            expected_seat_name = 'SEAT-' + '-' .join(parts[1:6]) + '-' + parts[7]
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
            incorrect_seat  = True
            incorrect_plug  = True
            seat_code = get_item_from_name(expected_seat_name)
            plug_code = get_item_from_name(expected_plug_name)

        else:
            bom_doc = frappe.get_doc("BOM", bom[0].name)

            if len(bom_doc.items) == 2:
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
            else:
                frappe.msgprint(_("BOM for Item: {0} does not have exactly 2 items.").format(item_code))
                incorrect_seat  = True
                incorrect_plug  = True
                seat_code = get_item_from_name(expected_seat_name)
                plug_code = get_item_from_name(expected_plug_name)
        
        #create BOM if incorrect
        if incorrect_seat or incorrect_plug:
            frappe.msgprint(_("The BOM for Item: {0} does not contain the expected Seat and Plug components. Creating new BOM").format(item_code))
            bom_materials = [   {"item_code": seat_code, "qty": 1},
                                {"item_code": plug_code, "qty": 1}]
            create_bom_for_assembly(item_code, bom_materials)

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
            filters={
                "item_name": item_name,
                "disabled": 0,
                "item_code": ["like", "_10%"],
            },
            fieldname="item_code",           
        )

        if not item_code:
            frappe.throw(f"No active item found for name '{item_name}' with matching code pattern.")
        return item_code
    
    except Exception as e:
        frappe.throw(f"Failed to retrieve item code for item name {item_name}: {e}")
        return None


@frappe.whitelist()
def get_last_item_code(*args, **kwargs):
    """
    Legacy helper kept for compatibility with older callers.
    Returns the highest occupied 4-digit suffix among the managed Plug/Seat/Head codes.
    """
    return get_highest_bom_managed_suffix()
        

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
                item_data, *_ = _prepare_pump_data(doc,  motor_code, syringe_code)
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
        frappe.throw(_("Invalid item group specified for preview: {0}").format(group))
    
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
    create_bom_for_assembly(asm_item_code, bom_materials)

    # Fetch BOM to update item valuation_rate with BOM cost
    bom = frappe.get_doc("BOM", {"item": asm_item_code, "is_default": 1})
    bom_cost = frappe.get_value("BOM", bom.name, "total_cost")
    item = frappe.get_doc("Item", asm_item_code)
    item.valuation_rate = bom_cost
    item.save()
    frappe.db.commit()

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
    create_bom_for_assembly(final_assembly_code, bom_materials)

    # Fetch BOM to update item valuation_rate with BOM cost
    bom = frappe.get_doc("BOM", {"item": final_assembly_code, "is_default": 1})
    bom_cost = frappe.get_value("BOM", bom.name, "total_cost")
    item = frappe.get_doc("Item", final_assembly_code)
    item.valuation_rate = bom_cost
    item.save()
    frappe.db.commit()

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
        create_bom_for_assembly(fg_code, bom_materials)
        created_items.append(fg_code)

        # Fetch BOM to update item valuation_rate with BOM cost
        bom = frappe.get_doc("BOM", {"item": fg_code, "is_default": 1})
        bom_cost = frappe.get_value("BOM", bom.name, "total_cost")
        item = frappe.get_doc("Item", fg_code)
        item.valuation_rate = bom_cost
        item.save()
        frappe.db.commit()
    
    frappe.msgprint("Successfully created RVM items {0}.")
    return created_items


def _create_pump_finished_goods(doc):
    """Create Pump finished goods for a given head and syringe."""
    created_items = []
    #for motor possible code in item_code
    for motor_code in ["5", "7", "9", "B"]:
        #for syringe possible code in item_code
        for syringe_code in ["2","3","4","5","8","9","D"]:
            item_data, bom_materials, scraps = _prepare_pump_data(doc,  motor_code, 
                                                                syringe_code)
            fg_code = _create_item_if_not_exists(item_data)
            create_bom_for_assembly(fg_code, bom_materials, scraps)
            created_items.append(fg_code)

            # Fetch BOM to update item valuation_rate with BOM cost
            bom = frappe.get_doc("BOM", {"item": fg_code, "is_default": 1})
            bom_cost = frappe.get_value("BOM", bom.name, "total_cost")
            item = frappe.get_doc("Item", fg_code)
            item.valuation_rate = bom_cost
            item.save()
            frappe.db.commit()

    return created_items

def _create_pump_hv_finished_goods(doc):
    """Create Pump HV finished goods for a given head and syringe."""
    created_items = []
    #for motor possible code in item_code
    for motor_code in ["6", "8", "A", "C"]:
        for syringe_code in ["E", "F"]:
            item_data, bom_materials = _prepare_pump_hv_data(doc, motor_code, syringe_code)
            fg_code = _create_item_if_not_exists(item_data)
            create_bom_for_assembly(fg_code, bom_materials)
            created_items.append(fg_code)

            # Fetch BOM to update item valuation_rate with BOM cost
            bom = frappe.get_doc("BOM", {"item": fg_code, "is_default": 1})
            bom_cost = frappe.get_value("BOM", bom.name, "total_cost")
            item = frappe.get_doc("Item", fg_code)
            item.valuation_rate = bom_cost
            item.save()
            frappe.db.commit()

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
        valuation_rate = 0.20 
        bom_materials = [
            {"item_code": base_code, "qty": 1},
            {"item_code": "SPL.3013", "qty": doc.get('plug_acc', 0)}
        ]
    else: # group == 'seat'
        base_name = doc.get('seat_name')
        base_code = doc.get('seat_code')
        item_group = "Valve Seat"
        valuation_rate = 30
        bom_materials = [
            {"item_code": base_code, "qty": 1},
            {"item_code": "SPL.3039", "qty": doc.get('seat_acc', 0)}
        ]


    if not all([base_name, base_code]):
        frappe.throw(_("Name and Code are required for {0}.").format(group))

    
    description = (
        f"<b>Item Code:</b> {base_code}<br>"
        f"<b>Item Name:</b> {base_name}<br>"
        f"<b>Item Group:</b> {item_group}<br>"
        f"<b>R&D Code:</b> {doc.get(f'{group}_rnd')}<br>"
        f"<b>Valve Type:</b> {valve_type_map.get(base_name.split('-')[1], 'Unknown')}<br>"
        f"<b>Number of Stages:</b> {base_name.split('-')[2]}<br>"
        f"<b>Number of Ports:</b> {base_name.split('-')[3]}<br>"
        f"<b>Channel Size:</b> {base_name.split('-')[4][0]}.{base_name.split('-')[4][1:]} mm<br>"
        f"<b>{item_group.split(' ')[0]} Material:</b> {material_map.get(base_name.split('-')[5], 'Unknown')}"
    )

    component_data = {
        "item_code": base_code,
        "item_name": base_name,
        "item_group": item_group,
        "item_type": "Component",
        "valuation_rate": valuation_rate,
        "reference_code": doc.get(f'{group}_rnd'),
        "reference_name": f"{base_code}: {base_name}",
        "tag_raw_mat": doc.get(f'{group}_mat'),
        "is_purchase_item": 0,
        "country_of_origin": "Switzerland",
        "item_defaults": [{
                "default_warehouse": "Main Stock - AMF21",
                # "expense_account": "4812 - Cost of materials (R&D) - AMF21",
                # "income_account": "4812 - Cost of materials (R&D) - AMF21"
            }],
        "description": description,
    }
    
    # Add drawing_item child table if drawing exists
    if doc.get(f'{group}_drawing'):
        component_data["drawing_item"] = [{
            "drawing": doc.get(f'{group}_drawing'),
            "item_code": base_code,
            "item_name": base_name,
            "reference_code": doc.get(f'{group}_rnd'),
            "version": "01",
            "revision": "01",
            "is_default": 1
        }]

    # Assembly code is derived by setting the second digit to '1'
    assembly_item_code = base_code[0] + '1' + base_code[2:]

    asm_description = (
        f"<b>Item Code:</b> {assembly_item_code}<br>"
        "------------------------------------------------------<br>"
        "SUB-ASSEMBLY<br>"
        "------------------------------------------------------<br>"
        f"<b>Item Name:</b> {base_name}<br>"
        f"<b>Item Group:</b> {item_group}<br>"
        f"<b>R&D Code:</b> {doc.get(f'{group}_rnd')}.ASM<br>"
        f"<b>Valve Type:</b> {valve_type_map.get(base_name.split('-')[1], 'Unknown')}<br>"
        f"<b>Number of Stages:</b> {base_name.split('-')[2]}<br>"
        f"<b>Number of Ports:</b> {base_name.split('-')[3]}<br>"
        f"<b>Channel Size:</b> {base_name.split('-')[4][0]}.{base_name.split('-')[4][1:]} mm<br>"
        f"<b>{item_group.split(' ')[0]} Material:</b> {material_map.get(base_name.split('-')[5], 'Unknown')}"
    )

    asm_data = {
        "item_code": assembly_item_code,
        "item_name": f"{base_name}",
        "item_group": item_group,
        "item_type": "Sub-Assembly",
        "reference_code": f"{doc.get(f'{group}_rnd')}.ASM",
        "reference_name": f"{assembly_item_code}: {base_name}",
        "is_purchase_item": 0,
        "country_of_origin": "Switzerland",
        "item_defaults": [{
                "default_warehouse": "Main Stock - AMF21",
                # "expense_account": "4812 - Cost of materials (R&D) - AMF21",
                # "income_account": "4812 - Cost of materials (R&D) - AMF21"
            }],
        "description": asm_description,
    }

    return component_data, asm_data, bom_materials


def _prepare_valve_head_data(doc):
    """Prepares data for the final Valve Head assembly."""
    head_name = doc.get('head_name')
    head_code = doc.get('head_code')
    plug_code = doc.get('plug_code') or doc.get('plug_item')
    seat_code = doc.get('seat_code') or doc.get('seat_item')

    if not all([head_name, head_code, plug_code, seat_code]):
        frappe.throw(_("Head, Plug, and Seat codes are required to build the Valve Head."))

    # CRITICAL: The BOM must use the SUB-ASSEMBLY codes, not the base component codes.description
    plug_assembly_code = plug_code[0] + '1' + plug_code[2:]
    seat_assembly_code = seat_code[0] + '1' + seat_code[2:]
    print(f"plug_assembly_code: {plug_assembly_code}, seat_assembly_code: {seat_assembly_code}")

    final_assembly_data = {
        "item_code": head_code,
        "item_name": head_name,
        "item_group": "Valve Head",
        "item_type": "Sub-Assembly", 
        "reference_code": doc.get('head_rnd'),
        "reference_name": f"{head_code}: {head_name}",
        "description": doc.get('head_description'),
        "is_purchase_item": 0,
        "country_of_origin": "Switzerland",
        "is_sales_item": 1,
        "item_defaults": [{
                "default_warehouse": "Main Stock - AMF21",
                # "expense_account": "4812 - Cost of materials (R&D) - AMF21",
                # "income_account": "4812 - Cost of materials (R&D) - AMF21"
            }],
        "weight_per_unit": 0.10,
        "weight_uom": "Kg",
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
        "reference_name": f"{item_code}: {item_name}",
        "description": (
            f"RVM series – Industrial Microfluidic Rotary Valve<br>"
            f"<b>Version</b>: Fast<br>"
            f"______________________________________________________<br>"
            f"<b>Body</b>: P201-O<br>"
            f"{head_desc}"
            f"______________________________________________________"
        ),
        "has_batch_no": 0,
        "is_purchase_item": 0,
        "country_of_origin": "Switzerland",
        "is_sales_item": 1,
        "item_defaults": [{
                "default_warehouse": "Main Stock - AMF21",
                # "expense_account": "4812 - Cost of materials (R&D) - AMF21",
                # "income_account": "4812 - Cost of materials (R&D) - AMF21"
            }],
        "weight_per_unit": 0.53,
        "weight_uom": "Kg",
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
        
    syringe_item_code = f"70{syringe_code}000"
    syringe_rnd = frappe.db.get_value("Item", syringe_item_code, "reference_code")
    syringe_qty = syringe_rnd.split('-')[1]

    item_code = f"4{X}{syringe_code}{head_code[-3:]}"
    item_name = f"P1{M}0-{N}/{head_rnd}/{syringe_rnd}"
    reference_code = f"P1{M}0{N}{head_code}{syringe_rnd.replace('-', '')}"
    if N == "O":
        bom_materials = [
            {"item_code": f"5{X}1000", "qty": 1},
            {"item_code": syringe_item_code, "qty": 1},
            {"item_code": head_code, "qty": 1},
            {"item_code": screw_type, "qty": screw_qty}
        ]
        desc = (
            f"SPM series – Industrial Programmable Syringe Pump<br>"
            f"<b>Version</b>: SPM {'HD' if M == 1 else ''}<br>"
            f"______________________________________________________<br>"
            f"<b>Body</b>: P1{M}0-O<br>"
            f"<b>Syringe</b>: {syringe_qty} µl ({syringe_rnd})<br>"
            f"{head_desc}"
            f"______________________________________________________"
        )
    else:
        bom_materials = [
            {"item_code": f"5{X}1000", "qty": 1},
            {"item_code": syringe_item_code, "qty": 1},
            {"item_code": head_code, "qty": 1},
            {"item_code": screw_type, "qty": screw_qty},
            {"item_code": "C100", "qty": 1},
            {"item_code": "C101", "qty": 1}
        ]
        desc = (
            f"LSPone series – Laboratory Microfluidic Programmable Syringe Pump<br>"
            f"<b>Version</b>: LSPone {'HD' if M == 1 else ''}<br>"
            f"______________________________________________________<br>"
            f"<b>Body</b>: P1{M}O-L<br>"
            f"<b>Syringe</b>: {syringe_qty} µl ({syringe_rnd})<br>"
            f"{head_desc}"
            f"______________________________________________________"
        )

    item_data = {
        "item_code": item_code,
        "item_name": item_name,
        "item_group": "Product",
        "item_type": "Finished Good",
        "reference_code": reference_code,
        "reference_name": f"{item_code}: {item_name}",
        "description": desc,
        "has_batch_no": 0,
        "is_purchase_item": 0,
        "country_of_origin": "Switzerland",
        "is_sales_item": 1,
        "item_defaults": [{
                "default_warehouse": "Main Stock - AMF21",
                # "expense_account": "4812 - Cost of materials (R&D) - AMF21",
                # "income_account": "4812 - Cost of materials (R&D) - AMF21"
            }],
        "weight_per_unit": 2.18,
        "weight_uom": "Kg",
    }
    scraps = [
            {"item_code": "RVM.1204", "qty": 1}
        ]
    
    return item_data, bom_materials, scraps


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
    
    syringe_item_code = f"70{syringe_code}000"
    syringe_rnd = frappe.db.get_value("Item", syringe_item_code, "reference_code")
    syringe_qty = syringe_rnd.split('-')[1]

    item_code = f"4{X}{syringe_code}{head_code[-3:]}"
    item_name = f"P1{M}1-{N}/{head_rnd}/{syringe_rnd}"
    reference_code = f"P1{M}1{N}{head_code}{syringe_rnd.replace('-', '')}"

    if N == "O":
        bom_materials = [
            {"item_code": f"5{X}1000", "qty": 1},
            {"item_code": syringe_item_code, "qty": 1},
            {"item_code": head_code, "qty": 1},
            {"item_code": screw_type, "qty": screw_qty},
        ]
        desc = (
            f"SPM series – Industrial Programmable Syringe Pump<br>"
            f"<b>Version</b>: SPM+ {'HD' if M == 1 else ''}<br>"
            f"______________________________________________________<br>"
            f"<b>Body</b>: P1{M}1-O<br>"
            f"<b>Syringe</b>: {syringe_qty} ml ({syringe_rnd})<br>"
            f"{head_desc}"
            f"______________________________________________________"
        )
    else:
        bom_materials = [
            {"item_code": f"5{X}1000", "qty": 1},
            {"item_code": syringe_item_code, "qty": 1},
            {"item_code": head_code, "qty": 1},
            {"item_code": screw_type, "qty": screw_qty},
            {"item_code": "C100", "qty": 1},
            {"item_code": "C101", "qty": 1},
        ]
        desc = (
            f"LSPone series – Laboratory Microfluidic Programmable Syringe Pump<br>"
            f"<b>Version</b>: LSPone+ {'HD' if M == 1 else ''}<br>"
            f"______________________________________________________<br>"
            f"<b>Body</b>: P1{M}1-L<br>"
            f"S<b>Syringe</b>: {syringe_qty} ml ({syringe_rnd})<br>"
            f"{head_desc}"
            f"______________________________________________________"
        )

    item_data = {
        "item_code": item_code,
        "item_name": item_name,
        "item_group": "Product",
        "item_type": "Finished Good",
        "reference_code": reference_code,
        "reference_name": f"{item_code}: {item_name}",
        "description": desc,
        "has_batch_no": 0,
        "is_purchase_item": 0,
        "country_of_origin": "Switzerland",
        "is_sales_item": 1,
        "item_defaults": [{
                "default_warehouse": "Main Stock - AMF21",
                # "expense_account": "4812 - Cost of materials (R&D) - AMF21",
                # "income_account": "4812 - Cost of materials (R&D) - AMF21"
            }],
        "weight_per_unit": 2.18,
        "weight_uom": "Kg",
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


        
