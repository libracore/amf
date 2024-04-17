import frappe

# Global Variables
item_code_plug = 100001
item_code_seat = 200001
item_code_head = 300001

# Utility Functions
def increment_code(code):
    if code == 1:
            global item_code_plug
            item_code_plug+=1
    elif code == 2:
            global item_code_seat
            item_code_seat+=1
    elif code == 3:
            global item_code_head
            item_code_head+=1
    return None

def log_info(message):
    """Log information using Frappe's logging mechanism."""
    frappe.logger().info(message)

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

# Item Fetching Functions
def fetch_items(item_group, disabled=False):
    """Fetch all items from a specific item group with a disabled flag."""
    fields = ['name', 'item_code', 'item_name']
    filters = {'item_group': item_group, 'disabled': disabled}
    return frappe.get_all('Item', fields=fields, filters=filters)

def fetch_items_with_group(item_groups):
    """Fetch all items from specified item groups that are not disabled."""
    fields = ['name', 'item_code', 'item_name', 'item_group']
    filters = {'item_group': ['in', item_groups], 'disabled': False}
    return frappe.get_all('Item', fields=fields, filters=filters)

# Item Creation and Management
def create_new_item(item, start_code):
    """Create a new item based on existing item with a new item code."""
    data = {
        'item_code': str(start_code),
        'item_name': f"{item['item_code']}-ASM",
        'item_group': 'Valve Head',
        'stock_uom': 'Nos',
        'is_stock_item': True,
        'include_item_in_manufacturing': True,
        'default_material_request_type': 'Manufacture',
        'description': f"Valve Head {item['item_code']}-ASM Assembly w/ Components",
        'item_defaults': [{'company': 'Advanced Microfluidics SA', 'default_warehouse': 'Assemblies - AMF21'}],
        'disabled': False
    }
    create_document('Item', data)

def create_new_item_and_bom():  
    # Fetch all items from the "Plug" and "Valve Seat" item groups
    item_groups = {
        'Plug': fetch_items('Plug'),
        'Valve Seat': fetch_items('Valve Seat')
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
            new_item = {
                'doctype': 'Item',
                'item_code': str(item_code_plug) if group_name == 'Plug' else str(item_code_seat),
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
            }
            create_document('Item', new_item)
            commit_transaction()
            # Prepare the BOM
            new_bom = {
                'doctype': 'BOM',
                'item': str(item_code_plug) if group_name == 'Plug' else str(item_code_seat),
                'quantity': 1,
                'is_default': 1,
                'is_active': 1,
                'items': [
                    {'item_code': item['name'], 'qty': 1},
                    {'item_code': 'SPL.3013' if group_name == 'Plug' else 'SPL.3039', 'qty': accessory_qty},
                ],
            }
            create_document('BOM', new_bom)
            commit_transaction()
            # Increment the item code for the next new item
            increment_code(1) if group_name == 'Plug' else increment_code(2)

    return None

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

def create_items_from_list(items):
    """Create new items from a list, starting with a specific code."""
    for item in items:
        create_new_item(item, item_code_head)
        increment_code(3)
    commit_transaction()
    log_info("All new items have been created successfully.")

# Item Processing
def process_item_codes(items):
    """Process item codes to extract and store individual parts."""
    processed_items = []
    for item in items:
        parts = item['item_code'].split('-')
        processed_parts = [part for sub in parts for part in sub.split()]
        if len(processed_parts) < 3:
            continue
        processed_items.append({'item_code': item['item_code'], 'item_name': item['item_name'], 'split_parts': processed_parts})
    return processed_items

# Item Matching and Reporting
def get_matching_plugs_seats(processed_items):
    """Match plugs and seats based on processed items' split parts."""
    all_plugs_seats = fetch_items_with_group(['Plug', 'Valve Seat'])
    plugs = [item for item in all_plugs_seats if item['item_group'] == 'Plug']
    seats = [item for item in all_plugs_seats if item['item_group'] == 'Valve Seat']

    matched_items = []
    for item in processed_items:
        if len(item['split_parts']) >= 7:
            patterns = {
                'plug': f"{item['split_parts'][1]}-{item['split_parts'][2]}-{item['split_parts'][3]}-{item['split_parts'][4]}-{item['split_parts'][6]}-ASM",
                'seat': f"{item['split_parts'][1]}-{item['split_parts'][2]}-{item['split_parts'][3]}-{item['split_parts'][4]}-{item['split_parts'][5]}-ASM"
            }
            filtered_plugs = [plug for plug in plugs if patterns['plug'] in plug['item_name']]
            filtered_seats = [seat for seat in seats if patterns['seat'] in seat['item_name']]
            matched_items.append({'valve_head': item['item_code'], 'plug_items': filtered_plugs, 'seat_items': filtered_seats, 'plug_pattern': patterns['plug'], 'seat_pattern': patterns['seat']})
    return matched_items

def match_items(processed_items, print_mode):
    """Print matching plugs and seats for processed items."""
    matched_items = get_matching_plugs_seats(processed_items)
    for match in matched_items:
        if print_mode:
            print("Valve Head: ", match['valve_head'])
            print("Matching Plugs: ", [plug['item_name'] for plug in match['plug_items']])
            print("Matching Seats: ", [seat['item_name'] for seat in match['seat_items']])
            # Create missing Plugs and Seats
        if not match['plug_items']:  # No matching plugs found
            create_item('Plug', item_code_plug, match['plug_pattern'])
            if print_mode: print(f"Created missing plug: P-{match['plug_pattern']}")
            increment_code(1)
        if not match['seat_items']:  # No matching seats found
            create_item('Valve Seat', item_code_seat, match['seat_pattern'])
            if print_mode: print(f"Created missing seat: S-{match['seat_pattern']}")
            increment_code(2)

def create_item(item_group, code_group, item_pattern):
    """Create an item in the specified item group with the given pattern."""
    prefix = 'P' if item_group == 'Plug' else 'S'
    new_item_name = f"{prefix}-{item_pattern}"
    new_item = {
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
    }
    create_document('Item', new_item)
    commit_transaction()

def create_bom_head(code_plug, code_seat, code_head):
    new_bom = {
        'doctype': 'BOM',
        'item': code_head[0],
        'quantity': 1,
        'is_default': 1,
        'is_active': 1,
        'items': [
            {'item_code': code_plug[0], 'qty': 1},
            {'item_code': code_seat[0], 'qty': 1},
        ],
    }
    create_document('BOM', new_bom)
    commit_transaction()
    log_info("BOM associated created.")

def fetch_item_codes(item_names):
    """Fetch item codes for a list of item names."""
    item_codes = frappe.get_all(
        'Item', 
        fields=['item_code'],
        filters={'item_name': ['in', item_names], 'disabled': False}
    )
    return [item['item_code'] for item in item_codes]

def log_matching_items(match):
    """Log matching items' details."""
    print("Valve Head: ", match['valve_head'])
    print("Matching Plugs: ", [plug['item_name'] for plug in match['plug_items']])
    print("Matching Seats: ", [seat['item_name'] for seat in match['seat_items']])

def create_bom_for_items(match):
    """Create BOMs based on the matching plugs, seats, and valve heads."""
    plug_names = [plug['item_name'] for plug in match['plug_items']]
    seat_names = [seat['item_name'] for seat in match['seat_items']]
    valve_head_name = f"{match['valve_head']}-ASM"

    # Fetch item codes for plugs, seats, and the valve head
    plug_codes = fetch_item_codes(plug_names)
    seat_codes = fetch_item_codes(seat_names)
    valve_head_codes = fetch_item_codes([valve_head_name])

    # Assuming create_bom_head is a defined function that accepts three lists of item codes
    create_bom_head(plug_codes, seat_codes, valve_head_codes)

# Master Method to Manage Valve Head Items
@frappe.whitelist()
def manage_valve_head_items(creation_mode=True, print_mode=False):
    """Master function to fetch, create, process, and report on Valve Head items."""
    items = fetch_items('Valve Head')
    if creation_mode:
        create_new_item_and_bom()
        create_items_from_list(items)
    processed_items = process_item_codes(items)
    match_items(processed_items, print_mode)
    matched_items = get_matching_plugs_seats(processed_items)
    for match in matched_items:
        log_matching_items(match)
        create_bom_for_items(match)