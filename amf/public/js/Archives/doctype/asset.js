/*
Asset Script
--------------------

What this does:
* Sets Depreciation Start Date equal to Purchase Date

*/
frappe.ui.form.on("Asset", {
    before_save: function(frm) {
        if ((frm.doc.finance_books) && (frm.doc.finance_books.length > 0)) {
            frm.get_field("finance_books").grid.grid_rows[0].doc.depreciation_start_date = frm.doc.purchase_date;
            frm.get_field("finance_books").grid.grid_rows[0].refresh_field("depreciation_start_date");
        }
        frm.doc.available_for_use_date = frm.doc.purchase_date;
    }
});


