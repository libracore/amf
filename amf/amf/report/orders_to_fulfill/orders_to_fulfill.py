# Copyright (c) 2013-2022, bnovate, libracore and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
import textwrap
import itertools
from frappe import _

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    message = "Test message"
    chart = get_chart(filters)
    
    return columns, data, message, chart

def get_columns():
    return [
        {'fieldtype': 'Data', 'label': '', 'width': 20},
        {'fieldname': 'weeknum', 'fieldtype': 'Data', 'label': _('Week'), 'width': 80},
        {'fieldname': 'parent', 'fieldtype': 'Link', 'label': _('Sales Order'), 'options': 'Sales Order', 'width': 90},
        {'fieldname': 'indicator', 'fieldtype': 'Data', 'label': _('Status'), 'width': 90},
        {'fieldname': 'customer', 'fieldtype': 'Link', 'label': _('Customer'), 'options': 'Customer', 'width': 80},
        {'fieldname': 'customer_name', 'fieldtype': 'Data', 'label': _('Customer Name'), 'width': 150},
        {'fieldname': 'ship_date', 'fieldtype': 'Data', 'label': _('Ship date'), 'width': 80},
        # {'fieldname': 'qty', 'fieldtype': 'Int', 'label': _('Qty Ordered'), 'width': 100}, 
        {'fieldname': 'remaining_qty', 'fieldtype': 'Int', 'label': _('Qty to Deliver'), 'width': 100}, 
        {'fieldname': 'item_code', 'fieldtype': 'Link', 'label': _('Item code'), 'options': 'Item', 'width': 300},
        {'fieldname': 'item_name', 'fieldtype': 'Data', 'label': _('Item name'), 'width': 300},
        {'fieldname': 'item_group', 'fieldtype': 'Link', 'label': _('Item group'), 'options': 'Item Group', 'width': 150},
        # {'fieldname': 'status', 'fieldtype': 'Data', 'label': _('Status'), 'width': 100}
    ]
    
def get_data(filters):
    
    status_filter = "so.docstatus = 1 AND"
    if filters.include_drafts:
        status_filter = "so.docstatus <= 1 AND" # include drafts and submitted.

    extra_filters = ""
    if filters.only_manufacturing:
        extra_filters += "AND it.include_item_in_manufacturing = 1"
    
    sql_query = """
SELECT * FROM ((
    SELECT
        soi.name,
        WEEK(soi.delivery_date) as weeknum,
        soi.parent as parent,
        so.customer as customer,
        so.customer_name as customer_name,
        soi.qty as qty,
        (soi.qty - soi.delivered_qty) AS remaining_qty,
        soi.delivery_date as delivery_date,
        soi.item_code as item_code,
        it.item_name as item_name,
        it.item_group as item_group,
        FALSE as is_packed_item,
        soi.idx as idx,
        so.docstatus as docstatus
    FROM `tabSales Order Item` as soi
    JOIN `tabSales Order` as so ON soi.parent = so.name
    JOIN `tabItem` as it ON soi.item_code = it.name
    WHERE
        {status_filter}
        so.per_delivered < 100 AND
        soi.qty > soi.delivered_qty AND
        so.status != 'Closed' AND
        (so._user_tags NOT LIKE "%template%" OR so._user_tags IS NULL)
        {extra_filters}
) UNION (
    SELECT
        soi.name,
        WEEK(soi.delivery_date) as weeknum,
        NULL as parent,
        NULL as customer,
        NULL as customer_name,
        pi.qty as qty,
        (soi.qty - soi.delivered_qty) * (pi.qty / soi.qty) AS remaining_qty,
        soi.delivery_date as delivery_date,
        pi.item_code as item_code,
        pi.item_name as item_name,
        NULL as item_group,
        TRUE as is_packed_item,
        pi.idx as idx,
        so.docstatus as docstatus
    FROM `tabSales Order Item` as soi
    JOIN `tabSales Order` as so ON soi.parent = so.name
    JOIN `tabItem` as it on soi.item_code = it.name
    JOIN `tabPacked Item` as pi ON soi.name = pi.parent_detail_docname
    WHERE
        {status_filter}
        so.per_delivered < 100 AND
        soi.qty > soi.delivered_qty AND
        so.status != 'Closed' AND
        (so._user_tags NOT LIKE "%template%" OR so._user_tags IS NULL)
        {extra_filters}
)) as united
ORDER BY 
	delivery_date ASC,
    parent,
    is_packed_item,
    idx;
    """.format(status_filter=status_filter, extra_filters=extra_filters)

    print(sql_query)
    data = frappe.db.sql(sql_query, as_dict=True)
    
    week_colours = itertools.cycle(['black', '#6660A9', '#297045', '#CC5A2B'])
    day_colours = itertools.cycle(['black', '#6660A9', '#297045', '#CC5A2B'])

    
    last_week_num = ''
    last_day = ''
    week_colour = next(week_colours)
    day_colour = next(day_colours)
    
    for row in data:       
        if row['weeknum'] != last_week_num:
            week_colour = next(week_colours)
            last_week_num = row['weeknum']
        row['weeknum'] = "<span style='color:{week_colour}!important;font-weight:bold;'>{weeknum}</span>".format(week_colour=week_colour, weeknum=row['weeknum'])
        
        if row['delivery_date'] != last_day:
            day_colour = next(day_colours)
            last_day = row['delivery_date']
        row['ship_date'] = "<span style='color:{day_colour}!important;font-weight:bold;'>{delivery_date}</span>".format(day_colour=day_colour, delivery_date=row['delivery_date'].strftime('%d-%m-%Y'))

        if row['is_packed_item']:
            row['indent'] = 1
            row['weeknum'] = ''
            row['ship_date'] = ''
        else:
            row['indent'] = 0
            row['item_name'] = "<b>{name}</b>".format(name=row['item_name'])

        if row['docstatus'] == 0:
            row['indicator'] = '<span class="indicator whitespace-nowrap red"><span>Draft</span></span>'
        else:
            row['indicator'] = '<span class="indicator whitespace-nowrap orange"><span>To Deliver</span></span>'
    
    return data


def get_chart(filters):

    status_filter = "so.docstatus = 1 AND"
    if filters.include_drafts:
        status_filter = "so.docstatus <= 1 AND" # include drafts and submitted.

    extra_filters = ""
    if filters.only_manufacturing:
        extra_filters += "AND it.include_item_in_manufacturing = TRUE"
        
    sql_query = """
SELECT
    WEEK(soi.delivery_date) as weeknum,
    SUBDATE(soi.delivery_date, WEEKDAY(soi.delivery_date)) as week,
    SUM(soi.qty - soi.delivered_qty) AS remaining_qty,
    it.item_group as item_group
FROM `tabSales Order Item` as soi
JOIN `tabSales Order` as so ON soi.parent = so.name
JOIN `tabItem` as it on soi.item_code = it.name
WHERE
    {status_filter} 
    so.status != 'Closed' AND
    soi.qty > soi.delivered_qty AND
    (so._user_tags NOT LIKE "%template%" OR so._user_tags IS NULL)
    {extra_filters}
GROUP BY week, item_group
ORDER BY week ASC
    """.format(status_filter=status_filter, extra_filters=extra_filters)
    
    data = frappe.db.sql(sql_query, as_dict=True)
    
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
