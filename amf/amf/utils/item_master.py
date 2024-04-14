import frappe

def fetch_items(item_group, disabled=False):
    """Fetch all enabled items from a specific item group."""
    return frappe.get_all('Item', fields=['name', 'item_code', 'item_name'],
                          filters={'item_group': item_group, 'disabled': disabled})

def create_new_items(items, start_code=300001):
    """Create new items based on existing ones with modifications."""
    for item in items:
        new_item_code = str(start_code)
        new_item_name = f"{item['item_code']}-ASM"
        
        new_item = frappe.get_doc({
            'doctype': 'Item',
            'item_code': new_item_code,
            'item_name': new_item_name,
            'item_group': 'Valve Head',
            'disabled': False
        })
        new_item.insert()
        frappe.db.commit()
        start_code += 1

    print("All new items have been created successfully.")
    return start_code

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

def print_matching_items(processed_items, print_mode):
    """Print matching plugs and seats for processed items."""
    matching_items = get_matching_plugs_seats(processed_items)
    if print_mode:
        for match in matching_items:
            print("Valve Head: ", match['valve_head'])
            print("Matching Plugs: ", [plug['item_name'] for plug in match['plug_items']])
            print("Matching Seats: ", [seat['item_name'] for seat in match['seat_items']])

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
            print(pattern_plug)
            # Filter plugs and seats
            filtered_plugs = [plug for plug in plugs if pattern_plug in plug['item_name']]
            filtered_seats = [seat for seat in seats if pattern_seat in seat['item_name']]

            matched_items.append({
                'valve_head': item['item_code'],
                'plug_items': filtered_plugs,
                'seat_items': filtered_seats
            })

    return matched_items

# MASTER METHOD
@frappe.whitelist()
def get_valve_head_items(creation_mode=False, print_mode=True):
    items = fetch_items('Valve Head')
    if creation_mode:
        create_new_items(items)
    processed_items = process_item_codes(items)
    print_matching_items(processed_items, print_mode)
