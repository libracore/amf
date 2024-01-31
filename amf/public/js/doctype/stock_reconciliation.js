frappe.ui.form.on('Stock Reconciliation', {
    refresh: function (frm) {
        frm.add_custom_button('Clean Item Stock', function () {
            frappe.call({
                method: 'amf.www.item_information.zero_out_stock_for_items',
                args: { 'name': frm.doc.name },
                callback: function (r) {
                    if (r.message == 'success') {
                        frm.reload_doc();
                    }
                }
            });
        });
    }
});
