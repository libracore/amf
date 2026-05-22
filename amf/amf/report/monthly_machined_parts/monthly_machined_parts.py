# Copyright (c) 2026, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.utils import add_months, getdate, today


ITEM_CODE_PATTERNS = {
	"All": r"^(10|20)[0-9]{4}$",
	"Plugs (10)": r"^10[0-9]{4}$",
	"Valve Seats (20)": r"^20[0-9]{4}$",
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	normalize_filters(filters)

	columns = get_columns()
	data = get_data(filters)
	chart = get_chart(data)

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


def get_columns():
	return [
		{
			"fieldname": "month",
			"label": _("Month"),
			"fieldtype": "Data",
			"width": 95,
		},
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
		{
			"fieldname": "plug_qty",
			"label": _("Plugs (10)"),
			"fieldtype": "Float",
			"precision": 0,
			"width": 110,
		},
		{
			"fieldname": "valve_seat_qty",
			"label": _("Valve Seats (20)"),
			"fieldtype": "Float",
			"precision": 0,
			"width": 130,
		},
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


def get_data(filters):
	params = {
		"from_date": filters.from_date,
		"to_date": filters.to_date,
		"item_code_pattern": ITEM_CODE_PATTERNS.get(
			filters.item_type, ITEM_CODE_PATTERNS["All"]
		),
	}

	conditions = [
		"se.docstatus = 1",
		"se.purpose = 'Manufacture'",
		"se.posting_date BETWEEN %(from_date)s AND %(to_date)s",
		"IFNULL(sed.t_warehouse, '') != ''",
		"sed.item_code REGEXP %(item_code_pattern)s",
	]

	query = """
		SELECT
			manufactured.month,
			SUM(manufactured.produced_qty) AS total_produced_qty,
			SUM(IFNULL(scrap.scrap_qty, 0)) AS scrap_produced_qty,
			SUM(
				CASE
					WHEN LEFT(manufactured.item_code, 2) = '10'
					THEN manufactured.produced_qty
					ELSE 0
				END
			) AS plug_qty,
			SUM(
				CASE
					WHEN LEFT(manufactured.item_code, 2) = '20'
					THEN manufactured.produced_qty
					ELSE 0
				END
			) AS valve_seat_qty,
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
				AND sed.t_warehouse = 'Scrap - AMF21'
				AND sed.item_code REGEXP %(item_code_pattern)s
			GROUP BY se.work_order, sed.item_code
		) scrap
			ON scrap.work_order = manufactured.work_order
			AND scrap.item_code = manufactured.item_code
		GROUP BY manufactured.month
		ORDER BY manufactured.month ASC
	""".format(conditions=" AND ".join(conditions))

	data = frappe.db.sql(query, params, as_dict=True)
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

	return data


def get_chart(data):
	if not data:
		return None

	return {
		"data": {
			"labels": [row.get("month") for row in data],
			"datasets": [
				{
					"name": _("Total Produced"),
					"values": [row.get("total_produced_qty") or 0 for row in data],
				},
				{
					"name": _("Good Produced"),
					"values": [row.get("good_produced_qty") or 0 for row in data],
				},
				{
					"name": _("Scrap Produced"),
					"values": [row.get("scrap_produced_qty") or 0 for row in data],
				},
			],
		},
		"type": "bar",
		"height": 300,
	}
