// Copyright (c) 2026, libracore AG and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Monthly Machined Parts"] = {
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
			"fieldname": "item_type",
			"label": __("Item Type"),
			"fieldtype": "Select",
			"options": "\nAll\nPlugs (10)\nValve Seats (20)",
			"default": "All"
		}
	]
};
