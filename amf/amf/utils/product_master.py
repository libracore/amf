import frappe
from amf.amf.utils.utilities import *

@frappe.whitelist()
def main():
    create_product_variant()
    frappe.msgprint("Eof create_product_variant()")
    return None

def create_product_variant():
    log = create_log_entry("Starting amf.amf.utils.product_master method...", "create_product_variant()")
    update_log_entry(log, f"Starting the 4X items creation...")
    print("Starting the 4X items creation...")
    
    item_group = 'Products'
    
    # Fetch the item attributes
    attributes = frappe.get_all('Item Attribute', filters={'attribute_name': ['in', ['Driver', 'Valve Head', 'Syringe']]}, fields=['name'])
    
    # Initialize dictionaries to store attribute values
    drivers, valve_heads, syringes = [], [], []
    count, group_digit, driver_digit = 0, 4, 1
    item_code, last_item_code = None, None

    
    # Separate attribute values based on their type
    for attribute in attributes:
        attribute_doc = frappe.get_doc('Item Attribute', attribute['name'])
        for value in attribute_doc.item_attribute_values:
            if attribute['name'] == 'Driver':
                drivers.append(value.attribute_value)
            elif attribute['name'] == 'Valve Head':
                valve_heads.append(value.attribute_value)
            elif attribute['name'] == 'Syringe':
                syringes.append(value.attribute_value)
    
    # Function to check if the combination is valid based on the rules
    def is_valid_combination(driver, valve_head, syringe):
        # Removing None Syringe
        if syringe == 'S-500-U-UFM' or syringe == 'None':
            return False
        # P100-O, P100-L, P101-O always go with a valve head (only V-D models) and a syringe
        if driver in ['P100-O', 'P100-L', 'P101-O']:
            if (valve_head.startswith('V-S') or valve_head.startswith('V-O') or valve_head.startswith('V-B')):
                return False
        # P201-O, P200-O, P211-O, P221-O go with all valve heads but no syringes
        elif driver in ['P201-O', 'P200-O', 'P211-O', 'P221-O']:
                return 'RVM'
        return 'TRUE'

    # Create combinations
    for driver in drivers:
        if not driver:
            break

        for valve_head in valve_heads:
            if not valve_head:
                break
            
            # Retrieve head_code and head_digit once per valve_head
            head_code = frappe.db.get_value('Item', {'reference_code': valve_head}, 'item_code')
            if not head_code:
                break
            head_digit = head_code[-2:]

            syringe_digit = 1
            for syringe in syringes:
                if not syringe:
                    break

                combination = is_valid_combination(driver, valve_head, syringe)
                if combination == 'RVM':
                    item_code = f"{group_digit}{driver_digit:01}00{head_digit}"
                    if frappe.db.exists('Item', {'item_code': item_code}):
                        continue
                    if last_item_code != item_code:
                        create_item(item_code, valve_head, driver)
                        count += 1
                        last_item_code = item_code
                elif combination == 'TRUE':
                    item_code = f"{group_digit}{driver_digit:01}{syringe_digit:02}{head_digit}"
                    if frappe.db.exists('Item', {'item_code': item_code}):
                        continue
                    create_item(item_code, valve_head, driver, syringe)
                    count += 1

                syringe_digit += 1
                
        driver_digit += 1
        print(">> Driver:", driver, "done")
        update_log_entry(log, f">> Driver: {driver} done")
        frappe.msgprint(f">> Driver: {driver} done")
    
    update_log_entry(log, f"Done creating items.")
    print(count)
    
    return None

def create_item(pdt_code, valve_head, driver, syringe=None):
    def generate_info(head, new_ref_code, new_item_name, pdt_code, driver, syringe=None):
        if syringe:
            return f"""<div><strong>Code</strong>: {pdt_code}</div>
                    <div><strong>Reference</strong>: {new_ref_code}</div>
                    <div><strong>Name</strong>: {new_item_name}</div>
                    <div><strong>Group</strong>: Products</div>
                    <div><strong>___________________________________________________________________</strong></div>
                    <div><strong>Driver: </strong>{driver.item_code}</div>
                    <div><strong>Valve: </strong>{head.reference_code}</div>
                    <div><strong>Syringe: </strong>{syringe.item_code}</div>"""
        else:
            return f"""<div><strong>Code</strong>: {pdt_code}</div>
                    <div><strong>Reference</strong>: {new_ref_code}</div>
                    <div><strong>Name</strong>: {new_item_name}</div>
                    <div><strong>Group</strong>: Products</div>
                    <div><strong>________________________________________</strong></div>
                    <div><strong>Driver: </strong>{driver.item_code}</div>
                    <div><strong>Valve: </strong>{head.reference_code}</div>"""
    
    head = frappe.db.get_value('Item', {'reference_code': valve_head}, ['item_code', 'item_name', 'item_group', 'reference_code', 'description'], as_dict=1)
    syringe = frappe.db.get_value('Item', {'item_code': syringe}, ['item_code', 'item_name', 'item_group'], as_dict=1) if syringe else ''
    driver = frappe.db.get_value('Item', {'item_code': driver}, ['item_code', 'item_name', 'item_group'], as_dict=1)
    if syringe:
        new_ref_code = (f"{driver.item_code}{head.item_code}{syringe.item_code}").replace('-', '')
        new_item_name = f"{driver.item_code}/{head.reference_code}/{syringe.item_code}"
        new_description = f"""{head.description}
                            <div>Driver: {driver.item_name}</div>
                            <div>Syringe: {syringe.item_code}</div>"""
    else:
        new_ref_code = (f"{driver.item_code}{head.item_code}").replace('-', '')
        new_item_name = f"{driver.item_code}/{head.reference_code}"
        new_description = f"""{head.description}
                            <div>Driver: {driver.item_name}</div>"""
    description = generate_info(head, new_ref_code, new_item_name, pdt_code, driver, syringe)

        
    
    def get_income_account(item_code):
        if item_code in ['P201-O', 'P200-O', 'P221-O', 'P211-O']:
            return '3003 - RVM sales revenue - AMF21', '4003 - Cost of material: RVM rotary valve - AMF21'
        elif item_code in ['P100-O', 'P101-O']:
            return '3002 - SPM sales revenue - AMF21', '4002 - Cost of material: SPM - AMF21'
        elif item_code in ['P100-L']:
            return '3001 - LSP sales revenue - AMF21', '4001 - Cost of material: LSP - AMF21'

    def get_weight(item_code):
        if item_code in ['P201-O', 'P221-O', 'P211-O']:
            return '0.53'
        elif item_code in ['P200-O']:
            return '0.33'
        elif item_code in ['P100-O']:
            return '1.31'
        elif item_code in ['P101-O']:
            return '1.34'
        elif item_code in ['P100-L']:
            return '2.18'
    
    # Get the appropriate income account based on driver.item_code
    income_account, expense_account = get_income_account(driver.item_code)
    weight = get_weight(driver.item_code)
    
    new_item = {
            'doctype': 'Item',
            'item_code': pdt_code,
            'item_name': new_item_name,
            'item_group': 'Products',
            'reference_code': new_ref_code,
            'reference_name': f"{pdt_code}: {new_ref_code}",
            'has_batch_no': 0,
            'stock_uom': 'Nos',
            'is_stock_item': True,
            'include_item_in_manufacturing': True,
            'default_material_request_type': 'Manufacture',
            'internal_description': description,
            'description': new_description,
            'item_defaults': [{
                'company': 'Advanced Microfluidics SA',
                'default_warehouse': 'Main Stock - AMF21',
                'expense_account': expense_account,
                'income_account': income_account
            }],
            'uoms': [{
                'uom': 'Nos',
                'conversion_factor': 1,
            }],
            'disabled': False,
            'country_of_origin': 'Switzerland',
            'sales_uom': 'Nos',
            'customs_tariff_number': '8479.5020',
            'is_sales_item': 1,
            'is_purchase_item': 0,
            'has_serial_no': 0,
            'purchase_uom': 'Nos',
            'weight_uom': 'Kg',
            'weight_per_unit': weight,
            'warranty_period': '365',
            'item_type': 'Finished Good',
    }
    #print(new_item)
    create_document('Item', new_item)
    commit_database()
    
    if syringe:
        bom_items = [
                {'item_code': driver.item_code, 'qty': 1},
                {'item_code': syringe.item_code, 'qty': 1},
                {'item_code': head.item_code, 'qty': 1},
                {'item_code': 'RVM.1204', 'qty': 1, 'conversion_factor': -1},
                {'item_code': 'SPL.3028', 'qty': 2},
        ]
        if driver.item_code == 'P101-O':
            bom_items.append({'item_code': 'SPL.1114.01', 'qty': 1})
    else:
        bom_items = [
                {'item_code': driver.item_code, 'qty': 1},
                {'item_code': head.item_code, 'qty': 1},
        ]
        if head.reference_code.startswith('V-S') or head.reference_code.startswith('V-O'):
            bom_items.append({'item_code': 'RVM.3002', 'qty': 2})
        else:
            bom_items.append({'item_code': 'SPL.3028', 'qty': 2})
        if ('8-100' in head.reference_code) \
            or ('10-050' in head.reference_code) \
            or ('10-100' in head.reference_code) \
            or ('10-075' in head.reference_code) \
            or ('10-080' in head.reference_code) \
            or ('12-050' in head.reference_code) \
            or ('12-080' in head.reference_code) \
            or ('12-100' in head.reference_code):
            bom_items.append({'item_code': 'RVM.3038', 'qty': 1})
        elif head.reference_code.startswith('V-S') or head.reference_code.startswith('V-O'):
            bom_items.append({'item_code': 'RVM.3039', 'qty': 1})
        else:
            bom_items.append({'item_code': 'RVM.3040', 'qty': 1})
             
    new_bom = {
                        'doctype': 'BOM',
                        'item': pdt_code,
                        'quantity': 1,
                        'is_default': 1,
                        'is_active': 1,
                        'with_operations': 0,
                        'items': bom_items,
                    }    
    try:
        create_document('BOM', new_bom)
    except Exception as e:
        #print(new_bom)
        print(f"An error occurred: {str(e)}")
            
    commit_database()
    #update_log_entry(log, f"Creation of: {item}")
    return None

@frappe.whitelist()
def delete_item():
    # Fetch all items with item_code starting with '4_' and not disabled
    products = frappe.get_all('Item', filters={'item_code': ['like', '4_%'], 'disabled': '0'}, fields=['name'])
    
    for product in products:
        # Retrieve the item document
        item_doc = frappe.get_doc('Item', product['name'])
        
        # Fetch and delete associated BOMs
        boms = frappe.get_all('BOM', filters={'item': item_doc.name}, fields=['name'])
        for bom in boms:
            bom_doc = frappe.get_doc('BOM', bom['name'])
            try:
                bom_doc.cancel()
                bom_doc.delete()
            except:
                return None
            frappe.db.commit()  # Commit each BOM deletion
        
        # Delete the item document
        try:
            item_doc.delete()
        except:
            return None
        frappe.db.commit()  # Commit the item deletion
        #print("Product deleted:",product)
    return None

def update_product_descriptions():
    # Get all items in the 'Products' item group
    products = frappe.get_all('Item', filters={'item_code': ['like', '4_%'], 'disabled': '0'}, fields=['name'])

    for product in products:
        product_name = product['name']
        
        # Get the default BOM for the item
        default_bom = frappe.db.get_value('BOM', {'item': product_name, 'is_default': 1, 'docstatus': 1}, 'name')
        
        if not default_bom:
            frappe.log_error(f"No default BOM found for product {product_name}")
            continue
        
        # Get the BOM items
        bom_items = frappe.get_all('BOM Item', filters={'parent': default_bom}, fields=['item_code'])
        
        if not bom_items:
            frappe.log_error(f"No items found in BOM {default_bom} for product {product_name}")
            continue
        
        for bom_item in bom_items:
            item_code = bom_item['item_code']
            
            # Get the item group of the BOM item
            item_group = frappe.db.get_value('Item', item_code, 'item_group')
            
            if item_group == 'Valve Head':
                # Get the description of the Valve Head item
                valve_head_description = frappe.db.get_value('Item', item_code, 'description')
                
                if valve_head_description:
                    # Update the product's description
                    frappe.db.set_value('Item', product_name, 'description', valve_head_description)
                    frappe.db.commit()
                    
                    frappe.msgprint(f"Updated description of product {product_name} with Valve Head description.")
                    break
                else:
                    frappe.log_error(f"Description not found for Valve Head item {item_code} in product {product_name}")
    
    return None

@frappe.whitelist()
def enqueue_main():
    frappe.enqueue("amf.amf.utils.product_master.fetch_items_with_pattern", queue='long', timeout=15000)
    return {'result': frappe._('Started main...')}

def fetch_items_with_pattern():
    patterns = ['%P200-O-%', '%P201-O-%', '%P100-O-%', '%P100-L-%']
    
    for pattern in patterns:
        print(f"Processing pattern: {pattern}")
        items = frappe.get_all('Item', filters={'item_code': ['like', pattern]}, fields=['name', 'item_code'])
        
        for item in items:
            # Check if the item is present in any Delivery Note
            delivery_note_item_exists = frappe.get_all('Delivery Note Item', filters={'item_code': item['item_code']})
            
            if delivery_note_item_exists:
                print(f"Item {item['item_code']} is present in a Delivery Note, skipping...")
                continue  # Skip processing for this item

            # Enable the item (set 'disabled' to 0)
            frappe.db.set_value('Item', item['name'], 'disabled', 0)
            
            active_boms = frappe.get_all('BOM', filters={'item': item['name']}, fields=['name'])
            
            for bom in active_boms:
                work_orders = frappe.get_all('Work Order', filters={'bom_no': bom['name'], 'docstatus': 1}, fields=['name', 'status'])
                
                for work_order in work_orders:
                    print(f"  Item: {item['item_code']}")
                    print(f"    BOM: {bom['name']}")
                    print(f"      Work Order: {work_order['name']} (Status: {work_order['status']})")
                    
                    job_cards = frappe.get_all('Job Card', filters={'work_order': work_order['name']}, fields=['name', 'status'])
                    print("        Job Cards:")
                    for job_card in job_cards:
                        print(f"          Job Card: {job_card['name']} (Status: {job_card['status']})")
                        job_card_doc = frappe.get_doc('Job Card', job_card['name'])
                        job_card_doc.cancel()
                        job_card_doc.delete()
                        print(f"          Job Card: {job_card['name']} has been cancelled.")
                    
                    stock_entries = frappe.get_all(
                        'Stock Entry',
                        filters={'work_order': work_order['name'], 'docstatus': 1},
                        fields=['name', 'purpose'],
                        order_by='creation desc'
                    )
                    print("        Stock Entries:")
                    for stock_entry in stock_entries:
                        print(f"          Stock Entry: {stock_entry['name']} (Purpose: {stock_entry['purpose']})")
                        stock_entry_doc = frappe.get_doc('Stock Entry', stock_entry['name'])
                        stock_entry_doc.cancel()
                        stock_entry_doc.delete()
                        print(f"          Stock Entry: {stock_entry['name']} has been cancelled.")
                
                    work_order_doc = frappe.get_doc('Work Order', work_order['name'])
                    work_order_doc.cancel()
                    work_order_doc.delete()
                    
                # frappe.db.set_value('BOM', bom['name'], 'is_active', 0)
                # frappe.db.set_value('BOM', bom['name'], 'is_default', 0)
                bom_doc = frappe.get_doc('BOM', bom['name'])
                
                try:
                    bom_doc.cancel()
                except Exception as e:
                    print(e)
                try:
                    bom_doc.delete()
                except Exception as e:
                    print(e)
                        
                
            item_doc = frappe.get_doc('Item', item['name'])
            try:
                item_doc.delete()
            except Exception as e:
                frappe.db.set_value('Item', item['name'], 'disabled', 1)
                print(e)
            frappe.db.commit()    
  



@frappe.whitelist()
def replace_description_enqueue():
    frappe.enqueue("amf.amf.utils.product_master.replace_word_in_item_description", queue='long', tiemout=15000)
    return {'result': frappe._('Started replace_description_enqueue...')}


def replace_word_in_item_description():
    # Fetch all items where item_code starts with '4_'
    items_product = frappe.get_all('Item', filters={'item_code': ['like', '4_%']}, fields=['name', 'description', 'internal_description'])
    items_head = frappe.get_all('Item', filters={'item_code': ['like', '3_%']}, fields=['name', 'description', 'internal_description'])

    items = items_product + items_head
    
    for item in items:
        # Check if 'Driver' is in the description
        if item.description:
            # Replace 'Driver' with 'Body'
            new_description = item.description.replace('Driver', 'Body')
            new_description = new_description.replace('material', 'Material')
            new_description = new_description.replace('size', 'Size')
            new_description = new_description.replace('ports', 'Ports')
            new_description = new_description.replace('stages', 'Stages')
            new_description = new_description.replace('type', 'Type')
            # Update the item description
            frappe.db.set_value('Item', item.name, 'description', new_description)
        if item.internal_description:
            # Replace 'Driver' with 'Body'
            new_internal_description = item.internal_description.replace('Driver', 'Body')
            # Update the item description
            frappe.db.set_value('Item', item.name, 'internal_description', new_internal_description)
        
        frappe.db.commit()

    return None            



