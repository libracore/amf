# Copyright (c) 2013, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe

def execute(filters=None):
    columns, data = get_columns(), get_data(filters)
    return columns, data

def get_columns():
    return [
        {"fieldname": "item_group", "label": "Item Group", "fieldtype": "Data", "width": 150},
        {"fieldname": "purchased_qty", "label": "Purchased Quantity", "fieldtype": "Float", "width": 150},
        {"fieldname": "manufactured_qty", "label": "Manufactured Quantity", "fieldtype": "Float", "width": 180},
        {"fieldname": "percentage_manufactured", "label": "Percentage Manufactured Internally", "fieldtype": "Percent", "width": 200}
    ]

def get_data(filters):
    purchased_data = get_purchased_data(filters)
    manufactured_data = get_manufactured_data(filters)

    # Combine and calculate percentages
    combined_data = []
    for item_group in set([d['item_group'] for d in purchased_data] + [d['item_group'] for d in manufactured_data]):
        purchased_qty = next((d['delivered_qty'] for d in purchased_data if d['item_group'] == item_group), 0)
        manufactured_qty = next((d['total_manufactured_qty'] for d in manufactured_data if d['item_group'] == item_group), 0)
        total_qty = purchased_qty + manufactured_qty
        percentage_manufactured = (manufactured_qty / total_qty * 100) if total_qty else 0
        combined_data.append({
            "item_group": item_group,
            "purchased_qty": purchased_qty,
            "manufactured_qty": manufactured_qty,
            "percentage_manufactured": percentage_manufactured
        })
        
	# Process data to categorize by semester
    # combined_data = process_data_by_semester(purchased_data, manufactured_data)

    return combined_data

def process_data_by_semester(purchased_data, manufactured_data):
    # Logic to categorize and aggregate data by semester
    # Example: Create a dictionary to aggregate data
    semester_data = {}
    for entry in purchased_data + manufactured_data:
        year = entry['year']
        semester = "First" if entry['month'] <= 6 else "Second"
        key = f"{year} {semester}"
        
        if key not in semester_data:
            semester_data[key] = initialize_aggregate_data_structure()

        # Aggregate data in semester_data[key]
        # ...

    # Convert aggregated data into a list of dicts for ERPNext
    combined_data = []
    for key, value in semester_data.items():
        year, semester = key.split()
        combined_data.append({
            "year": year,
            "semester": semester,
            # ... other data fields
        })

    return combined_data

def initialize_aggregate_data_structure():
    # Initialize the structure with default values
    return {
        "purchased_qty": 0,
        "manufactured_qty": 0,
        # Any other fields you need to aggregate, initialized to default values
    }


def get_purchased_data(filters):
    query = """
        SELECT 
            it.item_group,
            SUM(pr_item.qty) AS delivered_qty
        FROM 
            `tabPurchase Receipt Item` pr_item
        JOIN 
            `tabPurchase Receipt` pr ON pr.name = pr_item.parent
        JOIN 
            `tabItem` it ON pr_item.item_code = it.item_code
        WHERE 
            pr.posting_date BETWEEN %(start_date)s AND %(end_date)s
            AND it.item_group IN %(item_groups)s
            AND pr.status != 'Cancelled'
        GROUP BY 
            it.item_group;
    """
    return frappe.db.sql(query, {"start_date": filters.get("start_date"), "end_date": filters.get("end_date"), "item_groups": filters.get("item_groups")}, as_dict=1)

def get_manufactured_data(filters):
    query = """
        SELECT 
            it.item_group,
            SUM(jc.total_completed_qty) AS total_manufactured_qty
        FROM 
            `tabJob Card` jc
        LEFT JOIN 
            `tabItem` it ON (jc.product_item = it.item_code OR jc.bom_no = it.default_bom)
        WHERE 
            jc.status = 'Completed'
            AND it.item_group IN %(item_groups)s
            AND jc.operation = 'CNC Machining'
            AND jc.posting_date BETWEEN %(start_date)s AND %(end_date)s
        GROUP BY 
            it.item_group;
    """
    return frappe.db.sql(query, {"start_date": filters.get("start_date"), "end_date": filters.get("end_date"), "item_groups": filters.get("item_groups")}, as_dict=1)
