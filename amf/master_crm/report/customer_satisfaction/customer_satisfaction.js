// Copyright (c) 2016, libracore AG and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Customer Satisfaction"] = {
    onload: function (report) {
        // today as YYYY-MM-DD
        const today = frappe.datetime.nowdate();
        const year = today.substr(0, 4);
        const start = `${year}-01-01`;
        const end = `${year}-12-31`;

        // set our two required filters
        report.set_filter_value("from_date", start);
        report.set_filter_value("to_date", end);
    },

    filters: [
        {
            fieldname: "from_date",
            label: "From Date",
            fieldtype: "Date",
            reqd: 1
        },
        {
            fieldname: "to_date",
            label: "To Date",
            fieldtype: "Date",
            reqd: 1
        }
    ]
};
