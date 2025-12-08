// Copyright (c) 2025, libracore AG and contributors
// For license information, please see license.txt

frappe.ui.form.on('Timer Production', {
	refresh(frm) {
		if (!frm.doc.status) return;

		if (frm.doc.status === 'IN PROCESS') {
			frm.page.set_indicator(__('In Process'), 'orange');
		} else if (frm.doc.status === 'FINISHED') {
			frm.page.set_indicator(__('Finished'), 'green');
		} else if (frm.doc.status === 'PAUSED') {
			frm.page.set_indicator(__('Paused'), 'blue');
		} else {
			frm.page.set_indicator(__('Unknown'), 'gray');
		}
	}
});

