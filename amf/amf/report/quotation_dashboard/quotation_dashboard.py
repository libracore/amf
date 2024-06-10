import frappe
from frappe.utils import flt, date_diff, nowdate

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)

    return columns, data

def get_columns():
    return [
        {"label": "Quotation Name", "fieldname": "name", "fieldtype": "Link", "options": "Quotation", "width": 100},
        {"label": "Quotation To", "fieldname": "quotation_to", "fieldtype": "Data", "width": 100},
        {"label": "Customer Name", "fieldname": "customer_name", "fieldtype": "Data", "width": 200},
        {"label": "Transaction Date", "fieldname": "transaction_date", "fieldtype": "Date", "width": 100},
        {"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 100},
        {"label": "Valid Till", "fieldname": "valid_till", "fieldtype": "Date", "width": 100},
        {"label": "Order Type", "fieldname": "order_type", "fieldtype": "Data", "width": 70},
        {"label": "Total", "fieldname": "total", "fieldtype": "Currency", "width": 120},
        {"label": "W#", "fieldname": "weeks_after_transaction", "fieldtype": "Int", "width": 60},
        {"label": "Probability", "fieldname": "probability", "fieldtype": "Percent", "width": 100},
        {"label": "Act. Probability", "fieldname": "new_probability", "fieldtype": "Percent", "width": 100},
    ]

def get_data(filters):
    conditions = get_conditions(filters)
    #print("CIAO")
    #print(conditions)
    query = """
        SELECT
        	name,
            quotation_to,
            customer_name,
            transaction_date,
            status,
            valid_till,
            order_type,
            total,
            probability
        FROM
            `tabQuotation`
        WHERE
            docstatus = 1 AND status = 'Open' AND transaction_date BETWEEN '{0}' AND '{1}' {2}
    """.format(filters.get("from_date"), filters.get("to_date"), conditions)

    data = frappe.db.sql(query, as_dict=True)
    
    for row in data:
        row['weeks_after_transaction'] = date_diff(nowdate(), row['transaction_date']) // 7
        row['new_probability'] = calculate_new_probability(row['probability'], row['weeks_after_transaction'])
    
    return data

def get_conditions(filters):
    conditions = ""
    customer = filters.get("customer")
    order_type = filters.get("order_type")

    if customer:
        conditions += " AND customer_name = '{}'".format(customer)
    if order_type:
        conditions += " AND order_type = '{}'".format(order_type)
    
    return conditions


def calculate_new_probability(probability, weeks_after_transaction):
    if weeks_after_transaction == 1:
        return flt(probability) / 2
    elif weeks_after_transaction in [2, 3]:
        return flt(probability) * 2
    elif weeks_after_transaction == 4:
        return flt(probability) / 2
    else:
        # If the week is beyond week 4, we can decide to keep it the same as week 4
        return flt(probability) / 2
