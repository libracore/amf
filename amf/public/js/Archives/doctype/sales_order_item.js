frappe.ui.form.on('Sales Order Item', {
	item_code: function(frm, cdt, cdn) {
        var row = locals[cdt][cdn];
        if (row.item_code) {
            frappe.call({
                method: 'frappe.client.get',
                args: {
                    doctype: 'Item',
                    name: row.item_code
                },
                callback: function(r) {
                    if (r.message) {
                        var default_warehouse = r.message.default_warehouse;
                        if (default_warehouse) {
                            frappe.model.set_value(cdt, cdn, 'warehouse', default_warehouse);
                        }
                    }
                }
            });
        }
    },
	refresh(frm) {
		// your code here
	}
})