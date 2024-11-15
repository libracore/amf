/* Script extensions for customer
 * 
 */
 
frappe.ui.form.on('Customer', {
    refresh: function(frm) {
        if (!frm.doc.__islocal) {
            frm.add_custom_button(__("Link Contact"), function() {
                frappe.prompt(
                    [
                        {'fieldname': 'contact', 'fieldtype': 'Link', 'label': __('Contact'), 'reqd': 1, 'options': 'Contact'}  
                    ],
                    function(values){
                        link_contact(values.contact, frm.doc.name);
                    },
                    __('Link existing contact'),
                    __('Add link')
                );
            });
        }
    },
    validate: function(frm) {
        if ((frm.doc.is_customer === 1) && (!frm.doc.accounting_email)) {
            frappe.msgprint( __("Please set an accounting email for a customer."), __("Validation") );
            frappe.validated=false;
        }
        if (!frm.doc.customer_primary_address) {
            frappe.msgprint( __("Please set a primary customer address."), __("Validation") );
        }
    }
});

function link_contact(contact, customer) {
    frappe.call({
        'method': 'amf.master_crm.utils.link_contact_to_customer',
        'args': {
            'contact': contact,
            'customer': customer
        },
        'callback': function(r) {
            cur_frm.reload_doc();
        }
    });
}
