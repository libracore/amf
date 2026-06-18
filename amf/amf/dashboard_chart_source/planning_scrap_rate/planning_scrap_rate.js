frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["Planning Scrap Rate"] = {
	method: "amf.amf.dashboard_chart_source.planning_scrap_rate.planning_scrap_rate.get",
	filters: [
		{
			fieldname: "mode",
			label: __("Mode"),
			fieldtype: "Select",
			options: "references\nsemester",
			default: "semester"
		},
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
			fieldname: "limit",
			label: __("Limit"),
			fieldtype: "Int",
			default: 20
		}
	]
};
