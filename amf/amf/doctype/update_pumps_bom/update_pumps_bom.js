// Copyright (c) 2025, libracore AG and contributors
// For license information, please see license.txt

frappe.ui.form.on('Update Pumps BOM', {
    update_pumps_bom_button: function() {
        frappe.call({
            method: 'amf.amf.utils.bom_updating_for_pump.enqueue_update_pumps_bom',
            freeze: true,
            callback: function(response) {
                const message = response?.message || __('BOM update has been queued.');
                frappe.msgprint(message);
            },
            error() {
                frappe.msgprint(__('Failed to queue the pump BOM update. Please check the error log.'));
            }
        });
    },
});
