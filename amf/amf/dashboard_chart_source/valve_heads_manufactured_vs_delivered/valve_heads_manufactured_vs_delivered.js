frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["Valve Heads Manufactured vs Delivered"] = {
	method: "amf.amf.dashboard_chart_source.valve_heads_manufactured_vs_delivered.valve_heads_manufactured_vs_delivered.get",
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
