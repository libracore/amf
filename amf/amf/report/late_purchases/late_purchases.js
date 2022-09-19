// Copyright (c) 2016, libracore and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Late Purchases"] = {
	filters: [
		{
			"fieldname": "only_stock_items",
			"label": __("Only stock items"),
			"fieldtype": "Check",
			"default": 0,
		},
		{
			"fieldname": "bnovate_contact",
			"label": __("bNovate Contact"),
			"fieldtype": "Link",
			"options": "User",
		}
	]
};
