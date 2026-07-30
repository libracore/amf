// Copyright (c) 2026, libracore AG and contributors
// For license information, please see license.txt

frappe.require("assets/erpnext/js/sales_trends_filters.js", function() {
	frappe.query_reports["Sales Invoice Trends"] = {
		filters: erpnext.get_sales_trends_filters(),
		formatter: function(value, row, column, data, default_formatter) {
			if (
				column.fieldtype === "Link"
				&& column.options === "Customer"
				&& data
				&& data._customer_display_name
			) {
				return frappe.format(
					value,
					column,
					{
						for_print: false,
						always_show_decimals: true,
						label: data._customer_display_name
					},
					data
				);
			}

			return default_formatter(value, row, column, data);
		}
	};
});
