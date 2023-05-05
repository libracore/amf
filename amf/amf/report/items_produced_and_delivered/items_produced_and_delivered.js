// Copyright (c) 2016, libracore AG and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Items Produced and Delivered"] = {
	"filters": [
        {
            "fieldname": "display_type",
            "label": _("Display Type"),
            "fieldtype": "Check",
            "options": "Produced\nDelivered",
            "default": ["Produced", "Delivered"],
        },
    ]
}