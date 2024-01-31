/*
Work Order Script
--------------------

*/
frappe.ui.form.on('Work Order', {
    before_save: function (frm) {
        frm.set_value('actual_start_date', frappe.datetime.nowdate());
        frm.set_value('actual_end_date', frappe.datetime.nowdate());
        frm.set_value('p_s_d', frappe.datetime.nowdate());
        var start_date = frm.doc.p_s_d;
        if (start_date) {
            frm.set_value('p_e_d', frappe.datetime.add_days(start_date, 1));
        }
        frm.refresh_fields('p_e_d');
        if (frm.doc.sales_order) {
            frappe.call({
                method: "frappe.client.get_value",
                args: {
                    doctype: "Sales Order",
                    filters: {
                        name: frm.doc.sales_order
                    },
                    fieldname: "delivery_date"
                },
                callback: function (response) {
                    if (response.message && response.message.delivery_date) {
                        frm.set_value('p_e_d', response.message.delivery_date);
                        frm.refresh_fields('p_e_d');
                    }
                }
            });
        }
    },
    
    end_date_time: function (frm) {
        calculate_duration(frm);
    },

    refresh(frm) {
        if (frm.is_new()) {
            frm.set_value('duration', 0);
            console.log("Duration is null.");
        }

        if (frm.doc.docstatus === 1 && frm.doc.status === 'In Process') {
            frm.add_custom_button(__('<i class="fa fa-print"></i> • Print'), function () {
                var w = window.open(frappe.urllib.get_full_url("/api/method/frappe.utils.print_format.download_pdf?"
                    + "doctype=" + encodeURIComponent("Work Order")
                    + "&name=" + encodeURIComponent(frm.doc.name)
                    + "&format=" + encodeURIComponent("Internal Work Order")
                    + "&no_letterhead=" + encodeURIComponent("1")
                ));
                if (!w) {
                    frappe.msgprint(__("Please enable pop-ups")); return;
                }
            });
        }
    },
    
    sales_order: function(frm) {
        // Check if sales_order field has a value
        if(frm.doc.sales_order)
            frappe.call({
                method: "frappe.client.get_value",
                args: {
                    doctype: "Sales Order",
                    filters: {
                        name: frm.doc.sales_order
                    },
                    fieldname: ["customer"]
                },
                callback: function(r) {
                    if(r.message)
                        frm.set_value('custo_detail', r.message.customer);
                }
            });
    }
    
});

function calculate_duration(frm) {
    try {
        let start_date_time = frm.doc.start_date_time;
        let end_date_time = frm.doc.end_date_time;

        if (!start_date_time) {
            frappe.msgprint('Start date-time is not set.');
            return;
        }

        if (!end_date_time) {
            frm.set_value('duration', 0);
            return;
        }
        
        console.log(`Start: ${start_date_time} • End: ${end_date_time}`);

        let startDate = moment(start_date_time);
        let endDate = moment(end_date_time);

        if (!startDate.isValid() || !endDate.isValid()) {
            frappe.msgprint('Invalid date-time format.');
            return;
        }

        let durationInSeconds = endDate.diff(startDate, 'seconds');
        
        if (durationInSeconds <= 0) {
            frappe.msgprint('End date-time should be greater than start date-time.');
            return;
        }

        frm.set_value('duration', durationInSeconds);
        frm.save('Update');

    } catch (error) {
        console.error("An error occurred during the duration calculation:", error);
        frappe.msgprint('An error occurred during the duration calculation. Please check the console for details.');
    }
}