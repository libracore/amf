// Copyright (c) 2024, libracore and contributors
// For license information, please see license.txt

frappe.ui.form.on("Quotation", {
    on_submit: function(frm) {
        // update contact status
        if (frm.doc.contact_person) {
            frappe.call({
                'method': 'amf.master_crm.utils.update_status',
                'args': {
                    'contact': frm.doc.contact_person,
                    'status': 'Prospect'
                }
            });
        }
    }
});
