/* Script extensions for customer
 * 
 */
 
frappe.ui.form.on('Customer', {
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
