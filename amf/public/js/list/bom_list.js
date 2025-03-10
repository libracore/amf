frappe.listview_settings['BOM'] = {
    ...frappe.listview_settings['BOM'],
	filters: [["docstatus", "!=", "2"]],
};