frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["Purchasing Amount by Currency"] = {
	method: "amf.amf.dashboard_chart_source.purchasing_amount_by_currency.purchasing_amount_by_currency.get",
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
