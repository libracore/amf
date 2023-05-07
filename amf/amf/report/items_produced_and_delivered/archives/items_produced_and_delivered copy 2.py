# imports
import frappe
from frappe import _
from frappe.utils import add_days, today

# function to fetch the data
def execute(filters=None):
    if not filters:
        filters = {}
        
    columns, data = [], []
    columns = get_columns()
    data = get_data(filters)
    return columns, data, None, get_filters()

# define columns
def get_columns():
    return [
        _("Item Group") + ":Link/Item Group:150",
        _("Items Produced") + ":Int:150",
        _("Items Delivered") + ":Int:150",
    ]

# get data
def get_data(filters):
    conditions = ""

    if filters.get("year"):
        conditions += " AND YEAR(posting_date) = %(year)s"
    if filters.get("quarter"):
        conditions += " AND QUARTER(posting_date) = %(quarter)s"

    # SQL query to fetch data
    query = f"""
        SELECT
            produced_items.item_group,
            COALESCE(items_produced, 0) as items_produced,
            COALESCE(items_delivered, 0) as items_delivered
        FROM
            (
                SELECT
                    se_item.item_group,
                    SUM(se_item.qty) as items_produced
                FROM `tabStock Entry` se
                JOIN `tabStock Entry Detail` se_item ON se.name = se_item.parent
                WHERE se.purpose = 'Manufacture'
                AND se_item.item_group IS NOT NULL AND se_item.item_group != ''
                AND se_item.item_group NOT IN ('parts', 'raw material', 'electronic boards') {conditions}
                GROUP BY se_item.item_group
            ) produced_items
        LEFT JOIN
            (
                SELECT
                    dn_item.item_group,
                    SUM(dn_item.qty) as items_delivered
                FROM `tabDelivery Note` dn
                JOIN `tabDelivery Note Item` dn_item ON dn.name = dn_item.parent
                WHERE dn_item.item_group IS NOT NULL AND dn_item.item_group != ''
                AND dn_item.item_group NOT IN ('parts', 'raw material', 'electronic boards') {conditions}
                GROUP BY dn_item.item_group
            ) delivered_items
        ON produced_items.item_group = delivered_items.item_group
        ORDER BY item_group;
    """

    # execute the query and fetch the result
    data = frappe.db.sql(query, filters, as_list=True)
    return data

def get_filters():
    return [
        {
            "fieldname": "year",
            "label": _("Year"),
            "fieldtype": "Select",
            "options": "2019\n2020\n2021\n2022\n2023",
            "default": "",
            "width": "40",
        },
        {
            "fieldname": "quarter",
            "label": _("Quarter"),
            "fieldtype": "Select",
            "options": "1\n2\n3\n4",
            "default": "",
            "width": "40",
        },
    ]
