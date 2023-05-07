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
        },
        {
            "fieldname": "year",
            "label": "Year",
            "fieldtype": "Int",
            "default": 2022,
            "options": "2019, 2020, 2021, 2022, 2023"
        },
        {
            "fieldname": "quarter",
            "label": "Quarter",
            "fieldtype": "Select",
            "options": "Q1\nQ2\nQ3\nQ4",
            "default": "",
        }
    ]
};
