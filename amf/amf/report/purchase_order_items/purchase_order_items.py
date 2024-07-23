import frappe
from frappe import _

def execute(filters=None):
    columns, data = get_columns(), get_data(filters)
    return columns, data

def get_columns():
    return [
        _("Item Code") + ":Link/Item:200",
        _("Item Name") + "::300",
        _("UOM") + "::100",
        _("Last Purchase Rate") + ":Currency:150",
        _("Previous Purchase Rate") + ":Currency:150",
        _("Rate Change (Last/Previous)") + "::150"
    ]

def get_data(filters):
    item_group = filters.get("item_group")
    item_code = filters.get("item_code")

    receipt_query = """
        SELECT
            pri.item_code,
            item.item_name,
            pri.uom,
            pri.conversion_factor,
            pri.rate / pri.conversion_factor AS normalized_rate,
            pr.posting_date
        FROM `tabPurchase Receipt Item` pri
        JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
        JOIN `tabItem` item ON item.item_code = pri.item_code
        WHERE pr.docstatus = 1
        AND YEAR(pr.posting_date) >= 2022
        AND item.item_group NOT IN ('Valve Seat', 'Plug', 'Valve Head', 'Generic Items')
    """

    if item_group:
        receipt_query += " AND item.item_group = '{item_group}'".format(item_group=item_group)

    if item_code:
        receipt_query += " AND pri.item_code = '{item_code}'".format(item_code=item_code)

    receipt_query += """
        ORDER BY pri.item_code, pr.posting_date DESC
    """

    receipt_data = frappe.db.sql(receipt_query, as_dict=True)

    order_query = """
        SELECT
            poi.item_code,
            item.item_name,
            poi.uom,
            poi.conversion_factor,
            poi.rate / poi.conversion_factor AS normalized_rate,
            po.transaction_date AS posting_date
        FROM `tabPurchase Order Item` poi
        JOIN `tabPurchase Order` po ON po.name = poi.parent
        JOIN `tabItem` item ON item.item_code = poi.item_code
        WHERE po.docstatus = 1
        AND YEAR(po.transaction_date) >= 2022
        AND item.item_group NOT IN ('Valve Seat', 'Plug', 'Valve Head', 'Generic Items')
    """

    if item_group:
        order_query += " AND item.item_group = '{item_group}'".format(item_group=item_group)

    if item_code:
        order_query += " AND poi.item_code = '{item_code}'".format(item_code=item_code)

    order_query += """
        ORDER BY poi.item_code, po.transaction_date DESC
    """

    order_data = frappe.db.sql(order_query, as_dict=True)

    # Combine receipt and order data
    item_data = {}
    for row in receipt_data + order_data:
        item_code = row['item_code']
        if item_code not in item_data:
            item_data[item_code] = {
                "item_code": row['item_code'],
                "item_name": row['item_name'],
                "uom": row['uom'],
                "last_rate": row['normalized_rate'],
                "previous_rate": None
            }
        elif item_data[item_code]["previous_rate"] is None:
            item_data[item_code]["previous_rate"] = row['normalized_rate']

    result = []
    for item in item_data.values():
        if item["previous_rate"] and item["previous_rate"] != 0:
            rate_change = round(item["last_rate"] / item["previous_rate"], 2)
        else:
            rate_change = None
        result.append([
            item["item_code"],
            item["item_name"],
            item["uom"],
            item["last_rate"],
            item["previous_rate"],
            rate_change
        ])

    return result
