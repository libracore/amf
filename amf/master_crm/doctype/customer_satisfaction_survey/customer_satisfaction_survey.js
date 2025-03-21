// Copyright (c) 2025, libracore AG and contributors
// For license information, please see license.txt

frappe.ui.form.on('Customer Satisfaction Survey', {
	before_submit: function(frm) {
        if (frm.doc.contact_name && frm.doc.organization_name) {
            frm.set_value("title", frm.doc.contact_name + " for " + frm.doc.organization_name);
        }
    },
    contact_person: function (frm) {
        if (!frm.doc.contact_person) {
            frm.set_value("contact_name", "");
        }
    },
    customer: function (frm) {
        if (!frm.doc.customer) {
            frm.set_value("organization_name", "");
        }
    },
});
