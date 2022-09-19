// Copyright (c) 2016, libracore and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Orders to Fulfill"] = {
	filters: [
		{
			"fieldname": "only_manufacturing",
			"label": __("Only manufactured items"),
			"fieldtype": "Check",
			"default": 1
		},
		{
			"fieldname": "include_drafts",
			"label": __("Include Drafts"),
			"fieldtype": "Check",
			"default": 0
		}
	],
	initial_depth: 0,
	/*,
	"formatter": function (value, row, column, data, default_formatter) {
		console.log(value, row, column, data, default_formatter);
		return default_formatter(value, row, column, data);
	
	*/
};
