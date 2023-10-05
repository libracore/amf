import frappe
from frappe import _
from datetime import datetime

def execute(filters=None):
    print("def execute")
    if not filters:
        filters = {}

    columns = get_columns()
    data = get_data(filters)

    return columns, data

def get_columns():
    print("def get_columns")
    return [
        _("Customer") + ":Link/Customer:200",
        _("Sales Order Type") + ":Data:150",
        _("Percentage") + ":Percent:100",
        _("Sum of Delivery Notes") + ":Currency:150"
    ]

def get_data(filters):
    print("def get_data")
    # You might want to extract the month and year from the filters or use the current month by default
    month = filters.get("month") or datetime.now().month
    year = filters.get("year") or datetime.now().year

    month_name_to_number = {
        'January': 1, 'February': 2, 'March': 3, 'April': 4, 'May': 5, 'June': 6,
        'July': 7, 'August': 8, 'September': 9, 'October': 10, 'November': 11, 'December': 12
    }

    month_number = month_name_to_number[filters.get("month")]
    year_number = int(filters.get("year"))

    delivery_data = frappe.db.sql("""
    SELECT
        dn.customer_name,
        so.sales_order_type,
        COUNT(dn.name) AS count_delivery_notes,
        SUM(dn.grand_total) AS sum_delivery_notes
    FROM
        `tabDelivery Note` as dn
    JOIN
        `tabDelivery Note Item` as dni ON dn.name = dni.parent
    JOIN
        `tabSales Order` as so ON dni.against_sales_order = so.name
    WHERE
        MONTH(dn.posting_date) = %s AND YEAR(dn.posting_date) = %s
    GROUP BY
        dn.customer_name, so.sales_order_type
""", (month_number, year_number), as_dict=True)

    total_delivery_notes = sum([entry.count_delivery_notes for entry in delivery_data])

    # Now, calculate percentage and format data
    data = []
    for entry in delivery_data:
        percentage = (entry.count_delivery_notes / total_delivery_notes) * 100
        data.append([entry.customer_name, entry.sales_order_type, percentage, entry.sum_delivery_notes])

    return data
