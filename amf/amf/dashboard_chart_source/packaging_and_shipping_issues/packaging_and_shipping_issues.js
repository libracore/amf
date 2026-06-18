frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["Packaging and Shipping Issues"] = {
	method: "amf.amf.dashboard_chart_source.packaging_and_shipping_issues.packaging_and_shipping_issues.get",
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
		}
	]
};
