frappe.ui.form.on("Work Order", {
    onload: function(frm) {
        toggle_estimated_manufacturing_time(frm);
    },
    refresh: function(frm) {
        toggle_estimated_manufacturing_time(frm);
    },
    production_item: function(frm) {
        toggle_estimated_manufacturing_time(frm);
    },
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

function toggle_estimated_manufacturing_time(frm) {
    var item_code = cstr(frm.doc.production_item || "");
    var show_field = /^(10|20)\d{4}$/.test(item_code);
    frm.toggle_display("temps_de_fabrication_estime", show_field);
    frm.toggle_display("temps_de_fabrication_estime_jours", show_field);
}

// extend/create dashboard
cur_frm.dashboard.add_transactions([
    {
        'label': __("Planning"),
        'items': ["Planning"]
    },
    {
        'label': __("Timer"),
        'items': ["Timer Production"]
    },
]);
