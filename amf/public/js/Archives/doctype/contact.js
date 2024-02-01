frappe.ui.form.on('Contact', {
	email_id: function(frm) {
		if (frm.doc.email_id) {
		    // Check if email already exists in the child table
		    let email_exists = frm.doc.email_ids.some(entry => entry.email_id === frm.doc.email_id);

		    if (!email_exists) {
		        // Add a new row in the child table 'email_ids'
		        var contact_detail = frm.add_child('email_ids');
		        // Set the email_id field of the new row
		        contact_detail.email_id = frm.doc.email_id;
		        // Refresh the form to show the changes
		        frm.refresh_field('email_ids');
		    } else {
		        frappe.msgprint(__('This email already exists in the list.'));
		    }
		}
	},
});
