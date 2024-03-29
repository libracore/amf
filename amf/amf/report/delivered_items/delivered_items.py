import frappe
from frappe import _

def execute(filters=None):
    columns, data = get_columns(), get_data(filters)
    chart_data = get_chart_data(data, filters.get("item_code"))  # Pass the selected item code to get_chart_data

    chart = {
        "data": {
            "labels": [d["label"] for d in chart_data],
            "datasets": [
                {
                    "name": "Delivered Quantity",
                    "values": [d["value"] for d in chart_data],
                    "chartType": "bar",
                }
            ]
        },
        "type": "bar",
        "title": _("Total Delivered Quantity by Item"),
    }

    return columns, data, None, chart, None  # Add the chart data as the fifth return value


def get_chart_data(data, item_code=None):
    chart_data = []

    for row in data:
        item_code_row, item_group, year, quarter, delivered_qty, invoiced_amount = row
        label = "{item_code_row} ({item_group})".format(item_code_row=item_code_row, item_group=item_group)
        chart_data.append({"label": label, "value": delivered_qty, "year": year, "quarter": quarter})

    # Sort the data based on the total number of items delivered (descending) or quarter (ascending)
    if item_code:
        chart_data = sorted(chart_data, key=lambda x: x["quarter"])
    else:
        chart_data = sorted(chart_data, key=lambda x: x["value"], reverse=True)

    return chart_data



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
    item_code = filters.get("item_code")  # New filter for item_code

    if sum_quarters:
        group_by_clause = "GROUP BY item.item_group, sii.item_code, YEAR(si.posting_date)"
        quarter_column = "null AS quarter,"
    else:
        group_by_clause = "GROUP BY item.item_group, sii.item_code, YEAR(si.posting_date), QUARTER(si.posting_date)"
        quarter_column = "QUARTER(si.posting_date) AS quarter,"

    query = """
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
        """.format(quarter_column=quarter_column)

    if item_group:
        query += " AND item.item_group = '{item_group}'".format(item_group=item_group)

    if year:
        query += " AND YEAR(si.posting_date) = {year}".format(year=year)

    if item_code:  # Add the item_code filter condition to the query
        query += " AND sii.item_code = '{item_code}'".format(item_code=item_code)

    query += """
        {group_by_clause}
        ORDER BY YEAR(si.posting_date) DESC, item.item_group, sii.item_code
        """.format(group_by_clause=group_by_clause)

    data = frappe.db.sql(query, as_list=True)
    return data
