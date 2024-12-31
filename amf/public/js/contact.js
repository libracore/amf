/*
Contact Client Custom Script
----------------------------
*/

// extend/create dashboard
cur_frm.dashboard.add_transactions([
    {
        'label': __("Pre-Sales"),
        'items': ["Opportunity", "Quotation", "Sales Activity"]
    },
    {
        'label': __("Procurement"),
        'items': ["Purchase Order"]
    },
    {
        'label': __("Complaints"),
        'items': ["Issue"]
    }
]);


frappe.ui.form.on('Contact', {
    refresh: function(frm) {
        // load the header section
        frappe.call({
            'method': 'amf.master_crm.contact.get_header',
            'args': {
                'contact': frm.doc.__islocal ? null : frm.doc.name
            },
            'callback': function(response) {
                cur_frm.set_df_property(
                    'contact_header_html', 
                    'options', 
                    response.message
                );
                // attach header form handlers
                attach_header_form_handlers();
            }
        });
        // remove the invite as user button
        cur_frm.remove_custom_button( __("Invite as User") );
        
        // note: this is async - the result takes a while (therefore not in before_save)
        check_duplicates(frm);
        
        // action buttons
        if (!frm.doc.__islocal) {
            frm.add_custom_button(__("Quotation"), function() {
                create_quotation(frm);
            }, __("Create"));
            
            if ((frm.doc.links) && (frm.doc.links.length > 0)) {
                frm.add_custom_button(__("Change Company"), function() {
                    change_company(frm);
                });
            }
        }
    },
    before_save: function(frm) {
        if (frm.doc.contact_function === "Primary") {
            cur_frm.set_value("is_primary_contact", 1);
        }
    },
    after_save: function(frm) {
        // transmit to Brevo
        if ((!frm.doc.unsubscribed) 
            && (frm.doc.email_id) 
            && (['Lead', 'Prospect', 'Customer'].includes(frm.doc.status))) {
            upload_to_brevo(frm);
        }
    },
    first_name: function(frm) {
        update_full_name(frm);
    },
    last_name: function(frm) {
        update_full_name(frm);
    }
});

// Utility function to validate email
function validate_email(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

function attach_header_form_handlers() {
    document.getElementById('email').onchange = function() {
        let updated = false;
        let new_email = document.getElementById('email').value;
        if (new_email) {
            if (validate_email(new_email)) {
                if (cur_frm.doc.email_ids) {
                    for (let i = 0; i < cur_frm.doc.email_ids.length; i++) {
                        if (cur_frm.doc.email_ids[i].is_primary) {
                            frappe.model.set_value(cur_frm.doc.email_ids[i].doctype, cur_frm.doc.email_ids[i].name, 'email_id', document.getElementById('email').value);
                            updated = true;
                            break;
                        }
                    }
                }
                if (!updated) {
                    var child = cur_frm.add_child('email_ids');
                    frappe.model.set_value(child.doctype, child.name, 'email_id', document.getElementById('email').value);
                    frappe.model.set_value(child.doctype, child.name, 'is_primary', 1);
                    
                }
                // cur_frm.set_value('email_id', document.getElementById('email').value);
                cur_frm.refresh_field('email_ids');
            } else {
                frappe.msgprint({
                    'message': __("Invalid email"), 
                    'title': __("Validation"), 
                    'indicator': 'red'
                });
            }
        } else {
            // email was cleared, remove
            if (cur_frm.doc.email_ids) {
                for (let i = 0; i < cur_frm.doc.email_ids.length; i++) {
                    if (cur_frm.doc.email_ids[i].is_primary) {
                        cur_frm.get_field("email_ids").grid.grid_rows[i].remove();
                        break;
                    }
                }
            }
        }
    };
    document.getElementById('phone').onchange = function() {
        let updated = false;    // default is false: insert in case there is nothing to update
        let phone_no = document.getElementById('phone').value;
        if (!phone_no) {
            // phone was cleared - remove if there is a primary phone
            if (cur_frm.doc.phone_nos) {
                for (let i = 0; i < cur_frm.doc.phone_nos.length; i++) {
                    if (cur_frm.doc.phone_nos[i].is_primary_phone) {
                        cur_frm.get_field("phone_nos").grid.grid_rows[i].remove();
                        break;
                    }
                }
            }
        } else {
            if (cur_frm.doc.phone_nos) {
                for (let i = 0; i < cur_frm.doc.phone_nos.length; i++) {
                    if (cur_frm.doc.phone_nos[i].is_primary_phone) {
                        frappe.model.set_value(cur_frm.doc.phone_nos[i].doctype, cur_frm.doc.phone_nos[i].name, 'phone', phone_no);
                        updated = true;
                        break;
                    }
                }
            }
            if (!updated) {
                var child = cur_frm.add_child('phone_nos');
                frappe.model.set_value(child.doctype, child.name, 'phone', document.getElementById('phone').value);
                frappe.model.set_value(child.doctype, child.name, 'is_primary_phone', 1);
                
            }
        }
        // cur_frm.set_value('phone', document.getElementById('phone').value);
        cur_frm.refresh_field('phone_nos');
    };
}

function check_duplicates(frm) {
    frappe.call({
        'method': 'frappe.client.get_list',
        'args': {
            'doctype': 'Contact',
            'filters': [
                ['email_id', '=', frm.doc.email_id]
            ],
            'fields': ['name', 'email_id'],
        },
        'callback': function(response) {
            if ((response.message) && (response.message.length > 1)) {
                let message = __("Please check the following contacts with the same email id:") + "<br>";
                for (let i = 0; i < response.message.length; i++) {
                    message += "<a href='" + frappe.utils.get_form_link("Contact", response.message[i].name)
                        + "' target='_blank'>" + response.message[i].name + "</a> (" + response.message[i].email_id + ")<br>";
                }
                frappe.msgprint({
                    'message': message, 
                    'title': __("Duplicates detected"), 
                    'indicator': 'red'
                });
            }
        }
    });
}

function create_quotation(frm) {
    if ((!frm.doc.links) || (frm.doc.links.length === 0)) {
        // ask for company name
        frappe.prompt([
                {'fieldname': 'company_name', 'fieldtype': 'Data', 'label': __('Company Name'), 'reqd': 1, 'default': frm.doc.company_name},
                {'fieldname': 'customer_group', 'fieldtype': 'Link', 'label': __('Customer Group'), 'reqd': 1, 'options': 'Customer Group'},
                {'fieldname': 'territory', 'fieldtype': 'Link', 'label': __('Territory'), 'reqd': 1, 'options': 'Territory'}
            ],
            function(values) {
                cur_frm.set_value('company_name', values.company_name);
                
                frappe.call({
                    'method': "amf.master_crm.utils.make_customer",
                    'args': {
                        'company_name': values.company_name,
                        'customer_group': values.customer_group,
                        'territory': values.territory
                    },
                    'callback': function(response) {
                        // link customer
                        let child = cur_frm.add_child('links');
                        frappe.model.set_value(child.doctype, child.name, 'link_doctype', 'Customer');
                        frappe.model.set_value(child.doctype, child.name, 'link_name', response.message.name);
                        cur_frm.refresh_field('links');
                        cur_frm.save().then(function() {
                            make_quotation(cur_frm);
                        });
                    }
                });
            
            },
            __('Enter Company Name'),
            __('OK')
        );
    } else {
        // customer available
        make_quotation(frm);
    }
}


function make_quotation(frm) {
    frappe.model.open_mapped_doc({
        'method': "amf.master_crm.utils.make_quotation",
        'args': {
            'contact_name': frm.doc.name
        },
        'frm': frm
    })
}

function upload_to_brevo(frm) {
    frappe.call({
        'method': 'amf.master_crm.doctype.brevo.brevo.create_update_contact',
        'args': {
            'contact': frm.doc.name,
            'list_ids': [42]
        },
        'callback': function(response) {
            frappe.show_alert("Brevo: " + response.message.status /* + " - " + response.message.text */);
        }
    });
}

function update_full_name(frm) {
    cur_frm.set_value("full_name", (frm.doc.first_name || "") + " " + (frm.doc.last_name || ""));
}

function change_company(frm) {
    let customer = null;
    let row_name = null;
    if (frm.doc.links) {
        for (let i = 0; i < frm.doc.links.length; i++) {
            if (frm.doc.links[i].link_doctype === "Customer") {
                customer = frm.doc.links[i].link_name;
                row_name = frm.doc.links[i].name;
            }
        }
    }
    frappe.prompt([
        {
            'fieldname': 'customer', 
            'fieldtype': 'Link', 
            'label': __('Company'), 
            'options': 'Customer', 
            'default': customer,
            'reqd': 1
        }  
    ],
    function(values){
        frappe.model.set_value(frm.doc.links[0].doctype, row_name, 'link_name', values.customer);
        cur_frm.save();
    },
    __("Change linked Company"),
    __('Change')
    );
}
