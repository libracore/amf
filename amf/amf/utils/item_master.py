import re
import time
import frappe

def fetch_items(item_group, disabled=False):
    """Fetch all enabled items from a specific item group."""
    return frappe.get_all('Item', fields=['name', 'item_code', 'item_name'],
                          filters={'item_group': item_group, 'disabled': disabled})

def create_new_items(items, start_code=300001):
    """Create new items based on existing ones with modifications."""
    for item in items:
        new_item = frappe.get_doc({
            'doctype': 'Item',
            'item_code': str(start_code),
            'item_name': f"{item['item_code']}-ASM",
            'item_group': 'Valve Head',
            'stock_uom': 'Nos',
            'is_stock_item': True,
            'include_item_in_manufacturing': True,
            'default_material_request_type': 'Manufacture',
            'description': f"Valve Head {item['item_code']}-ASM Assembly w/ Components",
            'item_defaults': [{
                    'company': 'Advanced Microfluidics SA',
                    'default_warehouse': 'Assemblies - AMF21'
                }],
            'disabled': False
        })
        new_item.insert(ignore_permissions=True)
        frappe.db.commit()
        start_code += 1

    print("All new items have been created successfully.")
    return None

def process_item_codes(items):
    """Process item codes to split and further process parts."""
    processed_items = []
    for item in items:
        parts = item['item_code'].split('-')
        if len(parts) < 3:
            continue
        processed_parts = [part for sub in parts for part in sub.split()]
        processed_items.append({'item_code': item['item_code'], 'item_name': item['item_name'], 'split_parts': processed_parts})
    return processed_items

def print_matching_items(processed_items, code_group, print_mode):
    """Print matching plugs and seats for processed items."""
    matching_items = get_matching_plugs_seats(processed_items)
    for match in matching_items:
        if print_mode:
            print("Valve Head: ", match['valve_head'])
            print("Matching Plugs: ", [plug['item_name'] for plug in match['plug_items']])
            print("Matching Seats: ", [seat['item_name'] for seat in match['seat_items']])
            # Create missing Plugs and Seats
        if not match['plug_items']:  # No matching plugs found
            create_item('Plug', code_group['Plug'], match['plug_pattern'])
            print(f"Created missing plug: P-{match['plug_pattern']}")
            code_group['Plug'] += 1
        if not match['seat_items']:  # No matching seats found
            create_item('Valve Seat', code_group['Valve Seat'], match['seat_pattern'])
            print(f"Created missing seat: S-{match['seat_pattern']}")
            code_group['Valve Seat'] += 1

def create_item(item_group, code_group, item_pattern):
    """Create an item in the specified item group with the given pattern."""
    prefix = 'P' if item_group == 'Plug' else 'S'
    new_item_name = f"{prefix}-{item_pattern}"
    accessory_qty = extract_bom_qty(new_item_name) if item_group == 'Plug' else 2
    new_item = frappe.get_doc({
        'doctype': 'Item',
        'item_code': str(code_group),
        'item_name': new_item_name,
        'item_group': item_group,
        'stock_uom': 'Nos',
        'is_stock_item': True,
        'include_item_in_manufacturing': True,
        'default_material_request_type': 'Manufacture',
        'description': f"{item_group} {new_item_name} Assembly w/ Components",
        'item_defaults': [{
            'company': 'Advanced Microfluidics SA',
            'default_warehouse': 'Assemblies - AMF21'
        }],
        'disabled': False
    })
    new_item.insert(ignore_permissions=True)

    # # Prepare the BOM
    # new_bom = frappe.get_doc({
    #     'doctype': 'BOM',
    #     'item': str(code_group),
    #     'quantity': 1,
    #     'is_default': 1,
    #     'is_active': 1,
    #     'items': [
    #         {'item_code': str(code_group), 'qty': 1},
    #         {'item_code': 'SPL.3013' if item_group == 'Plug' else 'SPL.3039', 'qty': accessory_qty},
    #     ],
    # })
    # new_bom.insert(ignore_permissions=True)
    # new_bom.submit()

    frappe.db.commit()

def fetch_items_with_group(item_groups):
    """Fetch all items from specified item groups."""
    return frappe.get_all('Item', fields=['name', 'item_code', 'item_name', 'item_group'],
                          filters={'item_group': ['in', item_groups], 'disabled': False})

def get_matching_plugs_seats(processed_items):
    """Match plugs and seats based on processed items' split parts."""
    # Fetch all plugs and seats
    all_plugs_seats = fetch_items_with_group(['Plug', 'Valve Seat'])
    plugs = [item for item in all_plugs_seats if item['item_group'] == 'Plug']
    seats = [item for item in all_plugs_seats if item['item_group'] == 'Valve Seat']

    matched_items = []

    for item in processed_items:
        if len(item['split_parts']) >= 7:
            pattern_plug = "{}-{}-{}-{}-{}-ASM".format(
                item['split_parts'][1], item['split_parts'][2], item['split_parts'][3],
                item['split_parts'][4], item['split_parts'][6]
            )
            pattern_seat = "{}-{}-{}-{}-{}-ASM".format(
                item['split_parts'][1], item['split_parts'][2], item['split_parts'][3],
                item['split_parts'][4], item['split_parts'][5]
            )

            # Filter plugs and seats
            filtered_plugs = [plug for plug in plugs if pattern_plug in plug['item_name']]
            filtered_seats = [seat for seat in seats if pattern_seat in seat['item_name']]

            matched_items.append({
                'valve_head': item['item_code'],
                'plug_items': filtered_plugs,
                'seat_items': filtered_seats,
                'plug_pattern': pattern_plug,
                'seat_pattern': pattern_seat
            })

    return matched_items

# MASTER METHOD
@frappe.whitelist()
def get_valve_head_items(creation_mode=True, print_mode=True):
    items = fetch_items('Valve Head')
    if creation_mode:
        code_group = create_new_items_and_boms()
        create_new_items(items)
    processed_items = process_item_codes(items)
    print_matching_items(processed_items, code_group, print_mode)


def create_new_items_and_boms():
    # Define the starting point for the new item codes
    item_code_start = {
        'Plug': 100001,
        'Valve Seat': 200001  # Starting code for Valve Seat items
    }
    
    # Fetch all items from the "Plug" and "Valve Seat" item groups
    item_groups = {
        'Plug': frappe.get_all('Item', filters={'item_group': 'Plug', 'disabled': False}, fields=['name', 'item_name']),
        'Valve Seat': frappe.get_all('Item', filters={'item_group': 'Valve Seat', 'disabled': False}, fields=['name', 'item_name'])
    }
    
    for group_name, items in item_groups.items():
        for item in items:
            # Extract the item code suffix
            accessory_qty = extract_bom_qty(item['item_name']) if group_name == 'Plug' else 2

            # Prepare the new item code and name
            parts = item['item_name'].split('-')
            if len(parts) < 3:
                continue
            processed_parts = [part for part in parts if part]
            prefix = 'P' if group_name == 'Plug' else 'S'
            new_item_name = f"{prefix}-{'-'.join(processed_parts[1:6])}-ASM"

            # Create the new Item
            new_item = frappe.get_doc({
                'doctype': 'Item',
                'item_code': str(item_code_start[group_name]),
                'item_name': new_item_name,
                'stock_uom': 'Nos',
                'is_stock_item': True,
                'include_item_in_manufacturing': True,
                'default_material_request_type': 'Manufacture',
                'description': f'{group_name} {new_item_name} Assembly w/ Components',
                'item_group': group_name,
                'item_defaults': [{
                    'company': 'Advanced Microfluidics SA',
                    'default_warehouse': 'Assemblies - AMF21'
                }],
            })
            new_item.insert(ignore_permissions=True)

            # Prepare the BOM
            new_bom = frappe.get_doc({
                'doctype': 'BOM',
                'item': str(item_code_start[group_name]),
                'quantity': 1,
                'is_default': 1,
                'is_active': 1,
                'items': [
                    {'item_code': item['name'], 'qty': 1},
                    {'item_code': 'SPL.3013' if group_name == 'Plug' else 'SPL.3039', 'qty': accessory_qty},
                ],
            })
            new_bom.insert(ignore_permissions=True)
            new_bom.submit()

            # Increment the item code for the next new item
            item_code_start[group_name] += 1

    # Commit the transaction
    frappe.db.commit()
    return item_code_start

# Function to extract quantity from the item name
def extract_bom_qty(item_name):
    try:
        parts = item_name.split('-')
        if len(parts) < 4:
            raise ValueError(f"Expected at least 4 parts in the item name, got {len(parts)} in '{item_name}'")

        second_number = parts[3]
        # Validate that the extracted part is a digit
        if not second_number.isdigit():
            raise ValueError(f"Extracted part '{second_number}' is not a digit in '{item_name}'")

        return int(second_number)  # Convert to integer for return

    except ValueError as e:
        print(f"Error processing item name '{item_name}': {e}")
        return None  # Return None or a suitable default/error value

def fetch_items_to_delete():
    """Fetch items from specified groups with an '-ASM' suffix."""
    item_groups = ['Plug', 'Valve Seat', 'Valve Head']
    items = frappe.get_all('Item', 
                           filters={'item_name': ['like', '%-ASM%'], 
                                    'item_group': ['in', item_groups]},
                           fields=['name', 'item_code'])
    return items

def cancel_and_delete_boms(item_name):
    """Cancel and delete BOMs associated with a given item."""
    associated_boms = frappe.get_all('BOM', 
                                     filters={'item': item_name},
                                     fields=['name', 'docstatus'])
    for bom in associated_boms:
        if bom['docstatus'] == 1:  # BOM is submitted
            bom_doc = frappe.get_doc('BOM', bom['name'])
            bom_doc.cancel()
        frappe.delete_doc('BOM', bom['name'], force=1)

@frappe.whitelist()
def delete_items_asm():
    """Delete items and their associated BOMs for specific item groups."""
    try:
        items_to_delete = fetch_items_to_delete()
        for item in items_to_delete:
            cancel_and_delete_boms(item['name'])
            frappe.delete_doc('Item', item['name'], force=1)

        frappe.db.commit()
        print("Items and associated BOMs have been deleted successfully.")

    except Exception as e:
        frappe.db.rollback()
        print(f"An error occurred: {e}")