frappe.ui.form.on("Quality Inspection", {
    refresh(frm) {
    },

    onload(frm) {
        // Set the item_code field to not required
        frm.set_df_property("item_code", "reqd", 0);
        frm.set_df_property("sample_size", "reqd", 0);
    },
});
