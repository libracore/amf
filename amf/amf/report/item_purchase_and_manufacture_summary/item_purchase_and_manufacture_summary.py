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
            "default": "",
            "options": "\n2019\n2020\n2021\n2022\n2023",
            "reqd": 0,
        },
        {
            "fieldname": "quarter",
            "label": "Quarter",
            "fieldtype": "Select",
            "options": "\nQ1\nQ2\nQ3\nQ4",
            "default": "",
            "reqd": 0,
        }
    ]

def get_columns():
    return [
        "Item Code:Link/Item:150",
        "Item Name:Data:300",
        "Year:Data:100",
        "Quarter:Data:100",
        "Purchased:Int:100",
        "CNC Machining Job Cards:Int:150"
    ]

def get_data(filters):
    data = []
    print("filters:", filters);
    year_range = range(2019, 2024)
    if filters.get("year"):
        selected_year = int(filters["year"])
        year_range = range(selected_year, selected_year + 1)

    quarter_range = range(1, 5)
    if filters.get("quarter"):
        selected_quarter = int(filters["quarter"][1:])
        quarter_range = range(selected_quarter, selected_quarter + 1)

    print("years:", year_range, "quarter:", quarter_range)
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
        SELECT SUM(pri.qty)
        FROM `tabPurchase Receipt` AS pr
        JOIN `tabPurchase Receipt Item` AS pri ON pr.name = pri.parent
        WHERE pri.item_code = %s
        AND pr.posting_date BETWEEN %s AND %s
        AND pr.docstatus = 1
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
        SELECT sum(se.fg_completed_qty)
        FROM `tabStock Entry` AS se
        JOIN `tabWork Order` AS wo ON se.work_order = wo.name
        WHERE wo.production_item = %s
        AND se.modified BETWEEN %s AND %s
        AND se.docstatus = 1
    """, (item_code, start_date, end_date))[0][0] or 0

    return cnc_machining_job_card_count

