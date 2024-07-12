/*
Contact Client Custom Script
----------------------------
*/
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
        
    },
    email_id: function(frm) {
        // Ensure the email_id field is not empty, trimmed, and valid
        const email = (frm.doc.email_id || '').trim();
        if (!email) {
            frappe.msgprint(__('Email cannot be empty.'));
            return;
        }
        if (!validate_email(email)) {
            frappe.msgprint(__('Invalid email format.'));
            return;
        }

        // Check if email already exists in the child table
        const emailExists = frm.doc.email_ids.some(entry => entry.email_id === email);
        if (emailExists) {
            frappe.msgprint(__('This email already exists in the list.'));
            return;
        }

        try {
            // Add a new row in the child table 'email_ids'
            const contactDetail = frm.add_child('email_ids');
            contactDetail.email_id = email;
            frm.refresh_field('email_ids');
        } catch (error) {
            console.error('Error adding email to contact:', error);
            frappe.msgprint(__('There was an error adding the email. Please try again.'));
        }
    },
});

// Utility function to validate email
function validate_email(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

function attach_header_form_handlers() {
    document.getElementById('email').onchange = function() {
        let updated = false;
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
        cur_frm.set_value('email_id', document.getElementById('email').value);
        cur_frm.refresh_field('email_ids');
    };
    document.getElementById('phone').onchange = function() {
        let updated = false;
        if (cur_frm.doc.phone_nos) {
            for (let i = 0; i < cur_frm.doc.phone_nos.length; i++) {
                if (cur_frm.doc.phone_nos[i].is_primary_phone) {
                    frappe.model.set_value(cur_frm.doc.phone_nos[i].doctype, cur_frm.doc.phone_nos[i].name, 'phone', document.getElementById('phone').value);
                    updated = true;
                    break;
                }
            }
        }
        if (!updated) {
            var child = cur_frm.add_child('email_ids');
            frappe.model.set_value(child.doctype, child.name, 'phone', document.getElementById('phone').value);
            frappe.model.set_value(child.doctype, child.name, 'is_primary_phone', 1);
            
        }
        //cur_frm.set_value('phone', document.getElementById('phone').value);
        cur_frm.refresh_field('phone_nos');
    };
}
