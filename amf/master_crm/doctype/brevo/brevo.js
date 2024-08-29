// Copyright (c) 2024, libracore AG and contributors
// For license information, please see license.txt

frappe.ui.form.on('Brevo', {
    refresh: function(frm) {
        if (frm.doc.api_key) {
            frm.add_custom_button(__("Fetch contacts"), function() {
                fetch_contacts(frm);
            });
            frm.add_custom_button(__("Fetch lists"), function() {
                fetch_lists(frm);
            });
        }
    }
});

function fetch_contacts(frm) {
    frappe.call({
        'method': 'amf.master_crm.doctype.brevo.brevo.fetch_contacts',
        'callback': function(response) {
            frappe.msgprint(response.message);
        }
    });
}

function fetch_lists(frm) {
    frappe.call({
        'method': 'amf.master_crm.doctype.brevo.brevo.fetch_lists',
        'callback': function(response) {
            let html = "<table class='table'>";
            let lists = response.message;
            for (let i = 0; i < lists.length; i++) {
                html += "<tr><td>" + lists[i].id 
                     + "</td><td>" + lists[i].name 
                     + "</td><td>" + lists[i].uniqueSubscribers + " subscribers</td></tr>";
            }
            html += "</table>";
            frappe.msgprint(html);
        }
    });
}
