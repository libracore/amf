import datetime
import re
from amf.amf.utils.utilities import update_log_entry
import frappe
import time

from frappe.exceptions import ValidationError

# Global Variables
PLUG = 1
SEAT = 2
HEAD = 3
ref_code_plug = 100001
ref_code_plug_asm = 110001
ref_code_seat = 200001
ref_code_seat_asm = 210001
ref_code_head = 300001
ref_code_head_asm = 310001

log_id = None

@frappe.whitelist()
def call_refactor(number):
    if number == 1:
        refactor_items()
    elif number == 2:
        refactor_items()
        create_raw_mat_bom()
    elif number == 3:
        refactor_items()
        create_raw_mat_bom()
        create_bom_for_items()
    elif number == 4:
        refactor_items()
        create_raw_mat_bom()
        create_bom_for_items()    
        update_bom_list()
    elif number == 5:
        refactor_items()
        create_raw_mat_bom()
        create_bom_for_items()    
        new_bom_valve_head()
        update_bom_list() 
    else:
        print("Error in choosing number of methods to call.")
    return None

@frappe.whitelist()
def refactor_items():
    create_log_entry("Starting amf.amf.utils.item_master3 method...", "refactor_items()")
    # Fetch items in the 'Plug' item group
    #items = frappe.get_all('Item', filters={'item_group': 'Valve Head', 'disabled': '0'}, fields=['name', 'item_code', 'item_name', 'item_group'])
    items = frappe.get_all('Item', filters={'item_group': ['in', ['Plug', 'Valve Seat', 'Valve Head']],
                                            'disabled': '0'},
                                   fields=['name', 'item_code', 'item_name', 'item_group'])
    
    for item in items:
        item_info = get_item_info(item)

        if item_info is None and item['item_group'] != 'Valve Head':
            continue

        name = item['name']
        old_item_code = item['item_code']
        item_name = item['item_name']
        item_group = item['item_group']

        # Determine the reference code based on the item group
        if item_group == 'Plug':
            ref_item_code = ref_code_plug
        elif item_group == 'Valve Seat':
            ref_item_code = ref_code_seat
        elif item_group == 'Valve Head':
            ref_item_code = ref_code_head
            match = re.search(r'-(\w{1,2})-', item_name)
            if match:
                index = match.start(1)
                # Extract the part after the single or double letters
                tail = item_name[index:]
                # Define the new prefix
                new_prefix = "VALVE HEAD-"
                # Combine new prefix with the tail
                item_name = f"{new_prefix}{tail}"

        reference_name = f"{old_item_code}: {item_name.upper()}"
        if item_group == 'Valve Head':
            reference_name = f"{ref_item_code}: {old_item_code}"
        
        description = f"""<div><strong>Code</strong>: {ref_item_code}</div>
                          <div><strong>Reference</strong>: {old_item_code}</div>
                          <div><strong>Name</strong>: {item_name.upper()}</div>
                          <div><strong>Group</strong>: {item_group}</div>"""
        
        # Update the item
        frappe.db.set_value('Item', name, 'item_code', ref_item_code)
        frappe.db.set_value('Item', name, 'item_name', item_name.upper())
        frappe.db.set_value('Item', name, 'reference_name', reference_name)
        frappe.db.set_value('Item', name, 'reference_code', old_item_code)
        frappe.db.set_value('Item', name, 'description', description)
        frappe.db.set_value('Item', name, 'has_batch_no', 1)
        frappe.db.set_value('Item', name, 'create_new_batch', 0)
        frappe.db.set_value('Item', name, 'sales_uom', 'Nos')
        frappe.db.set_value('Item', name, 'country_of_origin', 'Switzerland')
        if item_group == 'Valve Head':
            frappe.db.set_value('Item', name, 'variant_of', '')
            frappe.db.set_value('Item', name, 'customs_tariff_number', '8487.9000')
            frappe.db.set_value('Item', name, 'weight_per_unit', '0.10')
            frappe.db.set_value('Item', name, 'weight_uom', 'Kg')

        frappe.rename_doc('Item', name, f"{ref_item_code}", merge=False)
        
        if item_group != 'Valve Head':
            create_new_item(item, old_item_code)

        try:
            update_log_entry(log_id, f"Processing item {ref_item_code} with code {old_item_code}")
        except Exception as e:
            update_log_entry(log_id, f"Error creating BOM for item: {str(name)} - {str(e)}")
        
        if item_group == 'Plug':
            increment_code(PLUG)
        elif item_group == 'Valve Seat':
            increment_code(SEAT)
        elif item_group == 'Valve Head':
            increment_code(HEAD)

    frappe.db.commit()
    update_log_entry(log_id, "Item list refactored successfully.")
    return None

def create_new_item(item, old_item_code):
    """Create an item in the specified item group with the given pattern."""
    # Determine the reference code based on the item group
    custom_number = ''
    if item['item_group'] == 'Plug':
        ref_item_code = ref_code_plug
        ref_item_code_asm = ref_code_plug_asm
        description = f"""<div><strong>Code</strong>: {ref_item_code_asm}</div>
                          <div><strong>Reference</strong>: {old_item_code}.ASM</div>
                          <div><strong>Name</strong>: {item['item_name']}</div>
                          <div><strong>Group</strong>: {item['item_group']}</div>
                          <div><strong>Components</strong>: {ref_item_code} + SPL.3013</div>"""
    elif item['item_group'] == 'Valve Seat':
        ref_item_code = ref_code_seat
        ref_item_code_asm = ref_code_seat_asm
        description = f"""<div><strong>Code</strong>: {ref_item_code_asm}</div>
                          <div><strong>Reference</strong>: {old_item_code}.ASM</div>
                          <div><strong>Name</strong>: {item['item_name']}</div>
                          <div><strong>Group</strong>: {item['item_group']}</div>
                          <div><strong>Components</strong>: {ref_item_code} + SPL.3039</div>"""
    elif item['item_group'] == 'Valve Head':
        custom_number = '8487.9000'

    new_item = {
        'doctype': 'Item',
        'item_code': f"{ref_item_code_asm}",
        'item_name': item['item_name'],
        'item_group': item['item_group'],
        'reference_code': f"{old_item_code}.ASM",
        'reference_name': f"{old_item_code}.ASM: {item['item_name']}",
        'has_batch_no': 0,
        'stock_uom': 'Nos',
        'is_stock_item': True,
        'include_item_in_manufacturing': True,
        'default_material_request_type': 'Manufacture',
        'description': description,
        'item_defaults': [{
            'company': 'Advanced Microfluidics SA',
            'default_warehouse': 'Assemblies - AMF21',
            'expense_account': '4009 - Cost of material: Valve Head - AMF21',
            'income_account': '3007 - Valve Head sales revenue - AMF21'
        }],
        'disabled': False,
        'country_of_origin': 'Switzerland',
        'sales_uom': 'Nos',
        'customs_tariff_number': custom_number,
    }
    create_document('Item', new_item)
    
    try:
        update_log_entry(log_id, f"BOM created successfully for item: {ref_item_code_asm}")
    except Exception as e:
        update_log_entry(log_id, f"Error creating BOM for item: {ref_item_code_asm} - {str(e)}")
    
    commit_transaction()
    return None

@frappe.whitelist()
def new_bom_valve_head():
    create_log_entry("Starting amf.amf.utils.item_master3 method...", "create_bom_head()")
    
    valve_head_items = frappe.get_all('Item', filters={'item_group': 'Valve Head', 'disabled': '0'}, fields=['name', 'reference_code'])

    for item in valve_head_items:
        item_code = item['name']
        reference_code = item['reference_code']
        disable_existing_boms(item_code)
        
        # Fetch matching patterns from 'Plug' and 'Valve Seat' groups
        matching_plug, matching_seat = match_pattern(reference_code)

        if matching_plug and matching_seat:
            # Create new BOM (assuming you have a function to create BOM)
            create_new_bom(item_code, matching_plug, matching_seat)
        else:
            update_log_entry(log_id, f"No matching pattern found for {reference_code}")
    
    update_log_entry(log_id, f"Done creating new BOM for Valve Heads.")           
    return None

def match_pattern(reference_code):
    # Extract the last 6 elements of the reference code pattern
    try:
        pattern = '-'.join(reference_code.split('-')[-6:-2])
        head_seat_suffix = reference_code.split('-')[-2]
        head_plug_suffix = reference_code.split('-')[-1]
        update_log_entry(log_id, f"Valve Head main pattern: {pattern} with suffix: {head_seat_suffix} and {head_plug_suffix}")
    except Exception as e:
        pattern = None
        head_seat_suffix = None
        head_plug_suffix = None
        update_log_entry(log_id, f"Error split Valve Head for item: {reference_code} - {str(e)}")
    
    # Construct the patterns to match
    plug_pattern = f"%{pattern}-{head_plug_suffix}%"
    seat_pattern = f"%{pattern}-{head_seat_suffix}%"
    
    # Fetch items in 'Plug' and 'Valve Seat' groups
    plug = frappe.get_all('Item', filters={'item_group': 'Plug', 'disabled': '0', 'item_code': ['like', '_1%'], 'item_name': ['like', plug_pattern]}, fields=['name', 'item_name'])
    seat = frappe.get_all('Item', filters={'item_group': 'Valve Seat', 'disabled': '0', 'item_code': ['like', '_1%'], 'item_name': ['like', seat_pattern]}, fields=['name', 'item_name']) 
    
    matching_plug = plug[0]['name'] if plug else None
    matching_seat = seat[0]['name'] if seat else None
    
    update_log_entry(log_id, f"Plug / Seat: {matching_plug} / {matching_seat}")
    return matching_plug, matching_seat

def create_new_bom(item_code, plug_code, seat_code):
    update_log_entry(log_id, f"Creating new BOM for item {item_code} with plug {plug_code} and seat {seat_code}")
    
    new_bom = frappe.get_doc({
        'doctype': 'BOM',
        'item': item_code,
        'is_active': 1,
        'is_default': 1,
        'items': [
            {'item_code': plug_code, 'qty': 1},
            {'item_code': seat_code, 'qty': 1},
        ],
        # Add additional BOM fields here as required
    })
    new_bom.insert()
    new_bom.submit()
    commit_transaction()
    
    update_log_entry(log_id, f"New BOM created for item {item_code} with plug {plug_code} and seat {seat_code}")
    return None

@frappe.whitelist()
def create_raw_mat_bom():
    # Create initial log entry
    create_log_entry("Starting amf.amf.utils.item_master3 method...", "create_raw_mat_bom()")
    code_raw = '_0%'
    items = get_items_with_specific_code(code_raw)

    for item in items:
        create_raw_bom(item)
    
    update_log_entry(log_id, f">>> End of create_raw_mat_bom() <<<")
    return None 

def create_raw_bom(item):
    item_info = get_item_info(item)

    ref_item_code = item['item_code']
    if item['item_group'] == 'Plug':
        w_station = 'EMCOTURN 45'
        time_in_mins = 6
        qty_raw = 0.02
        if 'P' in item_info['raw_mat']:
            raw_mat = ['MAT.1007', 'MAT.1001']
        elif 'U' in item_info['raw_mat']:
            raw_mat = ['MAT.1003']
        else:
            raw_mat = []
    elif item['item_group'] == 'Valve Seat':
        w_station = 'CMZ TTS 46'
        time_in_mins = 12
        qty_raw = 0.03
        if item_info['raw_mat'] == 'C' and item_info['port'] < 10:
            raw_mat = ['MAT.1012','MAT.1006','MAT.1002']
        elif item_info['raw_mat'] == 'C' and item_info['port'] >= 10:
            raw_mat = ['MAT.1013','MAT.1008','MAT.1005','MAT.1004']
        elif item_info['raw_mat'] == 'K' and item_info['port'] < 10:
            raw_mat = ['MAT.1009']
        elif item_info['raw_mat'] == 'K' and item_info['port'] >= 10:
            raw_mat = ['MAT.1010']
        elif item_info['raw_mat'] == 'P':
            raw_mat = ['MAT.1007']
        elif item_info['raw_mat'] == 'A':
            raw_mat = ['MAT.1011']
        else:
            raw_mat = []
        
        if item_info['raw_mat'] == 'C' and item_info['port'] == 8 and item_info['size'] == 100:
            raw_mat = ['MAT.1013','MAT.1008','MAT.1005','MAT.1004']
        
        
    disable_existing_boms(ref_item_code)
    for mat in raw_mat:
        new_bom = {
            'doctype': 'BOM',
            'item': ref_item_code,
            'quantity': 1,
            'is_default': 1,
            'is_active': 1,
            'with_operations': 1,
            'operations':
                    [
                        {'operation': 'CNC Machining', 'workstation': w_station, 'time_in_mins': time_in_mins, 'operating_cost': time_in_mins},
                    ],
            'items':
                    [
                        {'item_code': mat, 'qty': qty_raw},
                    ],
        }    

        try:
            create_document('BOM', new_bom)
        except Exception as e:
            print(f"An error occurred: {str(e)}")

        try:
            update_log_entry(log_id, f"BOM created successfully for item: {ref_item_code}")
        except Exception as e:
            update_log_entry(log_id, f"Error creating BOM for item: {ref_item_code} - {str(e)}")

        commit_transaction()

    return None  

@frappe.whitelist()
def create_bom_for_items():
    # Create initial log entry
    create_log_entry("Starting amf.amf.utils.item_master3 method...", "create_bom_for_items()")
    code_asm = '_1%'
    items = get_items_with_specific_code(code_asm)
    
    for item in items:
        create_bom_head(item)

    update_log_entry(log_id, f">>> End of create_bom_for_items() <<<")
    return None

def create_bom_head(item):
    item_info = get_item_info(item)
    accessory_qty = item_info['port'] if item['item_group'] == 'Plug' else 2

    ref_item_code_asm = item['item_code']
    ref_item_code = ref_item_code_asm[0] + '0' + ref_item_code_asm[2:]
    
    bom_items = [
        {'item_code': ref_item_code, 'qty': 1},
        {'item_code': 'SPL.3013' if item['item_group'] == 'Plug' else 'SPL.3039', 'qty': accessory_qty},
    ]
    
    # Add an additional row for 'Valve Seat'
    if item['item_group'] == 'Valve Seat':
        bom_items.append({'item_code': 'RVM.1204', 'qty': 1})

    new_bom = {
        'doctype': 'BOM',
        'item': ref_item_code_asm,
        'quantity': 1,
        'is_default': 1,
        'is_active': 1,
        'items': bom_items,
    }

    disable_existing_boms(ref_item_code_asm)

    try:
        create_document('BOM', new_bom)
    except Exception as e:
        print(f"An error occurred: {str(e)}")

    try:
        update_log_entry(log_id, f"BOM created successfully for item: {ref_item_code_asm}")
    except Exception as e:
        update_log_entry(log_id, f"Error creating BOM for item: {ref_item_code_asm} - {str(e)}")
    
    commit_transaction()
    return None

def disable_existing_boms(item_code):
    # Fetch existing BOMs associated with the item
    boms = frappe.get_all(
        'BOM',
        filters={'item': item_code, 'is_active': 1},
        fields=['name']
    )
    
    for bom in boms:
        # Disable the BOM
        frappe.db.set_value('BOM', bom['name'], 'is_active', 0)
        frappe.db.set_value('BOM', bom['name'], 'is_default', 0)
    
    frappe.db.commit()
    return None

# Utility Functions
def get_items_with_specific_code(code):
    # Fetch items with item_code 6 digits long and the second digit is 1
    items = frappe.get_all(
        'Item',
        filters={
            'item_group': ['in', ['Plug', 'Valve Seat']],
            'item_code': ['like', code],
        },
        fields=['name', 'item_code', 'item_group', 'item_name']
    )
    return items

def get_item_info(item):
    if item['item_group'] == 'Valve Head':
        item_name = item['item_code']
    else:
        item_name = item['item_name']
    # Split the item_name by dashes
    info_parts = item_name.split('-')

    # Check if any element is empty or None
    if len(info_parts) < 6:
        return None
    
    # Create a dictionary to store the information
    item_info = {}

    # Map each part to a specific key in the dictionary
    keys = ['group', 'type', 'channel', 'port', 'size', 'raw_mat']
    int_keys = ['channel', 'port', 'size']

    for i, part in enumerate(info_parts):
        if i < len(keys):
            key = keys[i]
            if key in int_keys:
                try:
                    item_info[key] = int(part)
                except ValueError:
                    update_log_entry(log_id, f"Int Conversion Error for {item}")
                    return None  # Return None if conversion to integer fails
            else:
                item_info[key] = part

    # Return the dictionary containing the item information
    return item_info

def increment_code(code):
    if code == 1:
            global ref_code_plug
            ref_code_plug+=1
            global ref_code_plug_asm
            ref_code_plug_asm+=1
    elif code == 2:
            global ref_code_seat
            ref_code_seat+=1
            global ref_code_seat_asm
            ref_code_seat_asm+=1
    elif code == 3:
            global ref_code_head
            ref_code_head+=1
            global ref_code_head_asm
            ref_code_head_asm+=1
    return None

def create_document(doc_type, data):
    """Create and insert a new document in the Frappe database."""
    doc = frappe.get_doc({"doctype": doc_type, **data})
    doc.insert(ignore_permissions=True)
    if doc_type=='BOM':
        doc.submit()
    return doc

def commit_transaction():
    """Commit the current transaction to the database."""
    frappe.db.commit()
    time.sleep(1)
    
# def update_log_entry(log_id, message):
#     """ Update an existing log entry with additional messages """
#     log = frappe.get_doc("Log Entry", log_id)
#     log.message += "\n" + message  # Append new information
#     log.save(ignore_permissions=True)
    
def create_log_entry(message, category):
    """ Create a new log entry and return its ID """
    log_doc = frappe.get_doc({
        "doctype": "Log Entry",
        "timestamp": datetime.datetime.now(),
        "category": category,
        "message": message
    })
    log_doc.insert(ignore_permissions=True)
    frappe.db.commit()
    global log_id
    log_id = log_doc.name
    print(log_id)
    return None

"""====================================================================="""
def update_bom_list():
    create_log_entry("Starting amf.amf.utils.item_master3 method...", "update_bom_list()")
    # Fetch all items with active BOMs
    items_with_bom = frappe.get_all(
        'BOM',
        filters={'is_active': 1},
        fields=['item'],
        distinct=True
    )
    
    # Iterate through each item and update the fields
    for item in items_with_bom:
        item_code = item['item']
        if frappe.db.get_value('Item', item_code, 'disabled'):
            continue
        remove_old_company_defaults(item_code)
        update_item_bom_fields(item_code)
    
    frappe.db.commit()
    update_log_entry(log_id, f"BOM list updated for all items with active BOMs.")

def update_item_bom_fields(item_code):
    # Fetch all BOMs for the item
    boms = frappe.get_all(
        'BOM',
        filters={'item': item_code, 'is_active': 1, 'is_default': 1},
        fields=['name', 'total_cost', 'is_default']
    )
    if not boms:
        print(f"No active BOMs found for item {item_code}")
        return
    
    default_bom = None
    total_cost = 0
    bom_items = []

    for bom in boms:
        bom_name = bom['name']  # Ensure this is treated as a string
        total_cost = bom['total_cost']
        
        # Fetch BOM items for the current BOM
        bom_items = frappe.get_all(
            'BOM Item',
            filters={'parent': bom_name},
            fields=['item_code', 'item_name', 'qty', 'rate', 'amount', 'uom', 'description']
        )

        # Since we are fetching the default BOM, we assign it to default_bom
        if bom['is_default']:
            default_bom = bom_name
        
        try:
            frappe.get_doc("BOM", bom).update_cost(from_child_bom=False)
        except Exception as error:
            print("An error occurred:", error)

    # Update the item
    item_doc = frappe.get_doc('Item', item_code)
    item_doc.item_default_bom = default_bom
    item_doc.bom_cost = total_cost
    item_doc.set('bom_table', [])
    for bom_item in bom_items:
        item_doc.append('bom_table', bom_item)

    # Save the updated item document
    try:
        item_doc.save()
    except Exception as error:
        update_log_entry(log_id, f"An error occurred: {error}")

def remove_old_company_defaults(item_code):
    try:
        # Fetch the item document using the item_code
        item = frappe.get_doc("Item", item_code)
        
        # Filter out the 'item_defaults' child table rows where the company is 'Advanced Microfluidics SA (OLD)'
        item_defaults_to_keep = [
            row for row in item.item_defaults if row.company != "Advanced Microfluidics SA (OLD)"
        ]

        # Check if any rows were removed
        if len(item_defaults_to_keep) != len(item.item_defaults):
            # Assign the filtered list back to the item
            item.item_defaults = item_defaults_to_keep
            
            # Save the item document
            item.save()
            frappe.db.commit()
            update_log_entry(log_id, f"Removed old company defaults for item: {item_code}")
    except frappe.DoesNotExistError:
        update_log_entry(log_id, f"Item with code {item_code} does not exist.")
    except Exception as e:
        update_log_entry(log_id, f"An error occurred: {str(e)}")