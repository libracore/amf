import re
import time
from amf.amf.doctype.item_creation.item_creation import get_last_item_code
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
        

@frappe.whitelist()
def execute_db_enqueue():
    """
    This can be called manually to enqueue the full update of all items.
    """
    frappe.enqueue("amf.amf.utils.item_master.update_item_defaults", queue='long', timeout=15000)
    return

def update_item_defaults():
    mapping = {
        "30_%": ("4003 - Cost of material: RVM rotary valve - AMF21", "3003 - RVM sales revenue - AMF21"),
        "41_%": ("4003 - Cost of material: RVM rotary valve - AMF21", "3003 - RVM sales revenue - AMF21"),
        "42_%": ("4003 - Cost of material: RVM rotary valve - AMF21", "3003 - RVM sales revenue - AMF21"),
        "43_%": ("4003 - Cost of material: RVM rotary valve - AMF21", "3003 - RVM sales revenue - AMF21"),
        "44_%": ("4003 - Cost of material: RVM rotary valve - AMF21", "3003 - RVM sales revenue - AMF21"),
        "45_%": ("4002 - Cost of material: SPM - AMF21", "3002 - SPM sales revenue - AMF21"),
        "46_%": ("4002 - Cost of material: SPM - AMF21", "3002 - SPM sales revenue - AMF21"),
        "47_%": ("4001 - Cost of material: LSP - AMF21", "3001 - LSP sales revenue - AMF21"),
        "51_%": ("4002 - Cost of material: SPM - AMF21", "3002 - SPM sales revenue - AMF21"),
        "51001_%": ("4001 - Cost of material: LSP - AMF21", "3001 - LSP sales revenue - AMF21"),
        "52_%": ("4003 - Cost of material: RVM rotary valve - AMF21", "3003 - RVM sales revenue - AMF21"),
        "UFM": ("4000 - Cost of material: UFM - AMF21", "3000 - UFM sales revenue - AMF21"),
    }
    
    for item_code_pattern, accounts in mapping.items():
        item_list = frappe.get_all("Item", "name", filters={"item_code": ["like", item_code_pattern]})
        
        for item_code in item_list:
            item_doc = frappe.get_doc("Item", item_code)
            
            # Clear existing item_defaults table
            item_doc.set("item_defaults", [])            
            
            # Add new records to item_defaults
            if isinstance(accounts, list):
                for expense_account, income_account in accounts:
                    item_doc.append("item_defaults", {
                        "company": "Advanced Microfluidics SA",
                        "default_warehouse": "Main Stock - AMF21",
                        "expense_account": expense_account,
                        "income_account": income_account
                    })
            else:
                expense_account, income_account = accounts
                item_doc.append("item_defaults", {
                    "company": "Advanced Microfluidics SA",
                    "default_warehouse": "Main Stock - AMF21",
                    "expense_account": expense_account,
                    "income_account": income_account
                })
            
            # Save document
            item_doc.save()
            frappe.db.commit()
            
            print(f"Updated item: {item_code}")


@frappe.whitelist()
def execute_db_enqueue_delete():
    """
    This can be called manually to enqueue the full update of all items.
    """
    frappe.enqueue("amf.amf.utils.item_master.delete_disabled_items_with_bom", queue='long', timeout=15000)
    return

def delete_disabled_items_with_bom():
    # Get a direct list of item names (strings) whose item_code starts with '45_' and are disabled
    items_data = frappe.db.sql(
        """
        SELECT name
        FROM `tabItem`
        WHERE item_code LIKE '45_%'
          AND disabled = 1
        """,
        as_list=True
    )
    # items_data is a list of lists (e.g. [["ITEM-001"], ["ITEM-002"], ...])
    # so we flatten it to a list of strings:
    items = [row[0] for row in items_data]

    for item_name in items:
        try:
            # For each Item, get BOMs as a direct list
            boms_data = frappe.db.sql(
                """
                SELECT name
                FROM `tabBOM`
                WHERE item = %s
                """,
                (item_name,),
                as_list=True
            )
            boms = [row[0] for row in boms_data]

            for bom_name in boms:
                try:
                    bom_doc = frappe.get_doc("BOM", bom_name)
                    # If docstatus=1, cancel it before deletion
                    if bom_doc.docstatus == 1:
                        bom_doc.cancel()
                    frappe.delete_doc("BOM", bom_name)
                except Exception as e:
                    frappe.log_error(
                        title=f"Error processing BOM '{bom_name}'",
                        message=f"Exception: {str(e)}"
                    )

            try:
                frappe.delete_doc("Item", item_name)
            except Exception as e:
                frappe.log_error(
                    title=f"Error deleting Item '{item_name}'",
                    message=f"Exception: {str(e)}"
                )

        except Exception as e:
            frappe.log_error(
                title=f"Error during item iteration for '{item_name}'",
                message=f"Exception: {str(e)}"
            )

    frappe.db.commit()
    print(f"Completed processing. Attempted to delete {len(items)} items and their associated BOMs.")

@frappe.whitelist()
def get_max_six_digit_item_code(item_group, item_type):
    """
    Determine the next 6-digit code for the given item_group and item_type.

    Logic:
      1. If item_group is one of [Plug, Valve Seat, Valve Head], build a 6-digit code:
         - Digit #1: '1' for Plug, '2' for Valve Seat, '3' for Valve Head
         - Digit #2: 
              * '0' if (Plug or Valve Seat) + item_type=component
              * '1' if (Plug or Valve Seat) + item_type=sub-assembly
              * '2' if (Plug or Valve Seat) + item_type=finished good
              * '0' for Valve Head (no item_type logic)
         - Digits #3-#6: the next 4-digit sequence, found by get_last_item_code(None) + 1
           (zero-padded to 4 digits).
      2. Otherwise, use the "normal" approach (see get_normal_six_digit_code), which:
         - Derives a second digit from item_type (component→0, sub-assembly→1, finished good→2, else 0)
         - Looks up the highest 6-digit code matching ^[0-9]{second_digit}[0-9]{4}$
         - Returns the next code zero-padded to 6 digits.
    """
    # Safety check
    if not item_group:
        # Return a fallback if no group
        return "000000"

    # Define your "special" groups
    special_groups = ['Plug', 'Valve Seat', 'Valve Head', 'Product']

    # If not a special group => do normal logic
    if item_group not in special_groups:
        return get_normal_six_digit_code(item_group, item_type)

    # -----------------------------------------------------
    # Special group => gather the "last item code" baseline
    # -----------------------------------------------------
    # get_last_item_code(None) is assumed to return an integer
    # representing the highest found so far; handle accordingly.
    current_last = get_last_item_code(None) or 0  # ensure integer fallback
    next_val = current_last + 1
    last_four = str(next_val).zfill(4)  # e.g. '0007'

    # 1) Determine the first digit (group-based)
    group_digit_map = {
        'Plug': '1',
        'Valve Seat': '2',
        'Valve Head': '3',
        'Product': '4',
    }
    first_digit = group_digit_map.get(item_group, '0')

    # 2) Determine the second digit
    #    Only matters for Plug or Valve Seat. Otherwise, e.g. Valve Head => '0'.
    if item_group in ['Plug', 'Valve Seat']:
        item_type_lower = (item_type or '').strip().lower()
        if item_type_lower == 'component':
            second_digit = '0'
        elif item_type_lower == 'sub-assembly':
            second_digit = '1'
        elif item_type_lower == 'finished good':
            second_digit = '2'
        else:
            # Fallback if item_type is something else
            second_digit = '0'
    elif item_group in ['Product']:
        second_digit = 'X'
    else:
        # For Valve Head => '0'
        second_digit = '0'

    # 3) Construct the final 6-digit code
    #    Example: '10' + '0015' => '100015'
    final_code = f"{first_digit}{second_digit}{last_four}"
    return final_code


def get_normal_six_digit_code(item_group, item_type):
    """
    Fallback logic for non-special groups:
      - Derive second digit from item_type (component=0, sub-assembly=1, finished good=2, else 0).
      - Find the max code matching ^[0-9]{second_digit}[0-9]{4}$ in the same item_group.
      - Return next 6-digit code.
    """
    if not item_group:
        return "000000"

    # Determine second digit from item_type
    item_type_lower = (item_type or '').strip().lower()
    if item_type_lower == 'component':
        second_digit = '0'
    elif item_type_lower == 'sub-assembly':
        second_digit = '1'
    elif item_type_lower == 'finished good':
        second_digit = '2'
    else:
        second_digit = '0'

    # Create a pattern that enforces:
    #  1st digit is [0-9], 
    #  2nd digit is second_digit, 
    #  next 4 digits are [0-9].
    pattern = f'^[0-9]{second_digit}[0-9]{{4}}$'

    result = frappe.db.sql(
        """
        SELECT MAX(CAST(item_code AS UNSIGNED)) AS max_code
        FROM `tabItem`
        WHERE item_group = %s
          AND disabled = 0
          AND item_code REGEXP %s
        """,
        (item_group, pattern),
        as_dict=True
    )

    max_code = result[0]["max_code"] if result and result[0].get("max_code") else 0
    next_code = max_code + 1
    return str(next_code).zfill(6)

import frappe

@frappe.whitelist()
def issue_and_then_enable_batch_for_raw_materials():
    """
    1) Create & submit a single Material Issue for all Raw Material items in all warehouses.
    2) After stock is issued, enable Batch No for those items. Disabled for now.
    3) Create (draft) Material Receipt with identical lines for restocking.
    """

    # Step 1a: Get all items in "Raw Material" item group
    raw_material_items = frappe.get_all(
        "Item",
        filters={"item_group": "Raw Material", "disabled": 0, "has_batch_no": 0},
        fields=["name"]
    )
    if not raw_material_items:
        frappe.msgprint("No items found in the 'Raw Material' group.")
        return

    # Step 1b: Gather line details for each item & warehouse from the Bin table
    line_details = []
    for rm_item in raw_material_items:
        bins = frappe.get_all(
            "Bin",
            filters={"item_code": rm_item.name},
            fields=["warehouse", "actual_qty"]
        )
        for bin_data in bins:
            if bin_data.actual_qty > 0:
                line_details.append({
                    "item_code": rm_item.name,
                    "warehouse": bin_data.warehouse,
                    "qty": bin_data.actual_qty
                })
                print("item_code", rm_item.name,
                      "warehouse", bin_data.warehouse,
                      "qty", bin_data.actual_qty)

    # If there's nothing to issue
    if not line_details:
        frappe.msgprint("No stock quantities found to issue for Raw Material items.")
        return

    # Step 1c: Create and submit Material Issue
    issue_entry = frappe.new_doc("Stock Entry")
    issue_entry.stock_entry_type = "Material Issue"

    for line in line_details:
        row = issue_entry.append("items", {})
        row.item_code = line["item_code"]
        row.s_warehouse = line["warehouse"]
        row.qty = line["qty"]
        row.uom = frappe.db.get_value("Item", line["item_code"], "stock_uom")

    issue_entry.insert()
    issue_entry.submit()
    frappe.db.commit()

    # Step 2: Now enable batch tracking for the raw material items
    # for rm_item in raw_material_items:
    #     item_doc = frappe.get_doc("Item", rm_item.name)
    #     if not item_doc.has_batch_no:
    #         item_doc.has_batch_no = 1
    #         item_doc.save(ignore_permissions=True)

    # Step 3: Create a draft Material Receipt with the same lines
    receipt_entry = frappe.new_doc("Stock Entry")
    receipt_entry.stock_entry_type = "Material Receipt"

    for line in line_details:
        row = receipt_entry.append("items", {})
        row.item_code = line["item_code"]
        row.t_warehouse = line["warehouse"]
        row.qty = line["qty"]
        row.uom = frappe.db.get_value("Item", line["item_code"], "stock_uom")

    # Insert but do NOT submit
    if receipt_entry.get("items"):
        receipt_entry.insert()
        frappe.msgprint(
            "Material Receipt has been created in Draft status. "
            "You can review and submit it when ready."
        )
    else:
        frappe.msgprint("No lines found for Material Receipt.")

    # Commit if running outside a request context (optional in most cases)
    frappe.db.commit()
