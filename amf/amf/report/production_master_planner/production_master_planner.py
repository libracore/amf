# Copyright (c) 2013, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
import textwrap
import itertools
import datetime
from frappe import _

def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	return columns, data

def get_columns():
	return [
		{'fieldname': 'soi_name', 'fieldtype': 'Link', 'label': ('Item Code'), 'options': 'Item', 'width': 200},
		{'fieldname': 'so', 'fieldtype': 'Link', 'label': ('Sales Order'), 'options': 'Sales Order', 'width': 100},
		{'fieldname': 'qty', 'fieldtype': 'Int', 'label': ('Quantity'), 'width': 80},
		{'fieldname': 'customer', 'fieldtype': 'Link', 'label': ('Customer'), 'options': 'Customer', 'width': 200},
		{'fieldname': 'progress', 'fieldtype': 'Percent', 'label': ('Progress'), 'width': 80},
		{'fieldname': 'weeknum', 'fieldtype': 'Data', 'label': _('Week'), 'width': 55},
		{'fieldname': 'ship_date', 'fieldtype': 'Date', 'label': ('Ship. Date'), 'width': 100},
		{'fieldname': 'start_date', 'fieldtype': 'Date', 'label': ('Start Date'), 'width': 100},
		{'fieldname': 'wo', 'fieldtype': 'Link', 'label': ('Work Order'), 'options': 'Work Order', 'width': 100},
		{'fieldname': 'p_e_d', 'fieldtype': 'Date', 'label': ('End Date'), 'width': 100},
	]

def get_data(filters):
	extra_filters = ""
	#if filters.wo:
	#	extra_filters += "AND `tabWork Order`.name IS NOT NULL\n"
	if filters.wo is None:
		extra_filters += "AND `tabWork Order`.`name` IS NULL\n"
	if filters.progress is None:
		extra_filters += "AND (`tabSales Order Item`.`delivered_qty`/`tabSales Order Item`.`qty`*100) < '100'\n"
	sql_query = """
SELECT
	`tabSales Order Item`.`item_code` as soi_name,
	`tabSales Order`.`name` as so,
	`tabSales Order Item`.`qty` as qty,
	`tabSales Order`.`customer` as customer,
	(`tabSales Order Item`.`delivered_qty`/`tabSales Order Item`.`qty`*100) as progress,
	WEEK(`tabSales Order Item`.`delivery_date`) as weeknum,
	`tabSales Order Item`.`delivery_date` as ship_date,
	date_add(`tabSales Order Item`.`delivery_date`, INTERVAL -(`tabSales Order Item`.`qty`*`tabItem`.`timetoproduce`/60/24)-5 DAY) as start_date,
	(`tabSales Order Item`.`qty`*`tabItem`.`timetoproduce`) as time_to_produce_min,
	`tabWork Order`.name as wo,
	`tabWork Order`.p_e_d

FROM `tabSales Order Item`
left join `tabWork Order` on `tabWork Order`.`sales_order_item` = `tabSales Order Item`.`name`
join `tabSales Order` on `tabSales Order`.`name` = `tabSales Order Item`.`parent`
join `tabItem` on `tabItem`.`item_code` = `tabSales Order Item`.`item_code`

WHERE `tabSales Order Item`.`item_code` NOT RLIKE "GX."
	AND `tabSales Order Item`.`delivery_date` BETWEEN "{from_date}" AND "{to_date}"
	AND `tabSales Order`.`status` NOT LIKE "Completed"
	AND `tabSales Order`.`status` NOT LIKE "Closed"
	AND `tabSales Order`.`status` NOT LIKE "Cancelled"
	AND (`tabWork Order`.`status` NOT LIKE "Cancelled" OR `tabWork Order`.`sales_order` IS NULL)
	{extra_filters}

ORDER BY `tabSales Order Item`.`delivery_date`, `tabSales Order`.`customer` ASC
	;
	""".format(from_date=filters.from_date, to_date=filters.to_date, extra_filters=extra_filters)

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

#		if row['ship_date'] != last_day:
#			day_colour = next(day_colours)
#			last_day = row['ship_date']
#		row['ship_date'] = "<span style='color:{day_colour}!important;font-weight:bold;'>{ship_date}</span>".format(day_colour=day_colour, ship_date=row['ship_date'].strftime('%d-%m-%Y'))

#		if row['is_packed_item']:
#			row['indent'] = 1
#			row['weeknum'] = ''
#			row['ship_date'] = ''
#		else:
#			row['indent'] = 0
#			row['so'] = "<b>{so}</b>".format(name=row['so'])

#		if row['docstatus'] == 0:
#			row['indicator'] = '<span class="indicator whitespace-nowrap red"><span>Draft</span></span>'
#		else:
#			row['indicator'] = '<span class="indicator whitespace-nowrap orange"><span>To Deliver</span></span>'
	
	return data
