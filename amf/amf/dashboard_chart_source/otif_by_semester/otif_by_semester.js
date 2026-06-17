frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["OTIF by Semester"] = {
	method: "amf.amf.dashboard_chart_source.otif_by_semester.otif_by_semester.get",
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
			fieldname: "item_group",
			label: __("Item Group"),
			fieldtype: "Link",
			options: "Item Group"
		},
		{
			fieldname: "include_rd",
			label: __("Include R&D"),
			fieldtype: "Check",
			default: 0
		}
	]
};
