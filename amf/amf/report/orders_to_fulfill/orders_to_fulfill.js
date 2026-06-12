// Copyright (c) 2016, libracore and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Orders to Fulfill"] = {
	filters: [
		{
			"fieldname": "include_drafts",
			"label": __("Include Drafts"),
			"fieldtype": "Check",
			"default": 1
		},
		{
			"fieldname": "include_loans",
			"label": __("Include Loans"),
			"fieldtype": "Check",
			"default": 1
		},
        {
			"fieldname": "remove_gx",
			"label": __("Remove GX"),
			"fieldtype": "Check",
			"default": 0
		},
        {
			"fieldname": "only_manufacturing",
			"label": __("Only Manufactured Items"),
			"fieldtype": "Check",
			"default": 0
		},
		{
			"fieldname": "company",
			"label": __("Company"),
			"fieldtype": "Link",
			"options": "Company"
		},
	],
	initial_depth: 0,
	"formatter": function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		if (!data) {
			return value;
		}

		const group_index = parseInt(data.order_group_index || 0, 10);
		const is_group_start = parseInt(data.order_group_start || 0, 10);
		const background = group_index % 2 ? "#f7fbff" : "#ffffff";
		const border = is_group_start ? "3px solid #8ea0ae" : "1px solid transparent";

		return `
			<div style="
				background:${background};
				border-top:${border};
				margin:-8px -10px;
				min-height:33px;
				padding:8px 10px;
			">${value || ""}</div>
		`;
	}
};
