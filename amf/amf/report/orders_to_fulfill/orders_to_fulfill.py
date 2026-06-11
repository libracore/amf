# Copyright (c) 2013-2022, bnovate, libracore and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import itertools

import frappe
from frappe import _
from frappe.utils import cint, formatdate


COLOURS = [
    "black", "#6660A9", "#297045", "#CC5A2B",
    "#FF5733", "#C70039", "#900C3F", "#581845",
    "#3498DB", "#2ECC71", "#F1C40F", "#8E44AD",
    "#2C3E50", "#F39C12", "#D35400", "#1ABC9C",
]

INDICATOR_COLOURS = {
    "Draft": "red",
    "To Deliver": "orange",
    "To Loan": "orange",
    "Partly Loaned": "orange",
    "Submitted": "orange",
    "Overdue": "red",
}


def execute(filters=None):
    filters = frappe._dict(filters or {})
    columns = get_columns()
    data = get_data(filters)
    chart = None

    return columns, data, chart


def get_columns():
    return [
        {'fieldname': 'weeknum', 'fieldtype': 'Data', 'label': _('Week'), 'width': 60},
        {'fieldname': 'indicator', 'fieldtype': 'Data', 'label': _('Status'), 'width': 100},
        {'fieldname': 'order', 'fieldtype': 'Dynamic Link', 'label': _('Order'), 'options': 'order_type', 'width': 110},
        {'fieldname': 'party', 'fieldtype': 'Dynamic Link', 'label': _('Party'), 'options': 'party_type', 'width': 90},
        {'fieldname': 'party_name', 'fieldtype': 'Data', 'label': _('Party Name'), 'width': 165},
        {'fieldname': 'ship_date', 'fieldtype': 'Data', 'label': _('Fulfill Date'), 'width': 90},
        {'fieldname': 'of', 'fieldtype': 'Data', 'label': _('OF'), 'width': 20},
        {'fieldname': 'dn', 'fieldtype': 'Check', 'label': _('DN'), 'width': 20},
        {'fieldname': 'remaining_qty', 'fieldtype': 'Float', 'label': _('Qty to Fulfill'), 'width': 100},
        {'fieldname': 'uom', 'fieldtype': 'Link', 'label': _('UOM'), 'options': 'UOM', 'width': 65},
        {'fieldname': 'item_code', 'fieldtype': 'Link', 'label': _('Item code'), 'options': 'Item', 'width': 300},
        {'fieldname': 'item_name', 'fieldtype': 'Data', 'label': _('Item name'), 'width': 300},
        {'fieldname': 'unit_price', 'fieldtype': 'Currency', 'label': _('Rate'), 'width': 120},
    ]


def get_data(filters):
    data = get_sales_order_items(filters)

    if cint(filters.get("include_loans", 1)):
        data.extend(get_loan_order_items(filters))

    set_sales_order_markers(data)
    sort_data(data)
    apply_order_group_markers(data)
    decorate_rows(data)

    return data


def get_sales_order_items(filters):
    conditions = get_common_item_conditions(filters, "so", "soi", "it")
    conditions.extend([
        "so.per_delivered < 100",
        "soi.qty > soi.delivered_qty",
        "so.status != 'Closed'",
        "(so._user_tags NOT LIKE \"%%template%%\" OR so._user_tags IS NULL)",
    ])

    if cint(filters.get("include_drafts")):
        conditions.insert(0, "so.docstatus <= 1")
    else:
        conditions.insert(0, "so.docstatus = 1")

    sql_query = """
    SELECT * FROM (
        SELECT
            soi.name,
            soi.name as sales_order_item,
            'Sales Order' as order_type,
            WEEK(soi.delivery_date) as weeknum,
            soi.parent as `order`,
            soi.parent as sort_order,
            'Customer' as party_type,
            so.customer as party,
            so.customer_name as party_name,
            soi.qty as qty,
            (soi.qty - soi.delivered_qty) AS remaining_qty,
            soi.delivery_date as delivery_date,
            soi.item_code as item_code,
            it.item_name as item_name,
            it.item_group as item_group,
            soi.uom as uom,
            soi.rate as unit_price,
            FALSE as is_packed_item,
            soi.idx as idx,
            so.docstatus as docstatus,
            so.status as order_status,
            '' as of,
            0 as dn
        FROM `tabSales Order Item` as soi
        JOIN `tabSales Order` as so ON soi.parent = so.name
        JOIN `tabItem` as it ON soi.item_code = it.name
        WHERE {conditions}

        UNION ALL

        SELECT
            soi.name,
            soi.name as sales_order_item,
            '' as order_type,
            WEEK(soi.delivery_date) as weeknum,
            NULL as `order`,
            soi.parent as sort_order,
            NULL as party_type,
            NULL as party,
            NULL as party_name,
            pi.qty as qty,
            (soi.qty - soi.delivered_qty) * (pi.qty / NULLIF(soi.qty, 0)) AS remaining_qty,
            soi.delivery_date as delivery_date,
            pi.item_code as item_code,
            pi.item_name as item_name,
            it.item_group as item_group,
            pi.uom as uom,
            soi.rate as unit_price,
            TRUE as is_packed_item,
            pi.idx as idx,
            so.docstatus as docstatus,
            so.status as order_status,
            '' as of,
            0 as dn
        FROM `tabSales Order Item` as soi
        JOIN `tabSales Order` as so ON soi.parent = so.name
        JOIN `tabPacked Item` as pi ON soi.name = pi.parent_detail_docname
        JOIN `tabItem` as it on pi.item_code = it.name
        WHERE {conditions}
    ) as united
    """.format(conditions=" AND ".join(conditions))

    return frappe.db.sql(sql_query, {"company": filters.get("company")}, as_dict=True)


def get_loan_order_items(filters):
    if not frappe.db.exists("DocType", "Loan Order"):
        return []

    conditions = get_common_item_conditions(filters, "lo", "loi", "it")
    conditions.extend([
        "lo.status NOT IN ('Closed', 'Cancelled', 'Returned')",
        "(loi.qty - IFNULL(loi.loaned_qty, 0)) > 0",
    ])

    if cint(filters.get("include_drafts")):
        conditions.insert(0, "lo.docstatus <= 1")
    else:
        conditions.insert(0, "lo.docstatus = 1")

    sql_query = """
        SELECT
            loi.name,
            NULL as sales_order_item,
            'Loan Order' as order_type,
            WEEK(lo.transaction_date) as weeknum,
            lo.name as `order`,
            lo.name as sort_order,
            lo.party_type as party_type,
            lo.party as party,
            lo.party_name as party_name,
            loi.qty as qty,
            (loi.qty - IFNULL(loi.loaned_qty, 0)) as remaining_qty,
            lo.transaction_date as delivery_date,
            loi.item_code as item_code,
            COALESCE(loi.item_name, it.item_name) as item_name,
            it.item_group as item_group,
            loi.uom as uom,
            loi.declared_rate as unit_price,
            FALSE as is_packed_item,
            loi.idx as idx,
            lo.docstatus as docstatus,
            lo.status as order_status,
            '' as of,
            0 as dn
        FROM `tabLoan Order Item` loi
        JOIN `tabLoan Order` lo ON loi.parent = lo.name
        JOIN `tabItem` it ON loi.item_code = it.name
        WHERE {conditions}
    """.format(conditions=" AND ".join(conditions))

    return frappe.db.sql(sql_query, {"company": filters.get("company")}, as_dict=True)


def get_common_item_conditions(filters, parent_alias, item_alias, item_master_alias):
    conditions = []

    if cint(filters.get("only_manufacturing")):
        conditions.append("{0}.include_item_in_manufacturing = 1".format(item_master_alias))

    if cint(filters.get("remove_gx")):
        conditions.append("{0}.item_code NOT LIKE 'GX%%'".format(item_alias))

    if filters.get("company"):
        conditions.append("{0}.company = %(company)s".format(parent_alias))

    return conditions


def set_sales_order_markers(data):
    sales_items = get_rendered_sales_order_items(data)
    work_order_map = get_work_order_map(sales_items)
    delivery_note_map = get_draft_delivery_note_map(sales_items.keys())

    for row in data:
        sales_order_item = row.get("sales_order_item")
        if not sales_order_item:
            continue

        row["of"] = work_order_map.get(sales_order_item, "")
        row["dn"] = 1 if delivery_note_map.get(sales_order_item) else 0


def get_rendered_sales_order_items(data):
    sales_items = {}
    for row in data:
        sales_order_item = row.get("sales_order_item")
        if sales_order_item and not row.get("is_packed_item"):
            sales_items[sales_order_item] = {
                "sales_order": row.get("sort_order"),
                "item_code": row.get("item_code"),
            }
    return sales_items


def get_work_order_map(sales_items):
    sales_orders = list(set([row["sales_order"] for row in sales_items.values() if row.get("sales_order")]))
    item_codes = list(set([row["item_code"] for row in sales_items.values() if row.get("item_code")]))

    if not sales_orders or not item_codes:
        return {}

    work_orders = frappe.get_all(
        "Work Order",
        filters={
            "production_item": ("in", item_codes),
            "sales_order": ("in", sales_orders),
            "docstatus": ("<=", 1),
        },
        fields=["name", "sales_order", "sales_order_item", "production_item", "docstatus", "status"],
    )

    sales_items_by_order_and_item = {}
    for sales_order_item, row in sales_items.items():
        key = (row.get("sales_order"), row.get("item_code"))
        sales_items_by_order_and_item.setdefault(key, []).append(sales_order_item)

    work_order_map = {}
    precedence = {"D": 1, "P": 2, "T": 3}

    for work_order in work_orders:
        candidates = []
        if work_order.get("sales_order_item") in sales_items:
            candidates = [work_order.get("sales_order_item")]
        else:
            key = (work_order.get("sales_order"), work_order.get("production_item"))
            candidates = sales_items_by_order_and_item.get(key, [])

        label = get_work_order_label(work_order)
        for sales_order_item in candidates:
            existing = work_order_map.get(sales_order_item)
            if existing and precedence[label] <= precedence[existing]:
                continue
            work_order_map[sales_order_item] = label

    return work_order_map


def get_work_order_label(work_order):
    if work_order.get("status") == "Completed":
        return "T"
    if cint(work_order.get("docstatus")) == 0:
        return "D"
    return "P"


def get_draft_delivery_note_map(sales_order_items):
    sales_order_items = list(sales_order_items)
    if not sales_order_items:
        return {}

    delivery_note_items = frappe.get_all(
        "Delivery Note Item",
        filters={"so_detail": ("in", sales_order_items)},
        fields=["parent", "so_detail"],
    )
    if not delivery_note_items:
        return {}

    delivery_note_names = list(set([row["parent"] for row in delivery_note_items]))
    draft_delivery_notes = frappe.get_all(
        "Delivery Note",
        filters={"name": ("in", delivery_note_names), "docstatus": 0},
        fields=["name"],
    )
    draft_delivery_note_names = set([row["name"] for row in draft_delivery_notes])

    return {
        row["so_detail"]: True
        for row in delivery_note_items
        if row["parent"] in draft_delivery_note_names
    }


def sort_data(data):
    data.sort(key=lambda row: (
        str(row.get("delivery_date") or ""),
        row.get("sort_order") or row.get("order") or "",
        cint(row.get("is_packed_item")),
        cint(row.get("idx")),
    ))


def apply_order_group_markers(data):
    last_order = None
    group_index = -1

    for row in data:
        order = row.get("sort_order") or row.get("order") or ""
        is_new_order = order != last_order

        if is_new_order:
            group_index += 1
            last_order = order

        row["order_group_index"] = group_index
        row["order_group_start"] = 1 if is_new_order else 0


def decorate_rows(data):
    week_colours = itertools.cycle(COLOURS)
    day_colours = itertools.cycle(COLOURS)
    last_week_num = ''
    last_day = ''
    week_colour = next(week_colours)
    day_colour = next(day_colours)

    for row in data:
        if row.get("weeknum") != last_week_num:
            week_colour = next(week_colours)
            last_week_num = row.get("weeknum")

        if row.get("delivery_date") != last_day:
            day_colour = next(day_colours)
            last_day = row.get("delivery_date")

        row["weeknum"] = get_coloured_value(row.get("weeknum"), week_colour)
        row["ship_date"] = get_coloured_value(format_report_date(row.get("delivery_date")), day_colour)

        if row.get("is_packed_item"):
            row["indent"] = 1
            row["weeknum"] = ""
            row["ship_date"] = ""
        else:
            row["indent"] = 0
            row["item_name"] = "<b>{0}</b>".format(row.get("item_name") or "")

        row["indicator"] = get_status_indicator(row)


def get_coloured_value(value, colour):
    if value in (None, ""):
        return ""
    return "<span style='color:{0}!important;font-weight:bold;'>{1}</span>".format(colour, value)


def format_report_date(value):
    if not value:
        return ""
    return formatdate(value, "dd-mm-yyyy")


def get_status_indicator(row):
    label = get_status_label(row)
    colour = INDICATOR_COLOURS.get(label, "orange")
    return '<span class="indicator whitespace-nowrap {0}"><span>{1}</span></span>'.format(colour, _(label))


def get_status_label(row):
    if cint(row.get("docstatus")) == 0:
        return "Draft"
    if row.get("order_type") == "Loan Order":
        return "To Loan" if row.get("order_status") == "Submitted" else row.get("order_status")
    return "To Deliver"


def get_chart(filters):
    filters = frappe._dict(filters or {})
    conditions = get_common_item_conditions(filters, "so", "soi", "it")
    conditions.extend([
        "so.status != 'Closed'",
        "soi.qty > soi.delivered_qty",
        "(so._user_tags NOT LIKE \"%%template%%\" OR so._user_tags IS NULL)",
    ])

    if cint(filters.get("include_drafts")):
        conditions.insert(0, "so.docstatus <= 1")
    else:
        conditions.insert(0, "so.docstatus = 1")

    sql_query = """
SELECT
    WEEK(soi.delivery_date) as weeknum,
    SUBDATE(soi.delivery_date, WEEKDAY(soi.delivery_date)) as week,
    SUM(soi.qty - soi.delivered_qty) AS remaining_qty,
    it.item_group as item_group
FROM `tabSales Order Item` as soi
JOIN `tabSales Order` as so ON soi.parent = so.name
JOIN `tabItem` as it on soi.item_code = it.name
WHERE {conditions}
GROUP BY week, item_group
ORDER BY week ASC
    """.format(conditions=" AND ".join(conditions))

    data = frappe.db.sql(sql_query, {"company": filters.get("company")}, as_dict=True)
    
    # Build dict of arrays, that store the sum of items in each group, each week.
    weeks = sorted(set([it['week'] for it in data]))
    groups = sorted(set([it['item_group'] for it in data]))
    plotdata = {}

    for g in groups:
        plotdata[g] = [0] * len(weeks)

    for item in data:
        week, group, qty = item['week'], item['item_group'], item['remaining_qty']
        plotdata[group][weeks.index(week)] += qty

    # Convert to format expected by Frappe charts
    datasets = []
    for group in plotdata.keys():
        datasets.append({
            "name": ellipsis(group, 12),
            "values": plotdata[group],
        })
    
    chart = {
        "data": {
            "labels": [w.strftime("(W%V) %d-%m-%Y") for w in weeks],
            "datasets": datasets,
        },
        "type": 'bar',
        "barOptions": {
            "stacked": True,
            "spaceRatio": 0.1,
        },
        "title": "Total items per week",
    }
    return chart
    
    
### Helpers

def ellipsis(text, length=10):
    if len(text) <= length:
        return text
    return text[:int(length/2)-1] + "…" + text[-int(length/2):]
