// Copyright (c) 2016, libracore AG and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Item Purchase and Manufacture Summary"] = {
	"filters": [
        {
            "fieldname": "item_code",
            "label": "Item Code",
            "fieldtype": "Link",
            "options": "Item",
            "default": "",
            "reqd": 0,
        },
        {
            "fieldname": "year",
            "label": "Year",
            "fieldtype": "Select",
            "default": "",
            "reqd": 0,
            "options": "\n2019\n2020\n2021\n2022\n2023",
        },
        {
            "fieldname": "quarter",
            "label": "Quarter",
            "fieldtype": "Select",
            "options": " \nQ1\nQ2\nQ3\nQ4",
            "default": "",
            "reqd": 0,
        }
    ]
};
