// Copyright (c) 2025, libracore AG and contributors
// For license information, please see license.txt

frappe.ui.form.on('Referral Satisfaction Survey', {
    before_submit: function (frm) {
        if (frm.doc.referred_contact_name && frm.doc.referred_organization_name) {
            frm.set_value("title", frm.doc.referred_contact_name + " for " + frm.doc.referred_organization_name);
        }
        else {
            frm.set_value("title", "Referral for " + frm.doc.referring_organization_name);
        }
    },
    contact_person: function (frm) {
        if (!frm.doc.contact_person) {
            frm.set_value("referred_contact_name", "");
        }
    },
    referred_organization: function (frm) {
        if (!frm.doc.referred_organization) {
            frm.set_value("referred_organization_name", "");
        }
    },
});
