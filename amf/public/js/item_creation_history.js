// Use the same searchable execution history from either side of a result link.
["Item", "BOM"].forEach(doctype => {
    frappe.ui.form.on(doctype, {
        refresh(frm) {
            if (frm.doc.__islocal || !frappe.model.can_read("Item Creation")) return;
            frm.add_custom_button(__("Item Creation History"), () => {
                frappe.route_options = {[doctype === "Item" ? "item_code" : "bom"]: frm.doc.name};
                frappe.set_route("query-report", "Item Creation Results");
            });
        },
    });
});
