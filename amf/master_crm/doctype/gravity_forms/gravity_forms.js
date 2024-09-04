// Copyright (c) 2024, libracore AG and contributors
// For license information, please see license.txt

frappe.ui.form.on('Gravity Forms', {
    refresh: function(frm) {
        if ((frm.doc.gravity_host) && (frm.doc.gravity_key) && (frm.doc.gravity_secret)) {
            frm.add_custom_button(__("Fetch Forms"), function() {
                fetch_forms(frm);
            });
            frm.add_custom_button(__("Fetch Entries"), function() {
                fetch_entries(frm);
            });
        }
        frm.add_custom_button(__("Forms"), function() {
            frappe.set_route("List", "Gravity Form");
        });
        frm.add_custom_button(__("Entries"), function() {
            frappe.set_route("List", "Gravity Form Entry");
        });
    }
});

function fetch_forms(frm) {
    frappe.call({
        'method': 'amf.master_crm.doctype.gravity_forms.gravity_forms.fetch_forms',
        'freeze': true,
        'freeze_message': __("Syncing forms... Please wait..."),
        'callback': function(response) {
            frappe.show_alert( __("Forms updated") );
        }
    });
}

function fetch_entries(frm) {
    frappe.call({
        'method': 'amf.master_crm.doctype.gravity_forms.gravity_forms.fetch_entries',
        'freeze': true,
        'freeze_message': __("Syncing entries... Please wait..."),
        'callback': function(response) {
            frappe.show_alert( __("Entries updated") );
        }
    });
}
