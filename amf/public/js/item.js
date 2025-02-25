function suggest_item_code(frm) {
    // Only do this if the document is new and we have both item_group + item_type
    if (frm.is_new() && frm.doc.item_group && frm.doc.item_type) {
        frappe.call({
            method: 'amf.amf.utils.item_master.get_max_six_digit_item_code',
            args: {
                item_group: frm.doc.item_group,
                item_type: frm.doc.item_type
            },
            callback: function(r) {
                if (!r.exc && r.message) {
                    let highest_code = parseInt(r.message, 10) || 0;
                    let next_code = highest_code + 1;
                    // Convert the numeric value back into 6 digits, zero-padded
                    let padded = String(next_code).padStart(6, '0');
                    frm.set_value('item_code', padded);
                }
            }
        });
    }
}

frappe.ui.form.on('Item', {
    item_group: function(frm) {
        if (frm.doc.item_type)
            suggest_item_code(frm);
    },
});
