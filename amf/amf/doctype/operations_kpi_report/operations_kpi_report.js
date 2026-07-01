frappe.ui.form.on('Operations KPI Report', {
    setup: function(frm) {
        if (frm.is_new() && frm.doc.generate_ai_insights === undefined) {
            frm.set_value('generate_ai_insights', 1);
        }
        if (frm.is_new() && !frm.doc.report_mode) {
            frm.set_value('report_mode', 'Single Period');
        }
    },

    refresh: function(frm) {
        set_period_field_visibility(frm);
        if (frm.is_new()) {
            return;
        }

        if (['Draft', 'Completed', 'Completed with Warnings', 'Failed'].includes(frm.doc.status)) {
            frm.add_custom_button(__('Generate Report'), function() {
                frappe.call({
                    method: 'amf.amf.doctype.operations_kpi_report.operations_kpi_report.enqueue_generation',
                    args: {
                        name: frm.doc.name,
                        force: 1
                    },
                    freeze: true,
                    freeze_message: __('Queuing report generation'),
                    callback: function() {
                        frm.reload_doc();
                    }
                });
            }, __('Actions'));
        }

        if (
            ['Completed', 'Completed with Warnings'].includes(frm.doc.status)
            && frm.doc.ai_status !== 'Approval Required'
        ) {
            frm.add_custom_button(__('Send Email'), function() {
                frappe.call({
                    method: 'amf.amf.doctype.operations_kpi_report.operations_kpi_report.send_report_email',
                    args: {
                        name: frm.doc.name
                    },
                    freeze: true,
                    freeze_message: __('Queuing report email'),
                    callback: function() {
                        frm.reload_doc();
                    }
                });
            }, __('Actions'));
        }

        if (frm.doc.ai_status === 'Approval Required') {
            frm.add_custom_button(__('Approve AI Insights'), function() {
                frappe.call({
                    method: 'amf.amf.doctype.operations_kpi_report.operations_kpi_report.approve_ai_insights',
                    args: {name: frm.doc.name},
                    freeze: true,
                    freeze_message: __('Approving insights and rebuilding report files'),
                    callback: function() {
                        frm.reload_doc();
                    }
                });
            }, __('AI Review'));
        }

        if (['Approval Required', 'Approved'].includes(frm.doc.ai_status)) {
            frm.add_custom_button(__('Reject AI Insights'), function() {
                frappe.prompt(
                    [{
                        fieldname: 'reason',
                        fieldtype: 'Small Text',
                        label: __('Rejection Reason'),
                        reqd: 1
                    }],
                    function(values) {
                        frappe.call({
                            method: 'amf.amf.doctype.operations_kpi_report.operations_kpi_report.reject_ai_insights',
                            args: {
                                name: frm.doc.name,
                                reason: values.reason
                            },
                            freeze: true,
                            freeze_message: __('Removing AI content and rebuilding report files'),
                            callback: function() {
                                frm.reload_doc();
                            }
                        });
                    },
                    __('Reject AI Insights'),
                    __('Reject')
                );
            }, __('AI Review'));
        }

        if (frm.doc.ai_status === 'Rejected') {
            frm.add_custom_button(__('Approve AI Insights'), function() {
                frappe.call({
                    method: 'amf.amf.doctype.operations_kpi_report.operations_kpi_report.approve_ai_insights',
                    args: {name: frm.doc.name},
                    freeze: true,
                    freeze_message: __('Approving insights and rebuilding report files'),
                    callback: function() {
                        frm.reload_doc();
                    }
                });
            }, __('AI Review'));
        }
    },

    period_type: function(frm) {
        set_period_field_visibility(frm);
        if (frm.doc.period_type === 'Semester') {
            const today = frappe.datetime.get_today();
            const month = Number(today.slice(5, 7));
            if (!frm.doc.reporting_year) {
                frm.set_value('reporting_year', Number(today.slice(0, 4)));
            }
            if (!frm.doc.reporting_semester) {
                frm.set_value('reporting_semester', month <= 6 ? 'H1' : 'H2');
            }
        }
        set_default_comparison_period(frm);
    },

    reporting_month: function(frm) {
        set_default_comparison_period(frm);
    },

    reporting_year: function(frm) {
        set_default_comparison_period(frm);
    },

    reporting_semester: function(frm) {
        set_default_comparison_period(frm);
    },

    report_mode: function(frm) {
        set_period_field_visibility(frm);
        set_default_comparison_period(frm);
    }
});

function set_period_field_visibility(frm) {
    const is_semester = frm.doc.period_type === 'Semester';
    const is_comparative = frm.doc.report_mode === 'Comparative';
    frm.toggle_display('reporting_month', !is_semester);
    frm.toggle_display('reporting_year', is_semester);
    frm.toggle_display('reporting_semester', is_semester);
    frm.toggle_display('comparison_month', is_comparative && !is_semester);
    frm.toggle_display('comparison_year', is_comparative && is_semester);
    frm.toggle_display('comparison_semester', is_comparative && is_semester);
    frm.toggle_display('comparison_period_start', is_comparative);
    frm.toggle_display('comparison_period_end', is_comparative);
}

function set_default_comparison_period(frm) {
    if (frm.doc.report_mode !== 'Comparative') {
        return;
    }
    if (frm.doc.period_type === 'Semester') {
        if (!frm.doc.reporting_year || !frm.doc.reporting_semester) {
            return;
        }
        let comparison_year = Number(frm.doc.reporting_year);
        let comparison_semester = 'H1';
        if (frm.doc.reporting_semester === 'H1') {
            comparison_year -= 1;
            comparison_semester = 'H2';
        }
        if (!frm.doc.comparison_year) {
            frm.set_value('comparison_year', comparison_year);
        }
        if (!frm.doc.comparison_semester) {
            frm.set_value('comparison_semester', comparison_semester);
        }
        return;
    }
    if (!frm.doc.reporting_month || frm.doc.comparison_month) {
        return;
    }
    frm.set_value(
        'comparison_month',
        frappe.datetime.add_months(frm.doc.reporting_month, -1)
    );
}
