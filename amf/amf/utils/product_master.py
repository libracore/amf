import re
import frappe
from amf.amf.utils.utilities import *
from amf.amf.utils.item_master6 import split_item_info

@frappe.whitelist()
def main():
    create_product_variant()
    return None

def create_product_variant():
    log = create_log_entry("Starting amf.amf.utils.product_master method...", "create_product_variant()")
    item_group = 'Products'
    
    # Fetch the item attributes
    attributes = frappe.get_all('Item Attribute', filters={'attribute_name': ['in', ['Driver', 'Valve Head', 'Syringe']]}, fields=['name'])
    
    # Initialize dictionaries to store attribute values
    drivers = []
    valve_heads = []
    syringes = []
    count=0
    
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
            if not (valve_head.startswith('V-S') or valve_head.startswith('V-O') or valve_head.startswith('V-B')):
                return False
        # P201-O, P200-O, P211-O, P221-O go with all valve heads but no syringes
        elif driver in ['P201-O', 'P200-O', 'P211-O', 'P221-O']:
                return 'RVM'
        return 'TRUE'
    
    group_digit = 4
    driver_digit = 0
    item_code=None
    # Create combinations
    for driver in drivers:
        driver_digit += 1
        for valve_head in valve_heads:
            head_code = frappe.db.get_value('Item', {'reference_code': valve_head}, 'item_code')
            head_digit = head_code[-2:]
            syringe_digit = 0
            for syringe in syringes:
                syringe_digit += 1
                if is_valid_combination(driver, valve_head, syringe) == 'RVM':
                    if item_code == f"{group_digit}{driver_digit}00{head_digit}":
                        continue
                    item_code = f"{group_digit}{driver_digit}00{head_digit}"
                    #print(item_code)
                    create_item(item_code, valve_head, driver)
                    update_log_entry(log, f"Created item: {item_code}")
                    count+=1
                elif is_valid_combination(driver, valve_head, syringe) == 'TRUE':
                    item_code = f"{group_digit}{driver_digit}{syringe_digit:02}{head_digit}"
                    #print(item_code)
                    create_item(item_code, valve_head, driver, syringe)
                    update_log_entry(log, f"Created item: {item_code}")
                    count+=1
                

    print(group_digit, driver_digit, syringe_digit, head_digit)
    print(count)
    
    return None

def create_item(pdt_code, valve_head, driver, syringe=None):
    def generate_info(head, new_ref_code, new_item_name, pdt_code, driver, syringe=None):
        if syringe:
            return f"""<div><strong>Code</strong>: {pdt_code}</div>
                    <div><strong>Reference</strong>: {new_ref_code}</div>
                    <div><strong>Name</strong>: {new_item_name}</div>
                    <div><strong>Group</strong>: 'Products'</div>
                    <div style="border-bottom: 1px solid lightgrey;"><strong>Components</strong></div>
                    <div><strong>Driver: </strong>{driver.item_code}</div>
                    <div><strong>Valve: </strong>{head.reference_code}</div>
                    <div><strong>Syringe: </strong>{syringe.item_code}</div>"""
        else:
            return f"""<div><strong>Code</strong>: {pdt_code}</div>
                    <div><strong>Reference</strong>: {new_ref_code}</div>
                    <div><strong>Name</strong>: {new_item_name}</div>
                    <div><strong>Group</strong>: 'Products'</div>
                    <div style="border-bottom: 1px solid lightgrey;"><strong>Components</strong></div>
                    <div><strong>Driver: </strong>{driver.item_code}</div>
                    <div><strong>Valve: </strong>{head.reference_code}</div>"""
    
    head = frappe.db.get_value('Item', {'reference_code': valve_head}, ['item_code', 'item_name', 'item_group', 'reference_code'], as_dict=1)
    syringe = frappe.db.get_value('Item', {'item_code': syringe}, ['item_code', 'item_name', 'item_group'], as_dict=1) if syringe else ''
    driver = frappe.db.get_value('Item', {'item_code': driver}, ['item_code', 'item_name', 'item_group'], as_dict=1)
    if syringe:
        new_ref_code = (f"{driver.item_code}{head.item_code}{syringe.item_code}").replace('-', '')
        new_item_name = f"{driver.item_code}/{head.reference_code}/{syringe.item_code}"
    else:
        new_ref_code = (f"{driver.item_code}{head.item_code}").replace('-', '')
        new_item_name = f"{driver.item_code}/{head.reference_code}"
    description = generate_info(head, new_ref_code, new_item_name, pdt_code, driver, syringe)

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
            'description': description,
            'item_defaults': [{
                'company': 'Advanced Microfluidics SA',
                'default_warehouse': 'Main Stock - AMF21'
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
            'has_serial_no': 1,
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

    ### LES CAPUCHONS A AJOUTER
         
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
        print(new_bom)
        print(f"An error occurred: {str(e)}")
            
    commit_database()
    #update_log_entry(log, f"Creation of: {item}")
    return None

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
