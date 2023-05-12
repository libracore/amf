// Copyright (c) 2016, libracore AG and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Delivered Items"] = {
    "filters": [
        {
            "fieldname": "item_code",
            "label": __("Item Code"),
            "fieldtype": "Link",
            "options": "Item",
            "reqd": 0,
            "default": ""
        },
        {
            "fieldname": "item_group",
            "label": __("Item Group"),
            "fieldtype": "Link",
            "options": "Item Group",
            "reqd": 0,
            "default": "Valve Head"
        },
        {
            "fieldname": "year",
            "label": __("Year"),
            "fieldtype": "Int",
            "reqd": 0,
            "default": "2022"
        },
        {
            "fieldname": "sum_quarters",
            "label": __("Sum Delivered Quantity by Year"),
            "fieldtype": "Check",
            "default": 1,
        }
    ]
}
