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

    refresh(frm) {
        //calculate_duration(frm);

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
});

// A separate function to calculate the duration
function calculate_duration(frm) {
    let start_date_time = frm.doc.start_date_time;
    console.log(start_date_time);
    let end_date_time = frm.doc.end_date_time;
    console.log(end_date_time);
    if (!end_date_time) {
        frm.set_value('duration', 0);
    }
    let duration = frm.doc.duration;
    console.log(!duration);

    if (start_date_time && end_date_time && !duration) {
        // Convert both dates to JavaScript Date objects
        console.log("In the calculation loop.");
        let startDate = new Date(start_date_time);
        let endDate = new Date(end_date_time);

        // Calculate the time difference in milliseconds
        let timeDifference = endDate - startDate;

        // Convert to seconds (and further to minutes or hours as you like)
        let seconds = timeDifference / 1000;

        // Set the calculated duration to the 'duration' field in the form
        frm.set_value('duration', seconds);

        // Save the form automatically after setting duration
        frm.save('Update');
    }
}