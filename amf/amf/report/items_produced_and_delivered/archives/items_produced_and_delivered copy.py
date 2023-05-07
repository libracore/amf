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
    return columns, data

# define columns
def get_columns():
    return [
        _("Item Group") + ":Link/Item Group:150",
        _("Quarter") + ":Data:100",
        _("Items Produced") + ":Int:150",
        _("Items Delivered") + ":Int:150",
    ]

# get data
def get_data(filters):
    conditions = ""

    if filters.get("quarter"):
        conditions += " AND CONCAT(YEAR(posting_date), ' Q', QUARTER(posting_date)) = %(quarter)s"

    # SQL query to fetch data
    query = f"""
        SELECT
            produced_items.item_group,
            produced_items.quarter,
            COALESCE(items_produced, 0) as items_produced,
            COALESCE(items_delivered, 0) as items_delivered
        FROM
            (
                SELECT
                    se_item.item_group,
                    CONCAT(YEAR(se.posting_date), ' Q', QUARTER(se.posting_date)) as quarter,
                    SUM(se_item.qty) as items_produced
                FROM `tabStock Entry` se
                JOIN `tabStock Entry Detail` se_item ON se.name = se_item.parent
                WHERE se.purpose = 'Manufacture'
                AND se_item.item_group IS NOT NULL AND se_item.item_group != ''
                AND se_item.item_group NOT IN ('parts', 'raw material', 'electronic boards')
                GROUP BY se_item.item_group, quarter
            ) produced_items
        LEFT JOIN
            (
                SELECT
                    dn_item.item_group,
                    CONCAT(YEAR(dn.posting_date), ' Q', QUARTER(dn.posting_date)) as quarter,
                    SUM(dn_item.qty) as items_delivered
                FROM `tabDelivery Note` dn
                JOIN `tabDelivery Note Item` dn_item ON dn.name = dn_item.parent
                WHERE dn_item.item_group IS NOT NULL AND dn_item.item_group != ''
                AND dn_item.item_group NOT IN ('parts', 'raw material', 'electronic boards')
                GROUP BY dn_item.item_group, quarter
            ) delivered_items
        ON produced_items.item_group = delivered_items.item_group
        AND produced_items.quarter = delivered_items.quarter
        WHERE 1 = 1 {conditions}
        ORDER BY quarter, item_group;
    """

    # execute the query and fetch the result
    data = frappe.db.sql(query, filters, as_list=True)
    return data

def get_filters():
    return [
        {
            "fieldname": "quarter",
            "label": _("Quarter"),
            "fieldtype": "Data",
            "options": "",
            "default": "",
            "width": "80",
        },
    ]
