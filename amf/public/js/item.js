function suggest_item_code(frm) {
    // Only do this if the document is new and we have both item_group + item_type
    if (frm.is_new() && frm.doc.item_group && frm.doc.item_type) {
        frappe.call({
            method: 'amf.amf.doctype.item_creation.item_creation.get_last_item_code',
            callback: function(r) {
                if (!r.exc && r.message) {
                    switch (frm.doc.item_group) {
                        case "Valve Head":
                            frm.set_value('item_code', '300' + r.message);
                            break;
                        case "Valve Seat":
                            if (frm.doc.item_type == 'Component')
                                frm.set_value('item_code', '200' + r.message);
                            else if (frm.doc.item_type == 'Sub-Assembly')
                                frm.set_value('item_code', '210' + r.message);
                            break;
                        case "Plug":
                            if (frm.doc.item_type == 'Component')
                                frm.set_value('item_code', '100' + r.message);
                            else if (frm.doc.item_type == 'Sub-Assembly')
                                frm.set_value('item_code', '110' + r.message);
                            break;
                    }
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
