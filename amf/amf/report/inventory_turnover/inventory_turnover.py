# Copyright (c) 2013, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe

def execute(filters=None):
    if not filters:
        filters = {}

    company = filters.get('company', 'Advanced Microfluidics SA')  # Replace with default company name if needed

	# Define the half-year periods
    periods = [
        ("2022-01-01", "2022-06-30"),
        ("2022-07-01", "2022-12-31"),
        ("2023-01-01", "2023-06-30"),
        ("2023-07-01", "2023-12-31"),
        ("2024-01-01", "2024-06-30"),
        ("2024-07-01", "2024-12-31"),
        ("2025-01-01", "2025-06-30"),
        ("2025-07-01", "2025-12-31")
    ]

    # Preparing report data
    columns = get_columns()
    data = []
    
    for from_date, to_date in periods:
        # Calculate COGS and inventory for each period
        cogs = extract_cogs(from_date, to_date, company)
        opening_inventory, closing_inventory = extract_inventory_data(from_date, to_date, company)
        inventory_turnover_ratio = calculate_inventory_turnover_ratio(cogs, opening_inventory, closing_inventory)

        # Append the results for each period to the data list
        data.append({
            'from_date': from_date,
            'to_date': to_date,
            'cogs': cogs,
            'opening_inventory': opening_inventory,
            'closing_inventory': closing_inventory,
            'inventory_turnover_ratio': inventory_turnover_ratio
        })

    return columns, data

def get_columns():
    """Return the columns for the report"""
    columns = [
        {"label": "From Date", "fieldname": "from_date", "fieldtype": "Date", "width": 100},
        {"label": "To Date", "fieldname": "to_date", "fieldtype": "Date", "width": 100},
        {"label": "COGS", "fieldname": "cogs", "fieldtype": "Currency", "width": 120},
        {"label": "Opening Inventory", "fieldname": "opening_inventory", "fieldtype": "Currency", "width": 150},
        {"label": "Closing Inventory", "fieldname": "closing_inventory", "fieldtype": "Currency", "width": 150},
        {"label": "Inventory Turnover Ratio", "fieldname": "inventory_turnover_ratio", "fieldtype": "Float", "width": 180},
    ]
    return columns

def calculate_half_yearly_inventory_turnover(from_date, to_date, company):
    cogs = extract_cogs(from_date, to_date, company)
    opening_inventory, closing_inventory = extract_inventory_data(from_date, to_date, company)
    inventory_turnover_ratio = calculate_inventory_turnover_ratio(cogs, opening_inventory, closing_inventory)
    return inventory_turnover_ratio

def extract_cogs(from_date, to_date, company):
    # List of COGS related accounts
    cogs_accounts = [
        "4000 - Cost of material: UFM - AMF21",
		"4001 - Cost of material: LSP - AMF21",
		"4002 - Cost of material: SPM - AMF21",
		"4003 - Cost of material: RVM rotary valve - AMF21",
		"4004 - Cost of production tools and materials (e.g. bars) - AMF21",
		"4005 - Cost of packaging materials - AMF21",
		"4006 - Cost of general materials - AMF21",
		"4070 - Import fees (production) - AMF21",
		"4071 - Cost of customs duties (production) - AMF21",
		"4072 - Transport fees (production) - AMF21",
		"4295 - Supplier discount - AMF21",
		"4400 - Cost of third party services (production) - AMF21",
		"4401 - Importation de services de tiers pour la production - AMF21",
		"4900 - Stock variation - AMF21",
		"4901 - Accessory costs (production) - AMF21",
		"4998 - Capitalization of production materials and services - AMF21",
		"4011 - Cost of test instruments (R&D) - AMF21",
		"4012 - Cost of materials (R&D) - AMF21",
		"4013 - Cost of tools (R&D) - AMF21",
		"4014 - Cost of services (R&D) - AMF21",
		"4016 - Quality system - AMF21",
		"4470 - Import fees (R&D) - AMF21",
		"4471 - Cost of customs duties (R&D) - AMF21",
		"4472 - Transport fees (R&D) - AMF21"
    ]

    total_cogs = 0
    for account in cogs_accounts:
        cogs_entries = frappe.db.sql(
            """
            SELECT SUM(debit) - SUM(credit) as total
            FROM `tabGL Entry`
            WHERE account=%s AND company=%s AND posting_date BETWEEN %s AND %s
            GROUP BY account
            """,
            (account, company, from_date, to_date),
            as_dict=1,
        )
        total_cogs += cogs_entries[0].total if cogs_entries else 0
    
    return total_cogs

def extract_inventory_data(from_date, to_date, company):
    # Define the inventory related accounts (same as used in COGS calculation)
    inventory_accounts = [
		"1410 - Stock In Hand - AMF21",
		"1411 - Work In Progress Stock - AMF21",
		"1412 - Finished Goods Stock - AMF21",
		"1413 - External Stock - AMF21",
		"1414 - Demo Devices - AMF21",
		"1415 - Repair Stock - AMF21",
		"1416 - R&D Stock - AMF21",
		"1417 - Waste Stock - AMF21",
    ]
	
	# Calculate opening inventory
    opening_inventory_value = get_inventory_value(from_date, company, inventory_accounts, True)
    # Calculate closing inventory
    closing_inventory_value = get_inventory_value(to_date, company, inventory_accounts, False)

    return opening_inventory_value, closing_inventory_value

def get_inventory_value(date, company, inventory_accounts, is_opening):
    total_inventory = 0
    for account in inventory_accounts:
        inventory_entries = frappe.db.sql(
            """
            SELECT SUM(debit) - SUM(credit) as total
            FROM `tabGL Entry`
            WHERE account=%s AND company=%s AND posting_date {} %s
            """.format('<=' if is_opening else '<'),
            (account, company, date),
            as_dict=1,
        )
        if(inventory_entries[0].total):
            total_inventory += inventory_entries[0].total if inventory_entries else 0

    return total_inventory

def calculate_inventory_turnover_ratio(cogs, opening_inventory, closing_inventory):
    average_inventory = (opening_inventory + closing_inventory) / 2
    return cogs / average_inventory if average_inventory != 0 else 0