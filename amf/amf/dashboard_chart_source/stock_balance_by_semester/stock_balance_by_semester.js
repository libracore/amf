frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["Stock Balance by Semester"] = {
	method: "amf.amf.dashboard_chart_source.stock_balance_by_semester.stock_balance_by_semester.get",
	filters: [
		{
			fieldname: "mode",
			label: __("Mode"),
			fieldtype: "Select",
			options: "amount\nquantity",
			default: "amount"
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
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: "Advanced Microfluidics SA"
		},
		{
			fieldname: "warehouse",
			label: __("Warehouse"),
			fieldtype: "Link",
			options: "Warehouse"
		}
	]
};
