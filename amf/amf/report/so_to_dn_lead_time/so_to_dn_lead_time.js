// Copyright (c) 2016, libracore AG and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["so_to_dn_lead_time"] = {
	"filters": [
    {
      "fieldname": "from_date",
      "label": "From Date",
      "fieldtype": "Date",
      "default": "2024-10-01"
    },
    {
      "fieldname": "to_date",
      "label": "To Date",
      "fieldtype": "Date",
      "default": "2025-10-01"
    },
    {
      "fieldname": "company",
      "label": "Company",
      "fieldtype": "Link",
      "options": "Company",
	  "default": "Advanced Microfluidics SA"
    },
    {
      "fieldname": "customer",
      "label": "Customer",
      "fieldtype": "Link",
      "options": "Customer"
    },
    {
      "fieldname": "only_with_dn",
      "label": "Only Orders With Delivery Notes",
      "fieldtype": "Check",
      "default": 0
    }
  ],
};
