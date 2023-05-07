// Copyright (c) 2016, libracore AG and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Items Produced and Delivered"] = {
	"filters": [
		{
			"fieldname": "text_year",
			"label": __("tYear"),
			"fieldtype": "Read Only",
			"default": "Year",
			"width": "40"
		},
		{
			"fieldname": "year",
			"label": __("Year"),
			"fieldtype": "Select",
			"options": "2019\n2020\n2021\n2022\n2023",
			"default": "",
			"width": "80"
		},
		{
			"fieldname": "text_quarter",
			"label": __("tQuarter"),
			"fieldtype": "Read Only",
			"default": "Quarter",
			"width": "40"
		},
		{
			"fieldname": "quarter",
			"label": __("Quarter"),
			"fieldtype": "Select",
			"options": "1\n2\n3\n4",
			"default": "",
			"width": "80"
		}
	]
}