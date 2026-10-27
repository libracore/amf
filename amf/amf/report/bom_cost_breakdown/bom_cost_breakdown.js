// Copyright (c) 2026, libracore AG and contributors

frappe.query_reports["BOM Cost Breakdown"] = {
	filters: [
		{
			fieldname: "view", label: __("View"), fieldtype: "Select",
			options: "Average by Reference\nRecursive BOM\nLatest Purchase BOM\nLatest Purchase + Process BOM\nExcluded Records\nDetailed Work Order",
			default: "Average by Reference", reqd: 1
		},
		{
			fieldname: "item_code", label: __("Finished Item"), fieldtype: "Link",
			options: "Item"
		},
		{
			fieldname: "only_4xxxxx", label: __("Only 4 + five digit Items (averages)"),
			fieldtype: "Check", default: 0
		},
		{
			fieldname: "bom", label: __("BOM (detail / recursive)"), fieldtype: "Link", options: "BOM",
			get_query: function () {
				return {filters: {item: frappe.query_report.get_filter_value("item_code")}};
			}
		},
		{
			fieldname: "work_order", label: __("Work Order (detail / recursive)"),
			fieldtype: "Link", options: "Work Order",
			get_query: function () {
				return {filters: {production_item: frappe.query_report.get_filter_value("item_code")}};
			}
		}
	]
};
