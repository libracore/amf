frappe.ui.form.on('Operations KPI Report Settings', {
    refresh: function(frm) {
        frm.add_custom_button(__('Generate Previous Month Now'), function() {
            frappe.call({
                method: 'amf.amf.doctype.operations_kpi_report_settings.operations_kpi_report_settings.generate_previous_month_now',
                freeze: true,
                freeze_message: __('Generating operations report'),
                callback: function(response) {
                    if (response.message && response.message.name) {
                        frappe.set_route('Form', 'Operations KPI Report', response.message.name);
                    }
                }
            });
        });

        frm.add_custom_button(__('Generate Previous Month Comparison Now'), function() {
            frappe.call({
                method: 'amf.amf.doctype.operations_kpi_report_settings.operations_kpi_report_settings.generate_previous_month_comparison_now',
                freeze: true,
                freeze_message: __('Generating comparative operations report'),
                callback: function(response) {
                    if (response.message && response.message.name) {
                        frappe.set_route('Form', 'Operations KPI Report', response.message.name);
                    }
                }
            });
        });

        frm.add_custom_button(__('Generate Previous Semester Now'), function() {
            frappe.call({
                method: 'amf.amf.doctype.operations_kpi_report_settings.operations_kpi_report_settings.generate_previous_semester_now',
                freeze: true,
                freeze_message: __('Generating semester operations report'),
                callback: function(response) {
                    if (response.message && response.message.name) {
                        frappe.set_route('Form', 'Operations KPI Report', response.message.name);
                    }
                }
            });
        });

        frm.add_custom_button(__('Generate Previous Semester Comparison Now'), function() {
            frappe.call({
                method: 'amf.amf.doctype.operations_kpi_report_settings.operations_kpi_report_settings.generate_previous_semester_comparison_now',
                freeze: true,
                freeze_message: __('Generating comparative semester operations report'),
                callback: function(response) {
                    if (response.message && response.message.name) {
                        frappe.set_route('Form', 'Operations KPI Report', response.message.name);
                    }
                }
            });
        });

        frm.add_custom_button(__('Generate Current Semester Now'), function() {
            frappe.call({
                method: 'amf.amf.doctype.operations_kpi_report_settings.operations_kpi_report_settings.generate_current_semester_now',
                freeze: true,
                freeze_message: __('Generating current semester operations report'),
                callback: function(response) {
                    if (response.message && response.message.name) {
                        frappe.set_route('Form', 'Operations KPI Report', response.message.name);
                    }
                }
            });
        });
    }
});
