// Copyright (c) 2016, libracore AG and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Production Master Planner Updated"] = {
	"filters": [
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"reqd": 0,
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"reqd": 0,
		},
		{
            "fieldname": "hide_completed",
            "label": __("HIDE COMPLETED"),
            "fieldtype": "Check",
            "default": 0,
        },
	]
};
