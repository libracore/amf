import frappe
from frappe import _
from frappe.utils import getdate, add_months

def execute(filters=None):
    filters = frappe._dict(filters or {})

    columns, data = get_columns(), get_data(filters)
    chart_data = prepare_chart_data(data, filters)

    return columns, data, chart_data

def get_columns():
    return [
        "Item Code:Link/Item:120",
        "Item Group:Link/Item Group:120",
        "Year:Data:60",
        "Quarter:Int:60",
        "Purchased:Int:90",
        "Produced:Int:90",
        "Delivered:Int:90"
    ]

def get_data(filters):
    conditions = build_conditions(filters)
    data = frappe.db.sql("""
        SELECT
            item_code, item_group, YEAR(posting_date) AS year,
            QUARTER(posting_date) AS quarter,
            SUM(CASE WHEN purpose = 'Material Receipt' THEN actual_qty ELSE 0 END) AS purchased,
            SUM(CASE WHEN purpose = 'Manufacture' THEN actual_qty ELSE 0 END) AS produced,
            SUM(CASE WHEN purpose = 'Delivery Note' THEN actual_qty ELSE 0 END) AS delivered
        FROM `tabStock Ledger Entry`
        WHERE {conditions}
        GROUP BY item_code, item_group, year, quarter
    """.format(conditions=conditions), filters, as_dict=1)

    return data

def build_conditions(filters):
    conditions = "1=1"

    if filters.item_code:
        conditions += " AND item_code = %(item_code)s"

    if filters.item_group:
        conditions += " AND item_group = %(item_group)s"

    if filters.year:
        conditions += " AND YEAR(posting_date) = %(year)s"

    return conditions

def prepare_chart_data(data, filters):
    chart_data = {
        'labels': ['Q1', 'Q2', 'Q3', 'Q4'],
        'datasets': [
            {'name': 'Purchased', 'values': [0, 0, 0, 0]},
            {'name': 'Produced', 'values': [0, 0, 0, 0]},
            {'name': 'Delivered', 'values': [0, 0, 0, 0]}
        ]
    }

    for row in data:
        idx = row.quarter - 1
        chart_data['datasets'][0]['values'][idx] += row.purchased
        chart_data['datasets'][1]['values'][idx] += row.produced
        chart_data['datasets'][2]['values'][idx] += row.delivered

    return chart_data
