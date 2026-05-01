/*
Purchase Invoice Script
-----------------------

Shows a reminder for transport supplier invoices and offers a shortcut to create
a Landed Cost Voucher prefilled with the net transport cost.
*/

frappe.ui.form.on("Purchase Invoice", {
    after_save: function(frm) {
        amf_show_transport_invoice_lcv_reminder(frm);
    },
});

function amf_show_transport_invoice_lcv_reminder(frm) {
    if (!frm.doc.supplier) {
        return;
    }

    frappe.db.get_value("Supplier", frm.doc.supplier, "supplier_group", function(supplier) {
        if (!supplier || supplier.supplier_group !== "Transport") {
            return;
        }

        amf_show_transport_invoice_dialog(frm);
    });
}

function amf_show_transport_invoice_dialog(frm) {
    var reminder_key = [frm.doctype, frm.doc.name, frm.doc.modified].join(":");

    if (frm._amf_transport_invoice_reminder_key === reminder_key) {
        return;
    }

    frm._amf_transport_invoice_reminder_key = reminder_key;

    var message = __("If this transport invoice relates to incoming stock, please use item PRD.4405 and create a Landed Cost Voucher for the net transport cost (minus VAT).");
    var dialog = new frappe.ui.Dialog({
        title: __("Transport Invoice"),
        fields: [
            {
                fieldname: "message",
                fieldtype: "HTML",
                options: "<p>" + frappe.utils.escape_html(message) + "</p>",
            },
        ],
        primary_action_label: __("Create Landed Cost Voucher"),
        primary_action: function() {
            dialog.hide();
            amf_create_landed_cost_voucher_from_transport_invoice(frm);
        },
        secondary_action_label: __("Close"),
    });

    dialog.show();
}

function amf_create_landed_cost_voucher_from_transport_invoice(frm) {
    frappe.model.with_doctype("Landed Cost Voucher", function() {
        var lcv = frappe.model.get_new_doc("Landed Cost Voucher");
        var net_transport_cost = flt(frm.doc.base_net_total || frm.doc.net_total || 0);

        lcv.company = frm.doc.company;
        lcv.distribute_charges_based_on = "Amount";

        if (net_transport_cost) {
            var tax = frappe.model.add_child(lcv, "taxes");
            tax.description = __("Transport cost from Purchase Invoice {0}", [frm.doc.name]);
            tax.amount = net_transport_cost;
            lcv.total_taxes_and_charges = net_transport_cost;
        }

        frappe.set_route("Form", "Landed Cost Voucher", lcv.name);
    });
}
