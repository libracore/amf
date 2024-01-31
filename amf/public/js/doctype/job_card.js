frappe.ui.form.on('Job Card', {
	onload: function(frm) {
        if (frm.is_new()) {
            if (!frm.doc.work_order) {
                frm.set_value("work_order", "OF-00072");
            }
            frm.set_value("employee", "HR-EMP-00003");
            frm.set_value("operation", "General Assembly");
            let new_row = frm.add_child("time_logs");
            new_row.from_time = frappe.datetime.now_datetime();
            new_row.to_time = new_row.from_time;
            // Fetch the Work Order
            frappe.call({
                method: 'frappe.client.get',
                args: {
                    doctype: 'Work Order',
                    name: frm.doc.work_order
                },
                callback: function(response) {
                    var work_order = response.message;
                }
            });
            frm.refresh_field("time_logs");
        }
    },
    
    after_save: function(frm) {
        //$.each(frm.doc.time_logs || [], function(i, d) {
        //    d.completed_qty = frm.doc.for_quantity;
        //});
    },
    
    before_save: function(frm) {
        $.each(frm.doc.time_logs || [], function(i, d) {
            d.completed_qty = frm.doc.for_quantity;
        });
    },
    
    refresh: function(frm) {
        frm.refresh_field("time_logs");
        if (frm.doc.docstatus === 1) { // Check if Job Card is submitted
            frm.add_custom_button(__('<i class="fa fa-file-text" aria-hidden="true"></i>&nbsp;&nbsp;•&nbsp;&nbsp;Create Stock Entry'), function() {
                // Create a new dialog
                var dialog = new frappe.ui.Dialog({
                    title: 'Create New Stock Entry',
                    fields: [
                        {'fieldname': 'stock_entry_type', 'fieldtype': 'Data', 'option': 'Stock Entry Type', 'label': 'Stock Entry Type', 'default': 'Manufacture', 'reqd': 1},
                        {'fieldname': 'item_code', 'fieldtype': 'Link', 'options': 'Item', 'label': 'Item Code', 'default': frm.doc.product_item, 'reqd': 1},
                        {'fieldname': 't_warehouse', 'fieldtype': 'Link', 'options': 'Warehouse', 'label': 'Target Warehouse', 'default': 'Main Stock - AMF21', 'reqd': 1},
                        {'fieldname': 'qty', 'fieldtype': 'Float', 'label': 'Quantity', 'default': frm.doc.total_completed_qty, 'reqd': 1},
                        {'fieldname': 'serial_no', 'fieldtype': 'Small Text', 'label': 'Serial No', 'reqd': 0},
                        {'fieldname': 'batch_no', 'fieldtype': 'Data', 'label': 'Batch No', 'reqd': 0},
                        // Add other fields as necessary
                    ],
                    primary_action: function() {
                        // Gather the data and create the new Stock Entry
                        var data = dialog.get_values();
                        frappe.call({
                            method: 'frappe.client.insert',
                            args: {
                                doc: {
                                    doctype: 'Stock Entry',
                                    stock_entry_type: data.stock_entry_type,
                                    items: [
                                        {
                                            doctype: 'Stock Entry Detail',
                                            item_code: data.item_code,
                                            t_warehouse: data.t_warehouse,
                                            qty: data.qty,
                                            serial_no: data.serial_no,
                                            batch_no: data.batch_no,
                                            // additional fields if needed
                                        },
                                    ],
                                    // additional fields if needed
                                },
                            },
                            callback: function(response) {
                                if (!response.exc) {
                                    frappe.show_alert(__('Stock Entry {0} created', [response.message.name]), 7);
                                    frappe.set_route('Form', 'Stock Entry', response.message.name);
                                }
                            },
                        });
                        dialog.hide();
                    },
                    primary_action_label: 'Submit'
                });
                dialog.show();
            });
        }
    }
});