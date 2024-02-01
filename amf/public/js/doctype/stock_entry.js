/*
Stock Entry Script
------------------

- Set all item's Expense Account to 4900.

*/
frappe.ui.form.on("Stock Entry", {
    refresh: function (frm) {
        if (frm.doc.docstatus === 1 && frm.doc.stock_entry_type === "Manufacture") {
            frm.add_custom_button(__('<i class="fa fa-print"></i>&nbsp;&nbsp;•&nbsp;&nbsp;QR Code'), function () {
                const print_format = "Serial No Item";
                const label_format = "Labels 35x55mm";

                var w = window.open(
                    frappe.urllib.get_full_url(
                        "/api/method/amf.amf.utils.labels.download_label_for_doc"
                        + "?doctype=" + encodeURIComponent(frm.doc.doctype)
                        + "&docname=" + encodeURIComponent(frm.doc.name)
                        + "&print_format=" + encodeURIComponent(print_format)
                        + "&label_reference=" + encodeURIComponent(label_format)
                    ),
                    "_blank"
                );
                if (!w) {
                    frappe.msgprint(__("Please enable pop-ups")); return;
                }
            });
        }
        if (frm.doc.docstatus === 1) {
            frm.add_custom_button(__('<i class="fa fa-print"></i>&nbsp;&nbsp;•&nbsp;&nbsp;Sticker'), function () {
                //get_label("Stock Entry", frm.doc.name, "Label QR Code", "Labels 9x46mm");
                var w = window.open(frappe.urllib.get_full_url("/api/method/amf.amf.utils.labels.download_label_for_doc"
                    + "?doctype=" + encodeURIComponent(frm.doc.doctype)
                    + "&docname=" + encodeURIComponent(frm.doc.name)
                    + "&print_format=" + encodeURIComponent("Stock Entry Sticker")
                    + "&label_reference=" + encodeURIComponent("Labels 45x55mm")
                ));
                if (!w) {
                    frappe.msgprint(__("Please enable pop-ups")); return;
                }
            });
        }
    },

    before_save: function (frm) {
        // Fill expense account on all items
        for (var item of frm.doc.items) {
            item.expense_account = "4900 - Stock variation - AMF21";
            if (frm.doc.purpose == 'Material Transfer for Manufacture' || frm.doc.purpose == 'Manufacture') {
                item.cost_center = "Automation - AMF21";
            }
        }
        console.log("Set expense account of all items.");
    },


    before_submit: async function (frm) {
        if (frm.doc.purpose === 'Manufacture') {
            let d = frm.doc.items[frm.doc.items.length - 1];
            let item = await frappe.db.get_value('Item', d.item_code, 'has_batch_no');

            if (item.message.has_batch_no) {
                let batch_id = d.item_code + " • " + frm.doc.posting_date + " • " + "AMF" + " • " + frm.doc.fg_completed_qty;
                let existingBatch = await frappe.db.get_value('Batch', { 'batch_id': batch_id }, 'name');

                if (existingBatch && existingBatch.message !== undefined) {
                    // Handling duplicate - generating a unique batch ID
                    // Example: appending a timestamp or a counter
                    let uniqueSuffix = new Date().getTime(); // Using timestamp for uniqueness
                    batch_id += " • " + uniqueSuffix;
                }

                // Create new batch with either the original or updated unique batch ID
                let new_batch = await frappe.call({
                    method: "frappe.client.insert",
                    args: {
                        doc: {
                            doctype: "Batch",
                            item: d.item_code,
                            batch_id: batch_id,
                        }
                    }
                });
                d.batch_no = new_batch.message.name;
            }
        }
    },

    on_submit: function (frm) {
        if (frm.doc.docstatus === 1 && frm.doc.stock_entry_type === "Manufacture") {
            frappe.call({
                method: "amf.amf.utils.delivery_note_api.generate_serial_number_qr_codes",
                args: {
                    stock_entry: frm.doc.name
                },
                callback: function (response) {
                    const qr_codes = response.message;
                    if (qr_codes.length > 0) {
                        let content = '';
                        qr_codes.forEach(qr_code => {
                            content += `
                                        <div>
                                            <span>S/N: ${qr_code.serial_number}</span>
                                            <img src="data:image/png;base64,${qr_code.qr_code}" />
                                        </div>
                                        <span style="font-size: 1px; font-style: italic; margin: 1px;"></span>
                                        `;
                        });
                        const qr_code_dialog = new frappe.ui.Dialog({
                            title: 'Serial Number QR Code',
                            fields: [{ fieldtype: 'HTML', fieldname: 'qr_code_display' }],
                        });

                        $(qr_code_dialog.fields_dict.qr_code_display.wrapper).html(content);
                        qr_code_dialog.show();
                    } else {
                        //frappe.msgprint("No QR codes generated.");
                    }
                }
            });
        }
    },
});