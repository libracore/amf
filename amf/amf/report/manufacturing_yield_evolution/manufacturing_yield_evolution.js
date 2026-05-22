// Copyright (c) 2026, libracore AG and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Manufacturing Yield Evolution"] = {
	"filters": [
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.add_months(frappe.datetime.get_today(), -12),
			"reqd": 1
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.get_today(),
			"reqd": 1
		},
		{
			"fieldname": "view_by",
			"label": __("View By"),
			"fieldtype": "Select",
			"options": "Month\nPlanning",
			"default": "Month",
			"reqd": 1
		},
		{
			"fieldname": "item_type",
			"label": __("Item Type"),
			"fieldtype": "Select",
			"options": "\nAll\nPlugs (10)\nValve Seats (20)",
			"default": "All"
		},
		{
			"fieldname": "item_code",
			"label": __("Item Code"),
			"fieldtype": "Link",
			"options": "Item"
		}
	]
};
