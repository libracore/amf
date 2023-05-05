import frappe
from frappe.utils import add_months, get_last_day

def execute(filters=None):
    if not filters:
        filters = {}

    columns = get_columns()
    data = get_data(filters)
    return columns, data, None, None, get_filters()

def get_filters():
    return [
        {
            "fieldname": "item_code",
            "label": "Item Code",
            "fieldtype": "Link",
            "options": "Item",
            "default": "",
            "reqd": 0,
        },
        {
            "fieldname": "year",
            "label": "Year",
            "fieldtype": "Select",
            "default": "2022",
            "options": "\n2019\n2020\n2021\n2022\n2023",
            "reqd": 0,
        },
        {
            "fieldname": "quarter",
            "label": "Quarter",
            "fieldtype": "Select",
            "options": " \nQ1\nQ2\nQ3\nQ4",
            "default": "",
            "reqd": 0,
        }
    ]

def get_columns():
    return [
        "Item Code:Link/Item:150",
        "Item Name:Data:300",
        "Year:Data:60",
        "Quarter:Data:60",
        "Purchased:Int:100",
        "CNC Machining Job Cards:Int:150"
    ]

def get_data(filters):
    data = []
    print("filters:", filters);
    year_range = range(int(filters.get("year", 2019)), 2024)
    quarter_range = range(int(filters.get("quarter", "Q1")[1:]), 5)
    if filters.year:
        year_range = int(filters.get("year"))
        year_range = range(year_range, year_range+1)
        print("year_range in if:", year_range);
    if filters.quarter:
        quarter_range = int(filters.get("quarter")[1:])
        quarter_range = range(quarter_range, quarter_range+1)
        print("quarter_range in if:", quarter_range);
    item_code = filters.get("item_code", None)
    for year in year_range:
        for quarter in quarter_range:
            start_date, end_date = get_quarter_dates(year, quarter)
            items = frappe.get_all("Item", filters={"item_code": item_code} if item_code else {}, fields=["item_code", "item_name"])
            for item in items:
                purchased_qty = get_purchased_qty(item.item_code, start_date, end_date)
                cnc_machining_job_card_count = get_cnc_machining_job_card_count(item.item_code, start_date, end_date)
                data.append([item.item_code, item.item_name, year, f"Q{quarter}", purchased_qty, cnc_machining_job_card_count])
    return data


def get_quarter_dates(year, quarter):
    print("year in get:", year);
    start_month = (quarter - 1) * 3 + 1
    start_date = f"{year}-{start_month:02d}-01"
    print("start_date in get:", start_date);
    end_date = get_last_day(add_months(start_date, 2))
    print("end_date in get:", end_date);
    return start_date, end_date

def get_purchased_qty(item_code, start_date, end_date):
    purchase_qty = frappe.db.sql("""
        SELECT SUM(po_item.qty)
        FROM `tabPurchase Order Item` AS po_item
        JOIN `tabPurchase Order` AS po ON po_item.parent = po.name
        WHERE po_item.item_code = %s
        AND po.transaction_date BETWEEN %s AND %s
        AND po.docstatus = 1
    """, (item_code, start_date, end_date))[0][0] or 0

    return purchase_qty

def get_produced_qty(item_code, start_date, end_date):
    produced_qty = frappe.db.sql("""
        SELECT SUM(se_item.qty)
        FROM `tabStock Entry Detail` AS se_item
        JOIN `tabStock Entry` AS se ON se_item.parent = se.name
        WHERE se_item.item_code = %s
        AND se.posting_date BETWEEN %s AND %s
        AND se.purpose = 'Manufacture'
        AND se.docstatus = 1
    """, (item_code, start_date, end_date))[0][0] or 0
    
    return produced_qty


def get_cnc_machining_job_card_count(item_code, start_date, end_date):
    #frappe.msgprint(end_date);
    cnc_machining_job_card_count = frappe.db.sql("""
        SELECT sum(jc.for_quantity)
        FROM `tabJob Card` AS jc
        JOIN `tabWork Order` AS wo ON jc.work_order = wo.name
        WHERE wo.production_item = %s
        AND jc.posting_date BETWEEN %s AND %s
        AND jc.operation = 'CNC Machining'
        AND jc.docstatus = 1
    """, (item_code, start_date, end_date))[0][0] or 0

    return cnc_machining_job_card_count

