// Copyright (c) 2016, libracore AG and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Production Master Planner"] = {
	"filters": [
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"default": "2022-11-01",
			"reqd": 1,
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"default": "2023-12-31",
			"reqd": 1,
		},
		{
			"fieldname": "wo",
			"label": __("Work Order"),
			"fieldtype": "Check",
			"default": 1,
		},
		{
			"fieldname": "progress",
			"label": __("Progess @100%"),
			"fieldtype": "Check",
			"default": 0,
		},
	]
};
