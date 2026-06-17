frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["Inventory Turnover Ratio"] = {
	method: "amf.amf.dashboard_chart_source.inventory_turnover_ratio.inventory_turnover_ratio.get",
	filters: [
		{
			fieldname: "semester_count",
			label: __("Number of Semesters"),
			fieldtype: "Int",
			default: 8
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date"
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today()
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: "Advanced Microfluidics SA"
		}
	]
};
