frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["Longest Manufactured Items"] = {
	method: "amf.amf.dashboard_chart_source.longest_manufactured_items.longest_manufactured_items.get",
	filters: [
		{
			fieldname: "semester_count",
			label: __("Number of Semesters"),
			fieldtype: "Int",
			default: 1
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
			fieldname: "limit",
			label: __("Limit"),
			fieldtype: "Int",
			default: 20
		}
	]
};
