# Copyright (c) 2026, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.utils import add_months, getdate, today


SCRAP_WAREHOUSE = "Scrap - AMF21"

ITEM_CODE_PATTERNS = {
	"All": r"^(10|20)[0-9]{4}$",
	"Plugs (10)": r"^10[0-9]{4}$",
	"Valve Seats (20)": r"^20[0-9]{4}$",
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	normalize_filters(filters)

	columns = get_columns(filters)
	data = get_data(filters)
	chart = get_chart(filters, data)

	return columns, data, None, chart


def normalize_filters(filters):
	if not filters.get("to_date"):
		filters.to_date = today()

	if not filters.get("from_date"):
		filters.from_date = add_months(filters.to_date, -12)

	filters.from_date = getdate(filters.from_date)
	filters.to_date = getdate(filters.to_date)

	if filters.from_date > filters.to_date:
		frappe.throw(_("From Date cannot be after To Date"))

	if not filters.get("item_type"):
		filters.item_type = "All"

	if filters.get("view_by") not in ("Month", "Planning"):
		filters.view_by = "Month"


def get_columns(filters):
	if filters.view_by == "Planning":
		return get_planning_columns()

	return get_monthly_columns()


def get_monthly_columns():
	return [
		{
			"fieldname": "month",
			"label": _("Month"),
			"fieldtype": "Data",
			"width": 95,
		},
		{
			"fieldname": "item_code",
			"label": _("Item Code"),
			"fieldtype": "Link",
			"options": "Item",
			"width": 110,
		},
		{
			"fieldname": "item_name",
			"label": _("Item Name"),
			"fieldtype": "Data",
			"width": 220,
		},
	] + get_yield_columns() + [
		{
			"fieldname": "manufacture_stock_entries",
			"label": _("Manufacture Entries"),
			"fieldtype": "Int",
			"width": 135,
		},
		{
			"fieldname": "scrap_stock_entries",
			"label": _("Scrap Entries"),
			"fieldtype": "Int",
			"width": 105,
		},
		{
			"fieldname": "work_orders",
			"label": _("Work Orders"),
			"fieldtype": "Int",
			"width": 105,
		},
	]


def get_planning_columns():
	return [
		{
			"fieldname": "posting_date",
			"label": _("Posting Date"),
			"fieldtype": "Date",
			"width": 105,
		},
		{
			"fieldname": "month",
			"label": _("Month"),
			"fieldtype": "Data",
			"width": 95,
		},
		{
			"fieldname": "planning",
			"label": _("Planning"),
			"fieldtype": "Link",
			"options": "Planning",
			"width": 145,
		},
		{
			"fieldname": "work_order",
			"label": _("Work Order"),
			"fieldtype": "Link",
			"options": "Work Order",
			"width": 125,
		},
		{
			"fieldname": "manufacture_stock_entry",
			"label": _("Manufacture Entry"),
			"fieldtype": "Link",
			"options": "Stock Entry",
			"width": 135,
		},
		{
			"fieldname": "item_code",
			"label": _("Item Code"),
			"fieldtype": "Link",
			"options": "Item",
			"width": 110,
		},
		{
			"fieldname": "item_name",
			"label": _("Item Name"),
			"fieldtype": "Data",
			"width": 220,
		},
	] + get_yield_columns() + [
		{
			"fieldname": "scrap_stock_entries",
			"label": _("Scrap Entries"),
			"fieldtype": "Int",
			"width": 105,
		},
	]


def get_yield_columns():
	return [
		{
			"fieldname": "total_produced_qty",
			"label": _("Total Produced"),
			"fieldtype": "Float",
			"precision": 0,
			"width": 120,
		},
		{
			"fieldname": "good_produced_qty",
			"label": _("Good Produced"),
			"fieldtype": "Float",
			"precision": 0,
			"width": 120,
		},
		{
			"fieldname": "scrap_produced_qty",
			"label": _("Scrap Produced"),
			"fieldtype": "Float",
			"precision": 0,
			"width": 120,
		},
		{
			"fieldname": "good_produced_ratio",
			"label": _("Good Ratio"),
			"fieldtype": "Percent",
			"precision": 1,
			"width": 105,
		},
		{
			"fieldname": "scrap_produced_ratio",
			"label": _("Scrap Ratio"),
			"fieldtype": "Percent",
			"precision": 1,
			"width": 105,
		},
	]


def get_data(filters):
	data = get_planning_data(filters) if filters.view_by == "Planning" else get_monthly_data(filters)
	add_yield_ratios(data)
	return data


def get_common_params(filters):
	return {
		"from_date": filters.from_date,
		"to_date": filters.to_date,
		"item_code_pattern": ITEM_CODE_PATTERNS.get(
			filters.item_type, ITEM_CODE_PATTERNS["All"]
		),
		"scrap_warehouse": SCRAP_WAREHOUSE,
		"item_code": filters.get("item_code"),
	}


def get_manufacture_conditions(filters, table_alias="sed"):
	conditions = [
		"se.docstatus = 1",
		"se.purpose = 'Manufacture'",
		"se.posting_date BETWEEN %(from_date)s AND %(to_date)s",
		"IFNULL({0}.t_warehouse, '') != ''".format(table_alias),
		"{0}.item_code REGEXP %(item_code_pattern)s".format(table_alias),
	]

	if filters.get("item_code"):
		conditions.append("{0}.item_code = %(item_code)s".format(table_alias))

	return conditions


def get_monthly_data(filters):
	params = get_common_params(filters)
	conditions = get_manufacture_conditions(filters)

	query = """
		SELECT
			manufactured.month,
			manufactured.item_code,
			item.item_name,
			SUM(manufactured.produced_qty) AS total_produced_qty,
			SUM(IFNULL(scrap.scrap_qty, 0)) AS scrap_produced_qty,
			SUM(manufactured.stock_entries) AS manufacture_stock_entries,
			SUM(IFNULL(scrap.scrap_stock_entries, 0)) AS scrap_stock_entries,
			COUNT(DISTINCT manufactured.work_order) AS work_orders
		FROM (
			SELECT
				DATE_FORMAT(se.posting_date, '%%Y-%%m') AS month,
				se.work_order,
				sed.item_code,
				SUM(COALESCE(NULLIF(sed.transfer_qty, 0), sed.qty, 0)) AS produced_qty,
				COUNT(DISTINCT se.name) AS stock_entries
			FROM `tabStock Entry` se
			INNER JOIN `tabStock Entry Detail` sed ON sed.parent = se.name
			WHERE {conditions}
			GROUP BY month, se.work_order, sed.item_code
		) manufactured
		LEFT JOIN (
			SELECT
				se.work_order,
				sed.item_code,
				SUM(COALESCE(NULLIF(sed.transfer_qty, 0), sed.qty, 0)) AS scrap_qty,
				COUNT(DISTINCT se.name) AS scrap_stock_entries
			FROM `tabStock Entry` se
			INNER JOIN `tabStock Entry Detail` sed ON sed.parent = se.name
			WHERE se.docstatus = 1
				AND se.purpose = 'Material Transfer'
				AND IFNULL(se.work_order, '') != ''
				AND sed.t_warehouse = %(scrap_warehouse)s
				AND sed.item_code REGEXP %(item_code_pattern)s
				{item_code_condition}
			GROUP BY se.work_order, sed.item_code
		) scrap
			ON scrap.work_order = manufactured.work_order
			AND scrap.item_code = manufactured.item_code
		LEFT JOIN `tabItem` item ON item.name = manufactured.item_code
		GROUP BY manufactured.month, manufactured.item_code, item.item_name
		ORDER BY
			manufactured.month ASC,
			(SUM(IFNULL(scrap.scrap_qty, 0)) / NULLIF(SUM(manufactured.produced_qty), 0)) DESC,
			manufactured.item_code ASC
	""".format(
		conditions=" AND ".join(conditions),
		item_code_condition="AND sed.item_code = %(item_code)s" if filters.get("item_code") else "",
	)

	return frappe.db.sql(query, params, as_dict=True)


def get_planning_data(filters):
	params = get_common_params(filters)
	conditions = get_manufacture_conditions(filters)

	query = """
		SELECT
			manufactured.posting_date,
			manufactured.month,
			COALESCE(planning.name, planning_by_work_order.name) AS planning,
			manufactured.work_order,
			manufactured.manufacture_stock_entry,
			manufactured.item_code,
			item.item_name,
			manufactured.produced_qty AS total_produced_qty,
			IFNULL(scrap.scrap_qty, 0) AS scrap_produced_qty,
			IFNULL(scrap.scrap_stock_entries, 0) AS scrap_stock_entries
		FROM (
			SELECT
				se.posting_date,
				DATE_FORMAT(se.posting_date, '%%Y-%%m') AS month,
				se.name AS manufacture_stock_entry,
				se.work_order,
				sed.item_code,
				SUM(COALESCE(NULLIF(sed.transfer_qty, 0), sed.qty, 0)) AS produced_qty
			FROM `tabStock Entry` se
			INNER JOIN `tabStock Entry Detail` sed ON sed.parent = se.name
			WHERE {conditions}
			GROUP BY se.name, se.posting_date, se.work_order, sed.item_code
		) manufactured
		LEFT JOIN (
			SELECT
				se.work_order,
				sed.item_code,
				SUM(COALESCE(NULLIF(sed.transfer_qty, 0), sed.qty, 0)) AS scrap_qty,
				COUNT(DISTINCT se.name) AS scrap_stock_entries
			FROM `tabStock Entry` se
			INNER JOIN `tabStock Entry Detail` sed ON sed.parent = se.name
			WHERE se.docstatus = 1
				AND se.purpose = 'Material Transfer'
				AND IFNULL(se.work_order, '') != ''
				AND sed.t_warehouse = %(scrap_warehouse)s
				AND sed.item_code REGEXP %(item_code_pattern)s
				{item_code_condition}
			GROUP BY se.work_order, sed.item_code
		) scrap
			ON scrap.work_order = manufactured.work_order
			AND scrap.item_code = manufactured.item_code
		LEFT JOIN `tabPlanning` planning
			ON planning.stock_entry = manufactured.manufacture_stock_entry
		LEFT JOIN `tabPlanning` planning_by_work_order
			ON planning_by_work_order.work_order = manufactured.work_order
			AND IFNULL(planning_by_work_order.stock_entry, '') = ''
		LEFT JOIN `tabItem` item ON item.name = manufactured.item_code
		ORDER BY manufactured.posting_date ASC, manufactured.item_code ASC, manufactured.work_order ASC
	""".format(
		conditions=" AND ".join(conditions),
		item_code_condition="AND sed.item_code = %(item_code)s" if filters.get("item_code") else "",
	)

	return frappe.db.sql(query, params, as_dict=True)


def add_yield_ratios(data):
	for row in data:
		total_produced_qty = row.get("total_produced_qty") or 0
		scrap_produced_qty = row.get("scrap_produced_qty") or 0
		good_produced_qty = total_produced_qty - scrap_produced_qty

		row["good_produced_qty"] = good_produced_qty
		row["manufacture_stock_entries"] = int(row.get("manufacture_stock_entries") or 0)
		row["scrap_stock_entries"] = int(row.get("scrap_stock_entries") or 0)
		row["work_orders"] = int(row.get("work_orders") or 0)
		row["good_produced_ratio"] = (
			good_produced_qty * 100 / total_produced_qty if total_produced_qty else 0
		)
		row["scrap_produced_ratio"] = (
			scrap_produced_qty * 100 / total_produced_qty if total_produced_qty else 0
		)


def get_chart(filters, data):
	if not data:
		return None

	if filters.view_by == "Planning" or filters.get("item_code"):
		return get_single_series_chart(filters, data)

	return get_item_comparison_chart(data)


def get_single_series_chart(filters, data):
	label_field = "planning" if filters.view_by == "Planning" else "month"
	labels = [
		(row.get(label_field) or row.get("work_order") or row.get("month") or row.get("item_code"))
		for row in data
	]

	return {
		"data": {
			"labels": labels,
			"datasets": [
				{
					"name": _("Good Ratio"),
					"values": [row.get("good_produced_ratio") or 0 for row in data],
				},
				{
					"name": _("Scrap Ratio"),
					"values": [row.get("scrap_produced_ratio") or 0 for row in data],
				},
			],
		},
		"type": "line",
		"height": 300,
	}


def get_item_comparison_chart(data):
	months = sorted(set(row.get("month") for row in data if row.get("month")))
	item_codes = sorted(set(row.get("item_code") for row in data if row.get("item_code")))

	return {
		"data": {
			"labels": months,
			"datasets": [
				{
					"name": item_code,
					"values": [
						next(
							(
								row.get("scrap_produced_ratio") or 0
								for row in data
								if row.get("month") == month and row.get("item_code") == item_code
							),
							0,
						)
						for month in months
					],
				}
				for item_code in item_codes[:12]
			],
		},
		"type": "line",
		"height": 300,
	}
