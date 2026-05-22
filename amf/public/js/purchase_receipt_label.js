frappe.ui.form.on("Purchase Receipt", {
    refresh: function(frm) {
        amf_add_raw_material_sticker_button(frm);
    },
});

function amf_add_raw_material_sticker_button(frm) {
    if (frm.doc.__islocal || frm.doc.docstatus !== 1) {
        return;
    }

    var request_key = [frm.doc.name, frm.doc.modified].join(":");
    frm._amf_raw_material_sticker_request_key = request_key;

    frappe.call({
        method: "amf.amf.utils.purchase_receipt.has_raw_material_items",
        args: {
            purchase_receipt: frm.doc.name,
        },
        callback: function(r) {
            if (frm._amf_raw_material_sticker_request_key !== request_key) {
                return;
            }

            if (!r.message || !r.message.has_items) {
                return;
            }

            frm.add_custom_button(__("Raw Material Sticker"), function() {
                amf_open_raw_material_stickers_pdf(frm);
            }, __("Print"));
        },
    });
}

function amf_open_raw_material_stickers_pdf(frm) {
    var url = frappe.urllib.get_full_url(
        "/api/method/amf.amf.utils.purchase_receipt.download_raw_material_stickers" +
        "?purchase_receipt=" + encodeURIComponent(frm.doc.name)
    );
    var pdf_window = window.open(url, "_blank");

    if (!pdf_window) {
        frappe.msgprint(__("Please enable pop-ups to open the sticker PDF."));
    }
}
