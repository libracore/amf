import frappe
from frappe import _

def execute(filters=None):
    columns, data = get_columns(), get_data(filters)
    return columns, data

def get_columns():
    return [
        _("Item Code") + ":Link/Item:300",
        _("Item Group") + ":Link/Item Group:200",
        _("Year") + ":Int:100",
        _("Quarter") + ":Int:100",
        _("Delivered Quantity") + ":Int:200",
        _("Invoiced Amount") + ":Currency:250"
    ]

def get_data(filters):
    item_group = filters.get("item_group")
    year = filters.get("year")
    sum_quarters = filters.get("sum_quarters")

    if sum_quarters:
        group_by_clause = "GROUP BY item.item_group, sii.item_code, YEAR(si.posting_date)"
        quarter_column = "null AS quarter,"
    else:
        group_by_clause = "GROUP BY item.item_group, sii.item_code, YEAR(si.posting_date), QUARTER(si.posting_date)"
        quarter_column = "QUARTER(si.posting_date) AS quarter,"

    query = f"""
        SELECT
            sii.item_code,
            item.item_group,
            YEAR(si.posting_date) AS year,
            {quarter_column}
            SUM(sii.qty) AS delivered_qty,
            SUM(sii.amount) AS invoiced_amount
        FROM `tabSales Invoice` AS si
        JOIN `tabSales Invoice Item` AS sii ON sii.parent = si.name
        JOIN `tabItem` AS item ON item.item_code = sii.item_code
        WHERE si.docstatus = 1
        """

    if item_group:
        query += f" AND item.item_group = '{item_group}'"

    if year:
        query += f" AND YEAR(si.posting_date) = {year}"

    query += f"""
        {group_by_clause}
        ORDER BY YEAR(si.posting_date) DESC, item.item_group, sii.item_code
        """

    data = frappe.db.sql(query, as_list=True)
    return data