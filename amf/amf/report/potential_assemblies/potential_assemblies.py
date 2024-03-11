# Copyright (c) 2013, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
import re

def execute(filters=None):
    columns = get_columns()
    data = get_potential_assemblies()
    return columns, data

def get_columns():
    """Define the columns for the custom report"""
    columns = [
        {"fieldname": "plug_ref", "label": "Plug Reference", "fieldtype": "Link", "options": "Item", "width": 150},
        {"fieldname": "seat_ref", "label": "Seat Reference", "fieldtype": "Link", "options": "Item", "width": 150},
        {"fieldname": "plug_qty", "label": "Plug Quantity", "fieldtype": "Float", "width": 110},
        {"fieldname": "seat_qty", "label": "Seat Quantity", "fieldtype": "Float", "width": 110},
        {"fieldname": "assembly_ref", "label": "Assembly Reference", "fieldtype": "Data", "width": 150},
        {"fieldname": "min_qty", "label": "Minimum Quantity", "fieldtype": "Float", "width": 200},
    ]
    return columns

def get_potential_assemblies():
    """Fetch all stock quantity of all plugs and all actual qty of valve seats and match references"""
    # Fetch plugs
    plug_query = """
        SELECT 
			i.item_name, 
			SUM(b.actual_qty) AS total_qty
		FROM 
			`tabBin` b
		JOIN 
			`tabItem` i ON b.item_code = i.item_code
		WHERE 
			i.item_group = 'Plug' AND 
			i.item_name RLIKE 'PLUG-' AND
			(b.warehouse = 'Main Stock - AMF21' OR b.warehouse = 'Assemblies - AMF21')
		GROUP BY 
			i.item_name
    """
    plugs = frappe.db.sql(plug_query, as_dict=True)
    #print(plugs)

    # Fetch seats
    seat_query = """
        SELECT 
			i.item_name, 
			SUM(b.actual_qty) AS total_qty
		FROM 
			`tabBin` b
		JOIN 
			`tabItem` i ON b.item_code = i.item_code
		WHERE 
			i.item_group = 'Valve Seat' AND 
			i.item_name RLIKE 'SEAT-' AND
			(b.warehouse = 'Main Stock - AMF21' OR b.warehouse = 'Assemblies - AMF21')
		GROUP BY 
			i.item_name
    """
    seats = frappe.db.sql(seat_query, as_dict=True)
    #print(seats)

    assemblies = []

    for plug in plugs:
        for seat in seats:
            if is_compatible(plug['item_name'], seat['item_name']):
                #assembly_ref = f"V-{plug['item_name'][5:]}-{seat['item_name'][-1]}"
                assembly_ref = f"V-{seat['item_name'][5:]}-{plug['item_name'][-1]}"
                min_qty = min(plug['total_qty'], seat['total_qty'])  # Calculate the minimum quantity
                #print(assembly_ref)
                assemblies.append({
                    'assembly_ref': assembly_ref,
                    'plug_ref': plug['item_name'],
                    'seat_ref': seat['item_name'],
                    'plug_qty': plug['total_qty'],
                    'seat_qty': seat['total_qty'],
                    'min_qty': min_qty
                })
    assemblies.sort(key=lambda x: x['assembly_ref'])
    return assemblies

def is_compatible(plug_ref, seat_ref):
    """Check if a plug and seat are compatible based on the reference patterns"""
    # Split the references to extract parts
    plug_parts = plug_ref.split('-')
    seat_parts = seat_ref.split('-')
    # Ensure arrays have enough parts to avoid index errors
    if len(plug_parts) < 6 or len(seat_parts) < 6:
        return False

    # Initial compatibility check based on A, B, C, XXX parts
    compatible = (plug_parts[1] == seat_parts[1]) and \
                 (plug_parts[2] == seat_parts[2]) and \
                 (plug_parts[3] == seat_parts[3]) and \
                 (plug_parts[4] == seat_parts[4])

    # Additional compatibility check for the variant (-C-P, -C-U, -K-P, -K-U)
    variant_compatible = False
    if plug_parts[5] == 'P' and seat_parts[5] in ['C', 'K']:
        variant_compatible = True
    elif plug_parts[5] == 'U' and seat_parts[5] in ['C', 'K']:
        variant_compatible = True

    return compatible and variant_compatible
