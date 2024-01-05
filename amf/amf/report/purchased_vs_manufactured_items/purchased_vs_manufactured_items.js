// Copyright (c) 2016, libracore AG and contributors
// For license information, please see license.txt
/* eslint-disable */

function formatDate(date) {
    var d = new Date(date),
        month = '' + (d.getMonth() + 1), // Months are zero indexed
        day = '' + d.getDate(),
        year = d.getFullYear();

    if (month.length < 2) 
        month = '0' + month;
    if (day.length < 2) 
        day = '0' + day;

    return [year, month, day].join('-');
}

function get_semester_dates() {
    var today = new Date();
    var currentYear = today.getFullYear();
    var start_date, end_date;

    // Check if the current date is in the first or second semester
    if (today.getMonth() < 6) {  // First semester (Jan - Jun)
        // Last semester would be the second semester of the previous year
        start_date = new Date(currentYear - 1, 6, 1);  // July 1st of the previous year
        end_date = new Date(currentYear - 1, 11, 31);  // December 31st of the previous year
    } else {  // Second semester (Jul - Dec)
        // Last semester would be the first semester of the current year
        start_date = new Date(currentYear, 0, 1);  // January 1st of the current year
        end_date = new Date(currentYear, 5, 30);  // June 30th of the current year
    }

    return { start_date: formatDate(start_date), end_date: formatDate(end_date) };
}

var semester_dates = get_semester_dates();

frappe.query_reports["Purchased vs Manufactured Items"] = {
    "filters": [
        {
            "fieldname": "start_date",
            "label": __("Start Date"),
            "fieldtype": "Date",
            "default": semester_dates.start_date,
            "reqd": 1
        },
        {
            "fieldname": "end_date",
            "label": __("End Date"),
            "fieldtype": "Date",
            "default": semester_dates.end_date,
            "reqd": 1
        },
        {
            "fieldname": "item_groups",
            "label": __("Item Groups"),
            "fieldtype": "MultiSelectList",
            "get_data": function(txt) {
                return frappe.db.get_link_options('Item Group', txt);
            },
            "default": ["Plug", "Valve Seat"]
        }
    ]
};
