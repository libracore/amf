/*
Payment Entry Script
--------------------

What this does:
* Automatically sets the posting date to the supplier invoice date

*/
frappe.ui.form.on('Payment Entry', {
    validate: function(frm) {
    frm.doc.posting_date = frm.doc.reference_date;
}
});