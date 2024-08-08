import re
import frappe
from amf.amf.utils.utilities import *

# TO BE DONE
# Variants
# Account Defaults
# Auto Item Creation w/ pop-up window: nb magnets, pins, etc.

@frappe.whitelist()
def main():
    item_info = build_item_matrix()
    find_corresponding_items(item_info)
    new_bom_component()
    new_asm_component()
    new_bom_asm()
    new_bom_head()
    init_item_defaults()
    
    return None

def find_corresponding_items(item_info):
    log = create_log_entry("Starting amf.amf.utils.item_master6 method...", "find_corresponding_items(item_info)")
    fields = ['name', 'item_code', 'item_name', 'item_group']
    for row in item_info:
        count = 0
        if 'P' in row['no']:
            if row['addon']:
                pattern = f"PLUG-{row['type']}-{row['channel']}-{row['ports']}-{row['size']}-{row['plug_raw_material']}{row['addon']}"
            else:
                pattern = f"PLUG-{row['type']}-{row['channel']}-{row['ports']}-{row['size']}-{row['plug_raw_material']}"

            plug = frappe.get_all('Item', filters={'item_group': 'Plug', 'item_name': pattern, 'disabled': '0'}, fields=fields)
            correct_item(row, plug, log)
            count+=1
            update_log_entry(log, f"{plug}")
        if 'S' in row['no']:
            if row['addon']:
                pattern = f"SEAT-{row['type']}-{row['channel']}-{row['ports']}-{row['size']}-{row['seat_raw_material']}{row['addon']}"
            else:
                pattern = f"SEAT-{row['type']}-{row['channel']}-{row['ports']}-{row['size']}-{row['seat_raw_material']}"
            
            seat = frappe.get_all('Item', filters={'item_group': 'Valve Seat', 'item_name': pattern, 'disabled': '0'}, fields=fields)
            correct_item(row, seat, log)
            count+=1
            update_log_entry(log, f"{seat}")
        if 'V' in row['no']:
            if row['addon']:
                pattern = f"V-{row['type']}-{row['channel']}-{row['ports']}-{row['size']}-{row['seat_raw_material']}-{row['plug_raw_material']}{row['addon']}"
            else:
                pattern = f"V-{row['type']}-{row['channel']}-{row['ports']}-{row['size']}-{row['seat_raw_material']}-{row['plug_raw_material']}"
                
            head = frappe.get_all('Item', filters={'item_group': 'Valve Head', 'item_code': pattern, 'disabled': '0'}, fields=fields)
            correct_item(row, head, log)
            count+=1
            update_log_entry(log, f"{head}")
        update_log_entry(log, f"{count}")
        print("Eof corresponding_item")
    return None

def correct_item(row, items, log):
    def generate_info(item, new_item_code):
        if item['item_group'] == 'Valve Head':
            match = re.search(r'-(\w{1,2})-', item['item_name'])
            if match:
                idx = match.start(1)
                tail = item['item_name'][idx:]
                new_prefix = "VALVE HEAD-"
                item_name = f"{new_prefix}{tail}"
            return item_name, f"{new_item_code}: {item['item_code']}", f"""<div><strong>Code</strong>: {new_item_code}</div>
                    <div><strong>Reference</strong>: {item['item_code']}</div>
                    <div><strong>Name</strong>: {item_name.upper()}</div>
                    <div><strong>Group</strong>: {item['item_group']}</div>"""
        else:
            return item['item_name'], f"{item['item_code']}: {item['item_name'].upper()}", f"""<div><strong>Code</strong>: {new_item_code}</div>
                    <div><strong>Reference</strong>: {item['item_code']}</div>
                    <div><strong>Name</strong>: {item['item_name'].upper()}</div>
                    <div><strong>Group</strong>: {item['item_group']}</div>"""

    def generate_item_code(index, item):
        if item['item_group'] == 'Plug':
            return f"1000{index}"
        if item['item_group'] == 'Valve Seat':
            return f"2000{index}"
        if item['item_group'] == 'Valve Head':
            return f"3000{index}"
    
    for item in items:
        update_log_entry(log, f"Correcting: {item}") 
        new_item_code = generate_item_code(row['index'], item)
        item_name, reference_name, description = generate_info(item, new_item_code)
        update_item(item, item_name, new_item_code, reference_name, description, log)
        
    return None

def update_item(item, item_name, new_item_code, reference_name, description, log):
    if not re.match(r'^\d{6}$', item['name']):
        frappe.db.set_value('Item', item['name'], 'item_code', new_item_code)
        frappe.db.set_value('Item', item['name'], 'item_name', item_name.upper())
        frappe.db.set_value('Item', item['name'], 'reference_name', reference_name)
        frappe.db.set_value('Item', item['name'], 'reference_code', item['item_code'])
        frappe.db.set_value('Item', item['name'], 'internal_description', description)
        frappe.db.set_value('Item', item['name'], 'has_batch_no', 1)
        frappe.db.set_value('Item', item['name'], 'create_new_batch', 0)
        frappe.db.set_value('Item', item['name'], 'sales_uom', 'Nos')
        frappe.db.set_value('Item', item['name'], 'purchase_uom', 'Nos')
        frappe.db.set_value('Item', item['name'], 'country_of_origin', 'Switzerland')
        frappe.db.set_value('Item', item['name'], 'variant_of', '')
        frappe.db.set_value('Item', item['name'], 'default_material_request_type', 'Manufacture')
        frappe.db.set_value('Item', item['name'], 'warranty_period', '365')
        frappe.db.set_value('Item', item['name'], 'end_of_life', '31-12-2099')
        frappe.db.set_value('Item', item['name'], 'weight_uom', 'Kg')
        if item['item_group'] == 'Valve Head':
            frappe.db.set_value('Item', item['name'], 'customs_tariff_number', '8487.9000')
            frappe.db.set_value('Item', item['name'], 'weight_per_unit', '0.10')
            frappe.db.set_value('Item', item['name'], 'is_sales_item', '1')
            frappe.db.set_value('Item', item['name'], 'item_type', 'Sub-Assembly')
        elif item['item_group'] == 'Valve Seat' or item['item_group'] == 'Plug':
            frappe.db.set_value('Item', item['name'], 'item_type', 'Component')
        
        frappe.rename_doc('Item', item['item_code'], f"{new_item_code}", merge=False)
    
    update_log_entry(log, f"Updated: {item}")
    commit_database()
    return None

def new_asm_component():
    log = create_log_entry("Starting amf.amf.utils.item_master6 method...", "new_asm_component()")
    def generate_info(item, new_code):
        if item['item_group'] == 'Plug':
            return f"""<div><strong>Code</strong>: {new_code}</div>
                          <div><strong>Reference</strong>: {item['reference_code']}.ASM</div>
                          <div><strong>Name</strong>: {item['item_name']}</div>
                          <div><strong>Group</strong>: {item['item_group']}</div>
                          <div><strong>Components</strong>: {item['item_code']} + SPL.3013</div>"""
        elif item['item_group'] == 'Valve Seat':
            return f"""<div><strong>Code</strong>: {new_code}</div>
                          <div><strong>Reference</strong>: {item['reference_code']}.ASM</div>
                          <div><strong>Name</strong>: {item['item_name']}</div>
                          <div><strong>Group</strong>: {item['item_group']}</div>
                          <div><strong>Components</strong>: {item['item_code']} + SPL.3039</div>"""
    
    items = frappe.get_all('Item', filters={'item_group': ['in', ['Plug', 'Valve Seat']],
                                            'disabled': '0',
                                            'item_code': ['like', '______']},
                                   fields=['name', 'item_code', 'item_name', 'item_group', 'reference_code'],
                                   order_by='item_code asc')
    for item in items:
        new_code = str(int(item['item_code']) + 10000)
        description = generate_info(item, new_code)

        new_item = {
            'doctype': 'Item',
            'item_code': f"{new_code}",
            'item_name': item['item_name'],
            'item_group': item['item_group'],
            'reference_code': f"{item['reference_code']}.ASM",
            'reference_name': f"{item['reference_code']}.ASM: {item['item_name']}",
            'has_batch_no': 0,
            'stock_uom': 'Nos',
            'is_stock_item': True,
            'include_item_in_manufacturing': True,
            'default_material_request_type': 'Manufacture',
            'internal_description': description,
            'item_defaults': [{
                'company': 'Advanced Microfluidics SA',
                'default_warehouse': 'Main Stock - AMF21',
                'expense_account': '4009 - Cost of material: Valve Head - AMF21',
                'income_account': '3007 - Valve Head sales revenue - AMF21'
            }],
            'disabled': False,
            'country_of_origin': 'Switzerland',
            'sales_uom': 'Nos',
            'customs_tariff_number': '8487.9000',
            'item_type': 'Sub-Assembly'
        }
        create_document('Item', new_item)
        commit_database()
        update_log_entry(log, f"Creation of: {item}")
    return None

def new_bom_component():
    log = create_log_entry("Starting amf.amf.utils.item_master6 method...", "new_bom_component()")
    code = '_0%'
    items = frappe.get_all('Item', filters={'item_group': ['in', ['Plug', 'Valve Seat']],
                                            'item_code': ['like', code],
                                            'disabled': '0',},
                                   fields=['name', 'item_code', 'item_name', 'item_group', 'reference_code'],
                                   order_by='item_code asc')
    
    for item in items:
        item_info = split_item_info(item)
        if item_info:
            item_info['code'] = item['item_code']
            item_info['index'] = item['item_code'][-2:]
            if item_info['group'].lower() in ['plug', 'p']:
                #plugs.append(item_info)
                item_info['w_station'] = 'EMCOTURN 45'
                item_info['time_in_mins'] = 6
                item_info['qty_raw'] = 0.02
                if 'P' in item_info['raw_material']:
                    raw_mat = ['MAT.1001', 'MAT.1007']
                elif 'U' in item_info['raw_material']:
                    raw_mat = ['MAT.1003']
                else:
                    raw_mat = []
            elif item_info['group'].lower() in ['seat', 's']:
                #seats.append(item_info)
                item_info['w_station'] = 'CMZ TTS 46'
                item_info['time_in_mins'] = 12
                item_info['qty_raw'] = 0.03
                if 'C' in item_info['raw_material'] and int(item_info['ports']) < 10:
                    raw_mat = ['MAT.1012','MAT.1006','MAT.1002']
                elif 'C' in item_info['raw_material'] and int(item_info['ports']) >= 10:
                    raw_mat = ['MAT.1013','MAT.1008','MAT.1005','MAT.1004']
                elif 'K' in item_info['raw_material'] and int(item_info['ports']) < 10:
                    raw_mat = ['MAT.1009']
                elif 'K' in item_info['raw_material'] and int(item_info['ports']) >= 10:
                    raw_mat = ['MAT.1010']
                elif 'P' in item_info['raw_material']:
                    raw_mat = ['MAT.1007']
                elif 'A' in item_info['raw_material']:
                    raw_mat = ['MAT.1011']
                else:
                    raw_mat = []
                if 'C' in item_info['raw_material'] and int(item_info['ports']) == 8 and int(item_info['size']) >= 100:
                    raw_mat = ['MAT.1013','MAT.1008','MAT.1005','MAT.1004']
        
        disable_existing_boms(item_info['code'])
        
        for mat in raw_mat:
            new_bom = {
                'doctype': 'BOM',
                'item': item_info['code'],
                'quantity': 1,
                'is_default': 1,
                'is_active': 1,
                'with_operations': 1,
                'operations':
                        [
                            {'operation': 'CNC Machining', 'workstation': item_info['w_station'], 'time_in_mins': item_info['time_in_mins'], 'operating_cost': item_info['time_in_mins']},
                        ],
                'items':
                        [
                            {'item_code': mat, 'qty': item_info['qty_raw']},
                        ],
            }    
            try:
                create_document('BOM', new_bom)
            except Exception as e:
                print(f"An error occurred: {str(e)}")
        
            commit_database()
        update_log_entry(log, f"BOM created for: {item}")          
    return None

def new_bom_asm():
    log = create_log_entry("Starting amf.amf.utils.item_master6 method...", "new_bom_asm()")
    code = '_1%'
    items = frappe.get_all('Item', filters={'item_group': ['in', ['Plug', 'Valve Seat']],
                                            'item_code': ['like', code],
                                            'disabled': '0',},
                                   fields=['name', 'item_code', 'item_name', 'item_group', 'reference_code'],
                                   order_by='item_code asc')
    
    for item in items:
        item_info = split_item_info(item)
        accessory_qty = item_info['ports'] if item['item_group'] == 'Plug' else 2
        components = frappe.get_all('Item', filters={'item_name': item['item_name'], 'item_code': ['like', '_0%'], 'disabled': '0'},
                                           fields=['name', 'item_code', 'item_name'])
        for component in components:
            bom_items = [
                {'item_code': component['item_code'], 'qty': 1},
                {'item_code': 'SPL.3013' if item['item_group'] == 'Plug' else 'SPL.3039', 'qty': accessory_qty},
            ]
            # Add an additional row for 'Valve Seat'
            if item['item_group'] == 'Valve Seat' and ('S' not in item_info['type'] or 'O' not in item_info['type'] or 'T' not in item_info['type']):
                bom_items.append({'item_code': 'RVM.1204', 'qty': 1})
                
            new_bom = {
                'doctype': 'BOM',
                'item': item['item_code'],
                'is_active': 1,
                'is_default': 1,
                'items': bom_items,
            }
            try:
                create_document('BOM', new_bom)
            except Exception as e:
                print(f"An error occurred: {str(e)}")
        
        update_log_entry(log, f"BOM created for: {item}")
        commit_database()
        
    return None

def new_bom_head():
    log = create_log_entry("Starting amf.amf.utils.item_master6 method...", "new_bom_head()")
    items = frappe.get_all('Item', filters={'item_group': 'Valve Head', 'item_code': ['like', '3_%'], 'disabled': '0',},
                                   fields=['name', 'item_code', 'item_name', 'item_group', 'reference_code', 'internal_description'],
                                   order_by='item_code asc')
    for item in items:
        item_info = split_item_info(item, True)
        update_log_entry(log, f"BOM created for: {item['item_code']}, {item_info}")
        boms = frappe.get_all('BOM', filters={'item': item['item_code'], 'is_active': 1, 'is_default': 1}, fields=['name'])
        code_plug = code_seat = qty_plug = qty_seat = 0
        for bom in boms:
            bom_doc = frappe.get_doc('BOM', bom['name'])
            filtered_items = frappe.get_all('BOM Item', filters={'parent': bom_doc.name, 'item_code': ['like', '______']}, fields=['name', 'item_code', 'qty'])
            for filtered_item in filtered_items:
                if filtered_item['item_code'].startswith('1'):
                    code_plug = int(filtered_item['item_code']) + 10000
                    qty_plug = filtered_item['qty']
                elif filtered_item['item_code'].startswith('2'):
                    code_seat = int(filtered_item['item_code']) + 10000
                    qty_seat = filtered_item['qty']
            
            bom_items = []           
            if code_plug:
                bom_items.append({'item_code': code_plug, 'qty': qty_plug})
            if code_seat:
                bom_items.append({'item_code': code_seat, 'qty': qty_seat})
            
            if bom_items:
                original_description = item['internal_description'] or ''
                additional_html = f'<div><strong>Components</strong>: {code_plug} + {code_seat}</div>'
                frappe.db.set_value('Item', item['name'], 'internal_description', f"{original_description}{additional_html}")
                
                disable_existing_boms(item['item_code'])
                
                new_bom = {
                        'doctype': 'BOM',
                        'item': item['item_code'],
                        'quantity': 1,
                        'is_default': 1,
                        'is_active': 1,
                        'with_operations': 0,
                        'items': bom_items,
                    }    
                try:
                    create_document('BOM', new_bom)
                except Exception as e:
                    print(f"An error occurred: {str(e)}")

        commit_database()
        
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
    
    commit_database()
    return None

def build_item_matrix():
    log = create_log_entry("Starting amf.amf.utils.item_master6 method...", "build_item_matrix()")
    items = frappe.get_all('Item', filters={'item_group': ['in', ['Plug', 'Valve Seat', 'Valve Head']],
                                            'disabled': '0'},
                                   fields=['name', 'item_code', 'item_name', 'item_group'],
                                   order_by='item_group asc')
    
    plug_count = 0
    valve_seat_count = 0
    valve_head_count = 0
    index_counter = 1  # Initialize the counter

    plugs = []
    valve_seats = []
    valve_heads = []
    matrix = []
    
    for item in items:
        item_info = split_item_info(item)
        if item_info:
            if item_info['group'].lower() in ['plug', 'p']:
                plug_count += 1
                plugs.append(item_info)
            elif item_info['group'].lower() in ['seat', 's']:
                valve_seat_count += 1
                valve_seats.append(item_info)
            elif item_info['group'].lower() == 'v':
                valve_head_count += 1
                valve_heads.append(item_info)
    
    update_log_entry(log, f"Number of Plugs: {plug_count}")
    update_log_entry(log, f"Number of Valve Seats: {valve_seat_count}")
    update_log_entry(log, f"Number of Valve Heads: {valve_head_count}")  
    print(f"Number of Plugs: {plug_count}")
    print(f"Number of Valve Seats: {valve_seat_count}")
    print(f"Number of Valve Heads: {valve_head_count}")
    
    # Find matches and add unmatched items
    matched_indices_seats = set()
    matched_indices_valve_heads = set()

    for i, plug in enumerate(plugs):
        matched = False
        for j, seat in enumerate(valve_seats):
            if (plug['type'] == seat['type'] and 
                plug['channel'] == seat['channel'] and
                plug['ports'] == seat['ports'] and
                plug['size'] == seat['size'] and
                plug.get('addon') == seat.get('addon')):
                
                # Check for matching valve head
                valve_head_matched = False
                for k, valve_head in enumerate(valve_heads):
                    if (valve_head['type'] == plug['type'] and
                        valve_head['channel'] == plug['channel'] and
                        valve_head['ports'] == plug['ports'] and
                        valve_head['size'] == plug['size'] and
                        valve_head['seat_raw_material'] == seat['raw_material'] and
                        valve_head['plug_raw_material'] == plug['raw_material'] and
                        valve_head.get('addon') == plug.get('addon')):
                        
                        match = {
                            'index': f"{index_counter:02d}",
                            'type': plug['type'],
                            'channel': plug['channel'],
                            'ports': plug['ports'],
                            'size': plug['size'],
                            'seat_raw_material': seat['raw_material'],
                            'plug_raw_material': plug['raw_material'],
                            'addon': plug.get('addon'),
                            'no': 'PSV',
                        }
                        matrix.append(match)
                        matched_indices_seats.add(j)  # Store the index of the matched seat
                        matched_indices_valve_heads.add(k)  # Store the index of the matched valve head
                        valve_head_matched = True
                        matched = True
                        index_counter += 1
                        break
                
                if not valve_head_matched:
                    match = {
                        'index': f"{index_counter:02d}",
                        'type': plug['type'],
                        'channel': plug['channel'],
                        'ports': plug['ports'],
                        'size': plug['size'],
                        'seat_raw_material': seat['raw_material'],
                        'plug_raw_material': plug['raw_material'],
                        'addon': plug.get('addon'),
                        'no': 'PS',
                    }
                    matrix.append(match)
                    matched_indices_seats.add(j)  # Store the index of the matched seat
                    matched = True
                    index_counter += 1
                    break

        if not matched:
            matrix.append({
                'index': f"{index_counter:02d}",
                'type': plug['type'],
                'channel': plug['channel'],
                'ports': plug['ports'],
                'size': plug['size'],
                'seat_raw_material': None,
                'plug_raw_material': plug['raw_material'],
                'addon': plug.get('addon'),
                'no': 'P',
            })
            index_counter += 1

    for j, seat in enumerate(valve_seats):
        if j not in matched_indices_seats:
            valve_head_matched = False
            for k, valve_head in enumerate(valve_heads):
                if (valve_head['type'] == seat['type'] and
                    valve_head['channel'] == seat['channel'] and
                    valve_head['ports'] == seat['ports'] and
                    valve_head['size'] == seat['size'] and
                    valve_head['seat_raw_material'] == seat['raw_material'] and
                    valve_head.get('addon') == seat.get('addon')):
                    
                    match = {
                        'index': f"{index_counter:02d}",
                        'type': seat['type'],
                        'channel': seat['channel'],
                        'ports': seat['ports'],
                        'size': seat['size'],
                        'seat_raw_material': seat['raw_material'],
                        'plug_raw_material': None,
                        'addon': seat.get('addon'),
                        'no': 'SV',
                    }
                    matrix.append(match)
                    matched_indices_valve_heads.add(k)  # Store the index of the matched valve head
                    valve_head_matched = True
                    index_counter += 1
                    break
            
            if not valve_head_matched:
                matrix.append({
                    'index': f"{index_counter:02d}",
                    'type': seat['type'],
                    'channel': seat['channel'],
                    'ports': seat['ports'],
                    'size': seat['size'],
                    'seat_raw_material': seat['raw_material'],
                    'plug_raw_material': None,
                    'addon': seat.get('addon'),
                    'no': 'S',
                })
                index_counter += 1

    for k, valve_head in enumerate(valve_heads):
        if k not in matched_indices_valve_heads:
            matrix.append({
                'index': f"{index_counter:02d}",
                'type': valve_head['type'],
                'channel': valve_head['channel'],
                'ports': valve_head['ports'],
                'size': valve_head['size'],
                'seat_raw_material': valve_head['seat_raw_material'],
                'plug_raw_material': valve_head['plug_raw_material'],
                'addon': valve_head.get('addon'),
                'no': 'V',
            })
            index_counter += 1

    for row in matrix:
        update_log_entry(log, f"{row}")
    print("Eof build_matrix")
    return matrix

def split_item_info(item, new_head=None):
    """
    This method splits items from the Item Doctype into different variables
    based on their patterns. It takes one argument: an item fetched from the get_all method.
    
    :param item: A dictionary containing item information, including 'item_name' and 'item_code'.
    :return: A dictionary with the split parts.
    """
    def split_parts(parts, is_valve_head=False):
        """
        Helper function to split parts based on whether it's a valve head or not.
        """
        if is_valve_head:
            return {
                'group': parts[0],
                'type': parts[1],
                'channel': parts[2],
                'ports': parts[3],
                'size': parts[4],
                'seat_raw_material': parts[5],
                'plug_raw_material': parts[6],
                'addon': f" {parts[7]}" if len(parts) > 7 else ''
            }
        else:
            return {
                'group': parts[0],
                'type': parts[1],
                'channel': parts[2],
                'ports': parts[3],
                'size': parts[4],
                'raw_material': parts[5],
                'addon': f" {parts[6]}" if len(parts) > 6 else ''
            }


    def is_valid_item_name(name):
        """
        Validate if the item name matches the expected patterns for Plug or Valve Seat.
        """
        return bool(re.match(r'^(PLUG|P|SEAT|S)[- ]\w+[- ]\d+[- ]\d+[- ](\d+|\d+\+\d+)[- ]\w+(?:[- ][\w\s/\-]+)?$', name, re.IGNORECASE)) 
           
    def is_valid_item_code(code):
        """
        Validate if the item code matches the expected pattern for Valve Head.
        """
        return bool(re.match(r'^V[- ]\w+[- ]\d+[- ]\d+[- ](\d+|\d+\+\d+)[- ]\w+[- ]\w+(?:[- ][\w\s/\-]+)?$', code, re.IGNORECASE))
    
    item_name = item.get('item_name', '')
    item_code = item.get('item_code', '')
    if new_head:
        item_code = item.get('reference_code', '')

    try:
        if is_valid_item_name(item_name):
            parts = item_name.replace(' ', '-').split('-')
            return split_parts(parts)
        elif is_valid_item_code(item_code):
            parts = item_code.replace(' ', '-').split('-')
            return split_parts(parts, is_valve_head=True)
    except:
        raise ValueError("Item does not match known patterns for Plug, Valve Seat, or Valve Head.")
    
def add_variant():
    log = create_log_entry("Starting amf.amf.utils.item_master6 method...", "add_variant()")
    items = frappe.get_all('Item', filters={'item_group': ['in', ['Plug', 'Valve Seat', 'Valve Head']],
                                            'item_code': ['like', '______'],
                                            'disabled': '0'},
                                   fields=['name', 'item_code', 'item_name', 'item_group'])
    for item in items:
        item_info = split_item_info(item)
        print(item)
        if item['item_group'] == 'Plug':
            frappe.db.set_value('Item', item['name'], 'variant_of', 'P')
        # elif item['item_group'] == 'Valve Seat':
        #     frappe.db.set_value('Item', item['name'], 'variant_of', )
        # elif item['item_group'] == 'Valve Head':
        #     frappe.db.set_value('Item', item['name'], 'variant_of', )
    return None

def create_product():
    log = create_log_entry("Starting amf.amf.utils.item_master6 method...", "create_product()")
    drivers = ['P100-O', 'P100-L', 'P101-O', 'P200-O', 'P201-O', 'P211-O', 'P221-O', 'UFM']
    heads = frappe.get_all('Item', filters={'item_group': 'Valve Head', 'item_code': ['like', '3_%'], 'disabled': '0'}, fields=['name', 'item_code', 'item_name', 'item_group', 'reference_code'])
    digit_driver = 40
    for driver in drivers:
        driver_name = driver.replace('-', '')
        digit_driver += 1
        for head in heads:
            head_name = head['reference_code'].replace('-', '')
            index = head['item_code'][-2:]
            new_item = {
                'doctype': 'Item',
                'item_code': f"{digit_driver}00{index}",
                'item_name': f"{driver} {head['reference_code']}",
                'item_group': 'Products',
                'reference_code': f"{driver_name}|{head_name}",
                'reference_name': f"{digit_driver}00{index}: {driver_name}-{head_name}",
                'has_batch_no': 0,
                'stock_uom': 'Nos',
                'is_stock_item': True,
                'include_item_in_manufacturing': True,
                'default_material_request_type': 'Manufacture',
                'description': '',
                'disabled': False,
                'country_of_origin': 'Switzerland',
                'has_serial_no': 1,
            }
            create_document('Item', new_item)
            # original_description = new_item['description'] or ''
            # additional_html = f""" {driver} + {head['item_code']}</div>"""
            # frappe.db.set_value('Item', new_item['name'], 'description', f"{original_description}{additional_html}")
            bom_items = [
                {'item_code': head['item_code'], 'qty': 1},
                {'item_code': driver, 'qty': 1},
            ]
            
            new_bom = {
                        'doctype': 'BOM',
                        'item': new_item['item_code'],
                        'quantity': 1,
                        'is_default': 1,
                        'is_active': 1,
                        'with_operations': 0,
                        'items': bom_items,
                    }    
            try:
                create_document('BOM', new_bom)
                update_log_entry(log, f"Creation of: {driver} & {head}")
            except Exception as e:
                print(f"An error occurred: {str(e)}")
            
            commit_database()
            
    return None

def att_variant():
    log = create_log_entry("Starting amf.amf.utils.item_master6 method...", "att_variant()")
    
    def get_attribute_value(attribute, abbreviation):
        # Fetch the attribute value based on the abbreviation
        attribute_value = frappe.db.get_value('Item Attribute Value', {'parent': attribute, 'abbr': abbreviation}, 'attribute_value')
        return attribute_value
    
    items = frappe.get_all('Item', 
        filters=[
            ['item_group', 'in', ['Plug']],
            ['disabled', '=', '0'],
            ['item_code', 'like', '_0%'],
            ['item_code', 'not like', '100000']
        ],
        fields=['name', 'item_code', 'item_name', 'item_group', 'reference_code']
    )
    
    code_template = 100000
    item_template = frappe.get_doc('Item', {'item_code': code_template})

    for item in items:
        item_info = split_item_info(item)

        if item_info:
            frappe.db.set_value('Item', item['name'], 'variant_of', code_template)
            # Process each attribute defined in the template, using an index to access corresponding item_info
            for idx, template_attr in enumerate(item_template.attributes, start=1):
                
                abbreviation = list(item_info.values())[idx]
                # Fetch the attribute value corresponding to the abbreviation
                attribute_value = get_attribute_value(template_attr.attribute, abbreviation)
                
                if idx < len(item_info):  # Ensure there is a corresponding element in item_info
                    # Insert a new attribute row
                    frappe.get_doc({
                        'doctype': 'Item Variant Attribute',
                        'parent': item['name'],
                        'parentfield': 'attributes',
                        'parenttype': 'Item',
                        'attribute': template_attr.attribute,
                        'attribute_value': attribute_value,
                    }).insert()
                else:
                    print("No data provided for attribute:", template_attr.attribute)
            
            # Save changes to the item
            try:
                frappe.get_doc('Item', item['name']).save()
            except Exception as e:
                print('ERROR:', e)
                
    return None

def kill_variant():
    log = create_log_entry("Starting amf.amf.utils.item_master6 method...", "att_variant()")
    items = frappe.get_all('Item', filters={'item_group': ['in', ['Plug']],
                                            'disabled': '0'},
                                   fields=['name', 'item_code', 'item_name', 'item_group', 'reference_code'])
        
    for item in items:
        try:
            frappe.db.set_value('Item', item['name'], 'variant_of', '')
            frappe.get_doc('Item', item['name']).save()
        except:
            print('ERROR',{item})
        # Save changes to the item
        
    return None

def init_item_defaults():
    log = create_log_entry("Starting amf.amf.utils.item_master6 method...", "init_item_defaults()")

    """
    This method retrieves all items with a 6-digit item code, 
    clears the item_defaults child table, and sets the 'company', 'default_warehouse',
    'expense_account', and 'income_account' fields for each entry in item_defaults.

    Returns:
    int: The number of items updated.
    """
    # Get all items with a 6-digit item code and specific item_group
    items = frappe.get_all('Item', filters={'name': ['like', '_0%'], 'item_group': ['in', ['Plug', 'Valve Seat', 'Valve Head']]}, fields=['name', 'item_group'])

    if not items:
        frappe.msgprint("No items found with a 6-digit item code.")
        return 0

    item_count = 0

    for item in items:
        # Load the item document
        item_doc = frappe.get_doc('Item', item['name'])

        # Clear the item_defaults table
        item_doc.item_defaults = []

        # Define the fields to set for the new item_defaults entry
        company = 'Advanced Microfluidics SA'
        default_warehouse = 'Main Stock - AMF21'
        expense_account = None
        income_account = None

        # Check item group to set specific accounts
        if item['item_group'] == 'Valve Head':
            expense_account = '4009 - Cost of material: Valve Head - AMF21'
            income_account = '3007 - Valve Head sales revenue - AMF21'

        # Create a new item_defaults entry
        new_item_default = {
            'company': company,
            'default_warehouse': default_warehouse
        }

        # Add expense and income accounts if applicable
        if expense_account:
            new_item_default['expense_account'] = expense_account
        if income_account:
            new_item_default['income_account'] = income_account

        # Append the new entry to item_defaults
        item_doc.append('item_defaults', new_item_default)

        # Save the changes to the item document
        item_doc.save()

        # Increment the counter
        item_count += 1

    print(f"Total Items Processed: {item_count}")
    update_log_entry(log, f"No of Items: {item_count}")

    # Return the number of items updated
    return None