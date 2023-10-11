from frappe import _
import frappe
from frappe.utils import add_months, getdate
import datetime

def execute(filters=None):
    columns = [
        {
            "fieldname": "month",
            "label": _("Month"),
            "fieldtype": "Data",
            "width": 120
        },
        {
            "fieldname": "stock_value",
            "label": _("Stock Variation"),
            "fieldtype": "Currency",
            "width": 120
        },
        {
            "fieldname": "revenue",
            "label": _("Revenue"),
            "fieldtype": "Currency",
            "width": 120
        },
        {
            "fieldname": "ratio",
            "label": _("Stock-Variation-to-Revenue Ratio"),
            "fieldtype": "Float",
            "width": 200,
            "precision": 1
        },
        {
			"fieldname": "custom_kpi",
			"label": _("Custom KPI"),
			"fieldtype": "Float",
			"width": 120,
			"precision": 1
		}
    ]
    
    # Initializing the start and end month
    start_date = getdate('2022-01-01')
    end_date = getdate('2023-08-31')

    stock_data = frappe.db.sql("""
        SELECT
            DATE_FORMAT(posting_date, '%%Y-%%m') as month,
            SUM(stock_value_difference) as stock_value
        FROM 
            `tabStock Ledger Entry`
        WHERE
            posting_date BETWEEN %s AND %s
        GROUP BY 
            month
        ORDER BY 
            month ASC
    """, (start_date, end_date), as_dict=1)

    revenue_data = frappe.db.sql("""
        SELECT
            DATE_FORMAT(posting_date, '%%Y-%%m') as month,
            SUM(grand_total) as revenue
        FROM 
            `tabSales Invoice`
        WHERE
            status = 'Paid' AND posting_date BETWEEN %s AND %s
        GROUP BY 
            month
        ORDER BY 
            month ASC
    """, (start_date, end_date), as_dict=1)

    # Initialize an empty list to store the data rows
    data = []
    current_date = start_date

    while current_date <= end_date:
        month = current_date.strftime('%Y-%m')
        row = {
            'month': month,
            'stock_value': 0,
            'revenue': 0,
            'ratio': 0  # Initialize ratio as 0
        }

        stock_value = next((d['stock_value'] for d in stock_data if d['month'] == month), None)
        if stock_value is not None:
            row['stock_value'] = stock_value

        revenue = next((d['revenue'] for d in revenue_data if d['month'] == month), None)
        if revenue is not None:
            row['revenue'] = revenue

        # Calculate the ratio; ensure we're not dividing by zero
        if row['revenue'] != 0:
            row['ratio'] = (row['stock_value'] / row['revenue'])*100.0
            
        # Calculate the custom KPI
        if row['revenue'] != 0:
            row['custom_kpi'] = row['ratio'] - 30  # Custom KPI

        data.append(row)
        
        current_date = add_months(current_date, 1)

    return columns, data
