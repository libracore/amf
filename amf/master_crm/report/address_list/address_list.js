// Copyright (c) 2024, libracore AG and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Address List"] = {
    "filters": [
        {
            'fieldname': 'country',
            'label': __("Country"),
            'fieldtype': "Link",
            'options': "Country"
        }
    ]
};
