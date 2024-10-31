// Copyright (c) 2024, libracore AG and contributors
// For license information, please see license.txt

frappe.ui.form.on('Gravity Form Entry', {
    refresh: function(frm) {
        if (!frm.doc.converted) {
            frm.add_custom_button(__("Create Contact"), function() {
                create_contact(frm);
            });
        }
        if (frm.doc.contact) {
            frm.add_custom_button(__("Open Contact"), function() {
                window.open("/desk#Form/Contact/" + frm.doc.contact, "_blank");
            });
        }
    }
});

function create_contact(frm) {
    // gather data
    let data = {};
    for (let i = 0; i < frm.doc.fields.length; i++) {
        data[frm.doc.fields[i].field_name] = frm.doc.fields[i].value;
    }
    
    var d = new frappe.ui.Dialog({
        'fields': [
            {'fieldname': 'first_name', 'fieldtype': 'Data', 'label': __("First name"), 'default': (data['First name'] || "")},
            {'fieldname': 'last_name', 'fieldtype': 'Data', 'label': __("Last name"), 'default': (data['Last name'] || "")},
            {'fieldname': 'phone', 'fieldtype': 'Data', 'label': __("Phone"), 'default': (data['Phone'] || "")},
            {'fieldname': 'email', 'fieldtype': 'Data', 'label': __("Email"), 'default': (data['Email'] || "")},
            {'fieldname': 'postition', 'fieldtype': 'Data', 'label': __("Position"), 'default': (data['Postition'] || "")}
        ],
        primary_action: function(){
            d.hide();
            let values = d.get_values();
            frappe.call({
                'method': 'amf.master_crm.contact.create_update_contact',
                'args': {
                    'first_name': values.first_name,
                    'last_name': values.last_name,
                    'email': values.email,
                    'phone': values.phone,
                    'position': values.position
                },
                'callback': function(response) {
                    if (response.message) {
                        cur_frm.set_value("converted", 1);
                        cur_frm.set_value("contact", response.message);
                        cur_frm.save();
                    } else {
                        frappe.msgprint( __("Ups, something went wrong...") );
                    }
                }
            });
        },
        primary_action_label: __('Create Contact')
    });
    d.show();
}
