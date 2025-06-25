// Copyright (c) 2025, libracore AG and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Leave Balance Overview"] = {
    "filters": [
                {
            "fieldname":"from_date",
            "label": __("From Date"),
            "fieldtype": "Date",
            "reqd": 1,
            "default": frappe.defaults.get_default("year_start_date")
        },
        {
            "fieldname":"to_date",
            "label": __("To Date"),
            "fieldtype": "Date",
            "reqd": 1,
            "default": frappe.defaults.get_default("year_end_date")
        },
        {
            "fieldname":"company",
            "label": __("Company"),
            "fieldtype": "Link",
            "options": "Company",
            "reqd": 1,
            "default": frappe.defaults.get_user_default("Company")
        }
    ]
};
