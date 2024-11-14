// Copyright (c) 2024, libracore AG and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Campaign List"] = {
    "filters": [
        {
            'fieldname': 'status',
            'label': __("Status"),
            'fieldtype': "Select",
            'options': "\nLead\nProspect\nCustomer\nSupplier\nBack-Office\nPassive\nInactive\nAMF\nDistributor"
        },
        {
            'fieldname': 'type_of_contact',
            'label': __("Type of Contact"),
            'fieldtype': "Select",
            'options': "\nPrimary\nPurchase\nSupply\nShipping\nInvoice\nQuality\nR&D\nOthers"
        },
        {
            'fieldname': 'customer',
            'label': __("Customer"),
            'fieldtype': "Link",
            'options': "Customer"
        },
        {
            'fieldname': 'city',
            'label': __("City"),
            'fieldtype': "Data"
        },
        {
            'fieldname': 'country',
            'label': __("Country"),
            'fieldtype': "Link",
            'options': "Country"
        },
        {
            'fieldname': 'customer_group',
            'label': __("Customer Group"),
            'fieldtype': "Link",
            'options': "Customer Group"
        },
        {
            'fieldname': 'source',
            'label': __("Source"),
            'fieldtype': "Select",
            'options': "\nEvent\nDatabase\nSEA\nSEO"
        },
        {
            'fieldname': 'from_source',
            'label': __("From Source"),
            'fieldtype': "Link",
            'options': "Lead Source"
        },
        {
            'fieldname': 'product',
            'label': __("Product"),
            'fieldtype': "Select",
            'options': "\nRVM\nSPM\nLSPone\nValves\nCustom"
        },
        {
            'fieldname': 'last_po',
            'label': __("Last PO (after)"),
            'fieldtype': "Date"
        },
        {
            'fieldname': 'development_stage',
            'label': __("Development Stage"),
            'fieldtype': "Select",
            'options': "\nProof of concept\nPrototype\nCommercial v1\nCommercial v2"
        },
        {
            'fieldname': 'revenue',
            'label': __("Revenue"),
            'fieldtype': "Currency"
        },
        {
            'fieldname': 'revenue_from',
            'label': __("Revenue from"),
            'fieldtype': "Date"
        },
        {
            'fieldname': 'revenue_to',
            'label': __("Revenue to"),
            'fieldtype': "Date"
        },
        {
            'fieldname': 'qualification',
            'label': __("Qualification"),
            'fieldtype': "Rating"
        },
        {
            'fieldname': 'deliverability',
            'label': __("Deliverability"),
            'fieldtype': "Select",
            'options': "\nOK\nTBD\nINVALID"
        },
        {
            'fieldname': 'gdpr',
            'label': __("GDPR"),
            'fieldtype': "Check"
        },
        {
            'fieldname': 'created_after',
            'label': __("Created after"),
            'fieldtype': "Date"
        },
        {
            'fieldname': 'modified_after',
            'label': __("Modified after"),
            'fieldtype': "Date"
        },
        {
            'fieldname': 'is_customer',
            'label': __("Is Customer"),
            'fieldtype': "Select",
            'options': "\nYes\nNo"
        }
    ],
    "onload": (report) => {
        report.page.add_inner_button(__('Upload to Brevo'), function () {
            upload_to_brevo()
        });
        
        // hide chart buttons
        setTimeout(function() {
            frappe.query_report.page.remove_inner_button( __("Set Chart") );
            frappe.query_report.page.remove_inner_button( __("Hide Chart") );
        }, 500);
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
