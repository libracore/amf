// Copyright (c) 2016, libracore AG and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Manufactured vs Purchased"] = {
	"filters": [
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            // Default: today minus 6 months
            default: frappe.datetime.add_months(frappe.datetime.get_today(), -6),
            reqd: 1
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            // Default: today
            default: frappe.datetime.get_today(),
            reqd: 1
        }
	]
};
