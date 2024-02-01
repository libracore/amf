/*
Contact Client Custom Script
----------------------------
*/
frappe.ui.form.on('Contact', {
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
