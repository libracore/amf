# -*- coding: utf-8 -*-
# Copyright (c) 2024, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document


class ItemCreation(Document):
	pass


@frappe.whitelist()
def populate_fields(head_name):
    """
    Fetch the value of 'head_name' and return the populated
    'seat_name' and 'plug_name' by extracting all characters after the first '-'.
    seat_name will exclude the last part of the string, plug_name will exclude the second-to-last part.
    """
    head_rnd = ""
    seat_name = ""
    plug_name = ""

    if head_name:
        try:
            # Extract the part after the first '-'
            parts = head_name.split('-', 1)
            if len(parts) > 1:
                # Full extracted part (everything after the first '-')
                extracted_part = parts[1]
                head_rnd = 'V-' + extracted_part
                # Split by '-' to get all sections
                sub_parts = extracted_part.split('-')

                # seat_name gets all but the last part
                seat_name = 'SEAT-' + '-'.join(sub_parts[:-1])  # Exclude the last part
                
                # plug_name gets all parts but excludes the second-to-last part
                if len(sub_parts) > 2:
                    plug_name = 'PLUG-' + '-'.join(sub_parts[:-2] + sub_parts[-1:])
                else:
                    plug_name = 'PLUG-' + '-'.join(sub_parts)  # Fallback in case fewer parts are present
            else:
                # Handle case where there is no '-' in head_name
                seat_name = head_name
                plug_name = head_name
                head_rnd = head_name
        except Exception as e:
            frappe.throw(f"Error in processing head_name: {str(e)}")

    # Return values for seat_name and plug_name
    return {
        "seat_name": seat_name,
        "plug_name": plug_name,
        "head_rnd": head_rnd
    }
    
@frappe.whitelist()
def get_last_item_code(code_body=None):
    """
    Fetch the last two digits from items in the 'Valve Seat', 'Valve Head', and 'Plug' item groups
    and return the highest two-digit number.
    """
    # Define the relevant item groups
    
    if code_body:
        item_groups = ['Products']
        # Query to find all item codes in the specified item groups
        items = frappe.db.sql("""
            SELECT item_code
            FROM `tabItem`
            WHERE item_group IN (%s)
            AND disabled = 0
            AND item_code REGEXP '^[0-9]{6}$'
        """, tuple(item_groups))
    else:
        item_groups = ['Valve Head', 'Valve Seat', 'Plug']
        # Query to find all item codes in the specified item groups
        items = frappe.db.sql("""
            SELECT item_code
            FROM `tabItem`
            WHERE item_group IN (%s, %s, %s)
            AND disabled = 0
            AND item_code REGEXP '^[0-9]{6}$'
        """, tuple(item_groups))
        
    # Variable to store the highest two-digit number
    highest_digit_number = None

    # Process each item and extract the last two digits
    for item in items:
        item_code = item[0]  # Assuming 'name' is the item code
        
        # Extract the last two digits from the item code (assumes the format allows this)
        if code_body:
            last_digits = item_code[-2:]  # Take the last two characters
        else:
            last_digits = item_code[-3:]
        
        # Check if the last two characters are numeric
        if last_digits.isdigit():
            last_digits = int(last_digits)
            
            # Compare to find the highest two-digit number
            if highest_digit_number is None or last_digits > highest_digit_number:
                highest_digit_number = last_digits

    # Return the highest two-digit number found, or throw an error if none found
    if highest_digit_number is not None:
        return highest_digit_number
    else:
        frappe.throw("No valid two-digit item codes found in the specified groups.")

@frappe.whitelist()
def create_item(doc, item_type):
    """
    Creates an item (plug, seat, valve head, or final product) based on the item_type provided.
    """
    doc = frappe._dict(doc)  # Convert the incoming doc to a dict format
    
    if item_type == 'plug':
        return create_plug(doc)
    elif item_type == 'seat':
        return create_seat(doc)
    elif item_type == 'valve_head':
        return create_valve_head(doc)
    elif item_type == 'final_product':
        return create_final_product(doc)
    else:
        frappe.throw("Invalid item type. Please specify 'plug', 'seat', 'valve_head', or 'final_product'.")

def create_plug(doc):
    # Logic for plug creation
    pass

def create_seat(doc):
    # Logic for seat creation
    pass

def create_valve_head(doc):
    # Logic for valve head creation
    pass

def create_final_product(doc):
    # Logic for final product creation
    pass
