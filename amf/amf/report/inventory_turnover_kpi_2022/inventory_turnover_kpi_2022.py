import frappe
from frappe.utils import flt, add_years

def execute(filters=None):
    columns, data = get_columns(), get_data(filters)
    return columns, data

def get_columns():
    return [
        "Item Code::150",
        "Item Name::150",
        "Cost of Goods Sold::150",
        "Average Inventory::150",
        "Inventory Turnover::150"
    ]

def get_data(filters):
    data = []
    start_date = '2022-01-01'
    end_date = '2022-12-31'

    items = frappe.get_all('Item', fields=['name', 'item_name'])

    for item in items:
        cogs = get_cogs(item.name, start_date, end_date)
        avg_inventory = get_average_inventory(item.name, start_date, end_date)
        inventory_turnover = flt(cogs) / flt(avg_inventory) if avg_inventory else 0

        data.append([item.name, item.item_name, cogs, avg_inventory, inventory_turnover])

    frappe.msgprint("COGS for {item_name}: {cogs}".format(item_code=item.name, cogs=cogs))
    frappe.msgprint("Average Inventory for {item_name}: {avg_inventory}".format(item_code=item.name, avg_inventory=avg_inventory))


    return data

def get_cogs(item_code, start_date, end_date):
    cogs = frappe.db.sql("""
        SELECT SUM(stock_value_difference)
        FROM `tabStock Ledger Entry`
        WHERE item_code = %s
        AND posting_date BETWEEN %s AND %s
        AND voucher_type = 'Sales Invoice'
    """, (item_code, start_date, end_date))

    return flt(cogs[0][0]) if cogs else 0

def get_average_inventory(item_code, start_date, end_date):
    opening_inventory = frappe.db.sql("""
        SELECT stock_value
        FROM `tabStock Ledger Entry`
        WHERE item_code = %s
        AND posting_date < %s
        ORDER BY posting_date DESC, creation DESC
        LIMIT 1
    """, (item_code, start_date))

    closing_inventory = frappe.db.sql("""
        SELECT stock_value
        FROM `tabStock Ledger Entry`
        WHERE item_code = %s
        AND posting_date <= %s
        ORDER BY posting_date DESC, creation DESC
        LIMIT 1
    """, (item_code, end_date))

    opening_stock_value = flt(opening_inventory[0][0]) if opening_inventory else 0
    closing_stock_value = flt(closing_inventory[0][0]) if closing_inventory else 0

    return (opening_stock_value + closing_stock_value) / 2
