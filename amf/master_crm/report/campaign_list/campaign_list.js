// Copyright (c) 2016, libracore AG and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Campaign List"] = {
    "filters": [
        {
            'fieldname': 'country',
            'label': __("Country"),
            'fieldtype': "Link",
            'options': "Country"
        },
        {
            'fieldname': 'city',
            'label': __("City"),
            'fieldtype': "Data"
        },
        {
            'fieldname': 'customer',
            'label': __("Customer"),
            'fieldtype': "Link",
            'options': "Customer"
        },
        {
            'fieldname': 'revenue',
            'label': __("Revenue"),
            'fieldtype': "Currency"
        },
        {
            'fieldname': 'modified_after',
            'label': __("Modified after"),
            'fieldtype': "Date"
        }
    ],
    "onload": (report) => {
        report.page.add_inner_button(__('Upload to Brevo'), function () {
            upload_to_brevo()
        });
    }
};

function upload_to_brevo() {
    frappe.call({
        'method': 'amf.master_crm.doctype.brevo.brevo.fetch_lists',
        'callback': function(response) {
            let lists = response.message;
            let list_options = [];
            for (let i = 0; i < lists.length; i++) {
                list_options.push(lists[i].id + ": " + lists[i].name);
            }
            var d = new frappe.ui.Dialog({
                'title': __('Pick target list'),
                'fields': [
                    {
                        'fieldname': 'list', 
                        'fieldtype': 'Select', 
                        'label': __('List'), 
                        'options': list_options.join("\n"), 
                        'reqd': 1, 
                        'default': list_options[0]
                    }
                ],
                'primary_action': function() {
                    d.hide();
                    let target_list_id = d.get_values().list.split(":")[0];
                    let data = frappe.query_report.data;
                    for (let r = 0; r < data.length; r++) {
                        console.log("Uploading " + data[r].contact + " to " + target_list_id);
                        frappe.call({
                            'method': 'amf.master_crm.doctype.brevo.brevo.create_update_contact',
                            'args': {
                                'contact': data[r].contact,
                                'list_ids': [target_list_id]
                            },
                            'async': false,
                            'freeze': true,
                            'freeze_message': __("Uploading") + " " + data[r].contact + "..."
                        });
                    }
                },
                'primary_action_label': __('Upload')
            });
            d.show();
        }
    });
}
