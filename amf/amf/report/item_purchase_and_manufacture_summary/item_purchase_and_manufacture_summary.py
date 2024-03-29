import frappe
from frappe.utils import add_months, get_last_day

def execute(filters=None):
    if not filters:
        filters = {}

    columns = get_columns()
    data = get_data(filters)

    chart = get_chart(data)
    return columns, data, None, chart, get_filters()

def get_chart(data):
    labels = []
    purchased_data = []
    produced_data = []

    for row in data[:-1]:
        purchased_qty = row[4]
        produced_qty = row[5]

        # Check if both purchased and produced quantities are not 0
        if purchased_qty != 0 or produced_qty != 0:
            labels.append('{year} {quarter} ({item_code})'.format(year=row[2], quarter=row[3], item_code=row[0]))  # Year, Quarter, and Item Code
            purchased_data.append(purchased_qty)  # Purchased Quantity
            produced_data.append(produced_qty)  # CNC Machining Job Cards

    chart = {
        "data": {
            'labels': labels,
            'datasets': [
                {
                    'name': 'Purchased',
                    'values': purchased_data,
                    'chartType': 'bar'
                },
                {
                    'name': 'Produced',
                    'values': produced_data,
                    'chartType': 'bar'
                }
            ]
        },
        "type": 'bar',
        "height": 300,
    }

    return chart

def get_filters():
    return [
        {
            "fieldname": "item_group",
            "label": "Item Group",
            "fieldtype": "Link",
            "options": "Item Group",
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

    total_purchased_qty = 0
    total_cnc_machining_job_card_count = 0

    print("years:", year_range, "quarter:", quarter_range)
    item_group = filters.get("item_group", None)
    for year in year_range:
        for quarter in quarter_range:
            start_date, end_date = get_quarter_dates(year, quarter)
            items = frappe.get_all("Item", filters={"item_group": item_group} if item_group else {}, fields=["item_code", "item_name"])
            for item in items:
                purchased_qty = get_purchased_qty(item.item_code, start_date, end_date)
                cnc_machining_job_card_count = get_cnc_machining_job_card_count(item.item_code, start_date, end_date)
                total_purchased_qty += purchased_qty
                total_cnc_machining_job_card_count += cnc_machining_job_card_count
                data.append([item.item_code, item.item_name, year, "Q{quarter}".format(quarter=quarter), purchased_qty, cnc_machining_job_card_count])
    
    if total_purchased_qty > 0 or total_cnc_machining_job_card_count > 0:
        purchased_vs_produced_percentage = (total_cnc_machining_job_card_count / (total_purchased_qty + total_cnc_machining_job_card_count)) * 100
        data.append(["Total Produced", "{:.2f}%".format(purchased_vs_produced_percentage), "", "", total_purchased_qty, total_cnc_machining_job_card_count])
    
    return data


def get_quarter_dates(year, quarter):
    print("year in get:", year);
    start_month = (quarter - 1) * 3 + 1
    start_date = "{year}-{start_month:02d}-01".format(year=year, start_month=start_month)
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

