frappe.ui.form.on("Work Order", {
    status: function(frm) {
        if (frm.doc.status === "Completed") {
            frm.set_value("progress", "QC");
        }
    },
    docstatus: function(frm) {
        if (frm.doc.docstatus === 1) {
            frm.set_value("progress", "QC");
        }
    },
});