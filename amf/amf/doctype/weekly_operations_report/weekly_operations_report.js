frappe.ui.form.on('Weekly Operations Report', {
    refresh: function(frm) {
        if (frm.is_new()) {
            return;
        }

        if (['Draft', 'Completed', 'Failed'].includes(frm.doc.status)) {
            frm.add_custom_button(__('Generate Slide'), function() {
                frappe.call({
                    method: 'amf.amf.doctype.weekly_operations_report.weekly_operations_report.generate_report',
                    args: {name: frm.doc.name, force: 1},
                    freeze: true,
                    freeze_message: __('Generating weekly operations slide'),
                    callback: function() {
                        frm.reload_doc();
                    }
                });
            }, __('Actions'));
        }

        if (frm.doc.status === 'Completed' && frm.doc.output_file) {
            frm.add_custom_button(__('Send Email'), function() {
                frappe.call({
                    method: 'amf.amf.doctype.weekly_operations_report.weekly_operations_report.send_report_email',
                    args: {name: frm.doc.name},
                    freeze: true,
                    freeze_message: __('Queuing weekly operations email'),
                    callback: function() {
                        frm.reload_doc();
                    }
                });
            }, __('Actions'));
        }
    }
});
