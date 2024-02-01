/*
Asset Client Custom Script
--------------------------
*/
frappe.ui.form.on("Asset", {
    refresh: function (frm) {
        console.log("Refresh function.")
    },

    before_save: function (frm) {
        // Ensure the finance_books and purchase_date fields are not undefined or null
        if (!frm.doc.finance_books || !frm.doc.purchase_date) {
            console.error("Missing finance_books or purchase_date in the form.");
            return;
        }

        // If finance_books is available and not empty, set depreciation_start_date for each entry
        if (frm.doc.finance_books.length > 0) {
            frm.doc.finance_books.forEach((entry, index) => {
                const financeBookRow = cur_frm.fields_dict["finance_books"].grid.grid_rows[index];
                if (financeBookRow && financeBookRow.doc) {
                    financeBookRow.doc.depreciation_start_date = frm.doc.purchase_date;
                    financeBookRow.refresh_field("depreciation_start_date");
                } else {
                    console.error(`Finance book row at index ${index} is undefined or does not have a doc property.`);
                }
            });
        } else {
            console.warn("Finance books are defined but the array is empty.");
        }

        // Set available_for_use_date equal to purchase_date
        frm.doc.available_for_use_date = frm.doc.purchase_date;
    }
});