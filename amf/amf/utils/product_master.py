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
        if syringe == 'None' or 'UFM' in syringe or 'XS' in valve_head:
            return False
        # P2XX- drivers do not take syringe
        if driver.startswith('P2'):
            return False
        # P1X drivers do not take V-S or V-O or V-B valve head
        if driver.startswith('P1') and (valve_head.startswith('V-S') or valve_head.startswith('V-O') or valve_head.startswith('V-B')):
            return False
        return True
    
    group_digit = 4
    driver_digit = 0
    # Create combinations
    for driver in drivers:
        driver_digit += 1
        for valve_head in valve_heads:
            head_code = frappe.db.get_value('Item', {'reference_code': valve_head}, 'item_code')
            head_digit = head_code[-2:]
            syringe_digit = 0
            for syringe in syringes:
                syringe_digit += 1
                if is_valid_combination(driver, valve_head, syringe):
                    item_code = f"{group_digit}{driver_digit}{syringe_digit:02}{head_digit}"
                    
                    create_item(item_code, valve_head, syringe, driver)
                    update_log_entry(log, f"Created item: {item_code}")
                    count+=1
    print(group_digit, driver_digit, syringe_digit, head_digit)
    print(count)
    
    return None

def create_item(pdt_code, valve_head, syringe, driver):
    def generate_info(head, new_ref_code, new_item_name, pdt_code, syringe, driver):
        return f"""<div><strong>Code</strong>: {pdt_code}</div>
                   <div><strong>Reference</strong>: {new_ref_code}.ASM</div>
                   <div><strong>Name</strong>: {new_item_name}</div>
                   <div><strong>Group</strong>: 'Products'</div>
                   <div style="border-bottom: 1px solid lightgrey;"><strong>Components</strong></div>
                   <div><strong>Driver: </strong>{driver.item_code}</div>
                   <div><strong>Valve: </strong>{head.reference_code}</div>
                   <div><strong>Syringe: </strong>{syringe.item_code}</div>"""
    
    head = frappe.db.get_value('Item', {'reference_code': valve_head}, ['item_code', 'item_name', 'item_group'], as_dict=1)
    syringe = frappe.db.get_value('Item', {'item_code': syringe}, ['item_code', 'item_name', 'item_group'], as_dict=1)
    driver = frappe.db.get_value('Item', {'item_code': driver}, ['item_code', 'item_name', 'item_group'], as_dict=1)
    new_ref_code = (f"{driver.item_code}{head.item_code}{syringe.item_code}").replace('-', '')
    new_item_name = f"{driver.item_code}/{head.item_name}/{syringe.item_code}"
    description = generate_info(head, new_ref_code, new_item_name, pdt_code, syringe, driver)

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
            'disabled': False,
            'country_of_origin': 'Switzerland',
            'sales_uom': 'Nos',
            'customs_tariff_number': '',
    }
    #print(new_item)
    create_document('Item', new_item)
    commit_database()
    
    bom_items = [
                {'item_code': driver.item_code, 'qty': 1},
                {'item_code': syringe.item_code, 'qty': 1},
                {'item_code': head.item_code, 'qty': 1},
            ]
            
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
        print(f"An error occurred: {str(e)}")
            
    commit_database()
    #update_log_entry(log, f"Creation of: {item}")
    return None