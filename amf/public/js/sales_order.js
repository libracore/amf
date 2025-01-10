// Copyright (c) 2024, libracore and contributors
// For license information, please see license.txt

frappe.ui.form.on("Sales Order", {
    on_submit: function (frm) {
        // update contact status
        if (frm.doc.contact_person) {
            frappe.call({
                'method': 'amf.master_crm.utils.update_status',
                'args': {
                    'contact': frm.doc.contact_person,
                    'status': 'Customer'
                }
            });
        }
        // update last PO
        if (frm.doc.contact_person) {
            frappe.call({
                'method': 'amf.master_crm.utils.update_last_po',
                'args': {
                    'contact': frm.doc.contact_person
                }
            });
        }
    },

    refresh: function (frm) {

        // Display the saved comments on the dashboard
        if (frm.doc.custom_production_comment) {
            const formatted_comments = `<span style="font-weight: bold; font-size: 16px;">${frm.doc.custom_production_comment.replace(/\n/g, '<br>------------------------------------------------<br>')}</span>`;
            frm.dashboard.add_comment(formatted_comments, 'red', true);
        }

        // Add a custom button
        frm.add_custom_button(__('Add Production Comment'), function () {
            // Prompt the user for a comment
            frappe.prompt(
                [
                    {
                        label: 'Comment',
                        fieldname: 'user_comment',
                        fieldtype: 'Small Text',
                        reqd: true
                    }
                ],
                function (values) {
                    // Append the user's comment to the custom_production_comment field
                    if (frm.doc.custom_production_comment) {
                        frm.set_value('custom_production_comment',
                            frm.doc.custom_production_comment + '\n' + values.user_comment
                        );
                    } else {
                        frm.set_value('custom_production_comment', values.user_comment);
                    }

                    frappe.msgprint(__('Please "Update" the document.'));
                },
                __('Enter Production Comment'),
                __('Add')
            );
        });

    },
})
