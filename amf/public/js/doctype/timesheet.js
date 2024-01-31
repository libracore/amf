frappe.ui.form.on('Timesheet', {
	refresh(frm) {
		// your code here
	}
});


frappe.ui.form.on('Timesheet Detail', {
    time_logs_add(frm, cdt, cdn) {
        /* this is a hotfix to clear project and task in new rows */
        frappe.model.set_value(cdt, cdn, "project", null);
        frappe.model.set_value(cdt, cdn, "task", null);
        // take last time step
        var row_idx = frappe.model.get_value(cdt, cdn, 'idx');
        if (row_idx > 1) {
            var last_time = frm.doc.time_logs[row_idx - 2].to_time;
            if (last_time) {
                frappe.model.set_value(cdt, cdn, 'from_time', last_time);
            }
        }
    }
});