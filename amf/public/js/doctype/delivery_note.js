/*
Delivery Note Script
--------------------

What this does:
* Handles click on "Add shipping and taxes" button:
    * Empties taxes table
    * Replaces by two items: first item shipping, second item VAT (applies to previous total)
*/

frappe.ui.form.on("Delivery Note", {

    before_save: async function (frm) {
        console.log("before_save start");
        /*
         * 1. Set the expense account for all items.
         * 2. Check which items require a serial number.
         * 3. Fetch the serial numbers for the flagged items.
         */

        // Step 1: Set the expense account for all items.
        /*
        frm.doc.items.forEach(item => {
            item.expense_account = "4900 - Stock variation - AMF21";
        });
        console.log("Set expense account of all items.");*/

        /*
        getItemWithSerialNo(frm).then(sn_required_indices => {
            //console.log(sn_required_indices);
            if (sn_required_indices.length && !frm.doc.is_return) {
                console.log('Getting serial numbers for indices:', sn_required_indices);
                get_serial_numbers(frm, sn_required_indices);
            }
        });
        */

        try {
            let sn_required_indices = await getItemWithSerialNo(frm);

            if (sn_required_indices.length && !frm.doc.is_return) {
                console.log('Getting serial numbers for indices:', sn_required_indices);
                await get_serial_numbers(frm, sn_required_indices);
            }

        } catch (error) {
            console.error("An error occurred:", error);
        }
        await new Promise(resolve => setTimeout(resolve, 1000));
        console.log("before_save end");
    },

    after_save: async function (frm) {},

    onload: function (frm) {},

    refresh: function (frm) {
        console.log("refresh start");
        
        frm.add_custom_button(__('<i class="fa fa-file-text"></i>&nbsp;&nbsp;•&nbsp;&nbsp;Export DHL File'), function () {
            frappe.call({
                method: "amf.amf.utils.delivery_note_api.generate_dhl",
                args: { "delivery_note_id": frm.doc.name },
                callback: function(r) {
                    if (r.message.status === "success") {
                        // Create a Blob and trigger a download
                        var blob = new Blob([r.message.data], { type: 'text/plain' });
                        var link = document.createElement('a');
                        link.href = window.URL.createObjectURL(blob);
                        link.download = 'dhl_file_' + frm.doc.name + '.txt';
                        document.body.appendChild(link);
                        link.click();
                        document.body.removeChild(link);
                        
                        // Prepare the description of items for the popup
                        var descriptions = [];
                        descriptions.push("Microfluidics equipment for laboratory use including: ");
                        $.each(frm.doc.items || [], function(i, item) {
                            descriptions.push(item.description);
                        });
                        descriptions.push(" for non-medical use.");
                        // Show a popup with the description of items
                        frappe.msgprint({
                            title: 'DHL Summarize >> Contents of Shipment.',
                            indicator: 'green',
                            message: descriptions.join('')
                        });
                    }
                }
            });
        });
        
        frm.add_custom_button(__('<i class="fa fa-print"></i>&nbsp;&nbsp;•&nbsp;&nbsp;Packaging Print'), function () {
            var w = window.open(frappe.urllib.get_full_url("/api/method/frappe.utils.print_format.download_pdf?"
                + "doctype=" + encodeURIComponent("Delivery Note")
                + "&name=" + encodeURIComponent(frm.doc.name)
                + "&format=" + encodeURIComponent("Packaging Branding AMF 2023")
                + "&no_letterhead=" + encodeURIComponent("0")
            ));
            if (!w) {
                frappe.msgprint(__("Please enable pop-ups")); return;
            }
        });

        frm.add = function (cost, costCenter, VATaccountHead, VATrate, VATdescription) {
            frm.clear_table("taxes");

            if (cost > 0) {
                var shipping = frm.add_child("taxes");
                frappe.model.set_value(shipping.doctype, shipping.name, "charge_type", "Actual");
                frappe.model.set_value(shipping.doctype, shipping.name, "cost_center", costCenter);
                frappe.model.set_value(shipping.doctype, shipping.name, "account_head", "3410 - Frais de transport et commissions (ex Paypal) - AMF21");
                frappe.model.set_value(shipping.doctype, shipping.name, "tax_amount", cost);
            }
            var taxes = frm.add_child("taxes");
            if (cost > 0) {
                frappe.model.set_value(taxes.doctype, taxes.name, "charge_type", "On Previous Row Total");
                frappe.model.set_value(taxes.doctype, taxes.name, "row_id", "1");
            } else {
                frappe.model.set_value(taxes.doctype, taxes.name, "charge_type", "On Net Total");
            }
            frappe.model.set_value(taxes.doctype, taxes.name, "cost_center", costCenter);

            frappe.model.set_value(taxes.doctype, taxes.name, "account_head", VATaccountHead);
            setTimeout(function () {
                if (cost > 0) {
                    frappe.model.set_value(shipping.doctype, shipping.name, "description", "Shipping");
                }
                frappe.model.set_value(taxes.doctype, taxes.name, "rate", VATrate);
                frappe.model.set_value(taxes.doctype, taxes.name, "description", VATdescription);
            }, 400);

            frm.refresh_field("taxes");
        };

        if ((frm.doc.__islocal) && (frm.doc.is_return)) {
            // select DN-RET- as naming series
            cur_frm.set_value("naming_series", "DN-RET-");
        }
        console.log("refresh end");
    },

    add_shipping_and_taxes: function (frm) {
        frappe.prompt([{
            'fieldname': 'cost',
            'fieldtype': 'Currency',
            'label': 'Shipping Cost',
            'reqd': 0,
            'default': 0,
        }, {
            'fieldname': 'costCenter',
            'fieldtype': 'Select',
            'options': 'General - AMF21\n' +
                'Automation - AMF21\n' +
                'Patch - AMF21',
            'label': 'Cost Center',
            'reqd': 1,
            'default': 0,
        }, {
            'fieldname': 'vat',
            'fieldtype': 'Select',
            'options':
                'VAT 8.1%\n' +
                'VAT 8.1% - Import of Services\n' +
                'VAT 0%\n' +
                'VAT 0% - Import of Services',
            'label': 'VAT',
            'reqd': 1,
        }],
            function (values) {
                console.log(values);
                var VATaccountHead;
                var VATrate;
                var VATdescription;
                switch (values.vat) {
                    case 'VAT 8.1%':
                        VATaccountHead = '2223 - VAT payable (Sales) - AMF21';
                        VATrate = 8.1;
                        VATdescription = 'VAT 8.1%';
                        break;
                    case 'VAT 8.1% - Import of Services':
                        VATaccountHead = '2226 - VAT payable on import of services - AMF21';
                        VATrate = 8.1;
                        VATdescription = 'VAT 8.1%';
                        break;
                    case 'VAT 0%':
                        VATaccountHead = '2223 - VAT payable (Sales) - AMF21';
                        VATrate = 0;
                        VATdescription = 'VAT 0%';
                        break;
                    case 'VAT 0% - Import of Services':
                        VATaccountHead = '2226 - VAT payable on import of services - AMF21';
                        VATrate = 0;
                        VATdescription = 'VAT 0%';
                        break;
                }
                frm.add(values.cost, values.costCenter, VATaccountHead, VATrate, VATdescription);
            },
            'Shipping Cost Entry',
            'Add',
        );
    },
});

function get_serial_numbers(frm, sn_required_indices) {
    $.each(sn_required_indices, function (_, idx) {
        let item = frm.doc.items[idx];
        console.log('item.item_code:', item.item_code);
        console.log('item.so_detail:', item.so_detail);
        console.log('item.against_sales_order:', item.against_sales_order);
        if (item.so_detail && item.against_sales_order) {
            frappe.call({
                method: 'amf.amf.utils.custom.get_latest_serial_no_new',
                args: {
                    'so_detail': item.so_detail,
                    'sales_order': item.against_sales_order,
                    'item_code': item.item_code
                },
                callback: function (r) {
                    if (r.message) {
                        console.log(r.message[item.so_detail]);
                        let qty = frappe.model.get_value(item.doctype, item.name, 'qty');
                        console.log("qty:", qty);
                        // Split the serial numbers by newline and slice the array based on 'qty'
                        let serial_nos = r.message[item.so_detail].split('\n').slice(0, qty);
                        console.log(serial_nos);
                        // Join back the sliced serial numbers into a string separated by newline
                        let serial_nos_str = serial_nos.join('\n');
                        console.log(serial_nos_str);
                        frappe.model.set_value(item.doctype, item.name, 'serial_no', serial_nos_str);
                    }
                },
                error: function (r) {
                    // Handle the error scenario
                    console.error("An error occurred while fetching serial numbers: ", r);
                }
            });
        }
    });
}


function getItemWithSerialNo(frm) {
    let sn_required_indices = [];
    let promises = [];  // Array to store all our promises

    for (let i = 0; i < frm.doc.items.length; i++) {
        let item = frm.doc.items[i];

        // Wrap the asynchronous call in a promise
        let promise = new Promise((resolve, reject) => {
            frappe.db.get_value('Item', { 'name': item.item_code }, 'has_serial_no', function (r) {
                if (r.has_serial_no == 1) {
                    sn_required_indices.push(i);
                    //console.log('Item index with serial number:', i);
                }
                resolve();  // Mark this promise as resolved
            });
        });

        promises.push(promise);
    }

    // Wait for all promises to resolve, then return the result
    return Promise.all(promises).then(() => {
        return sn_required_indices;
    });
}

frappe.ui.form.on('Delivery Note Item', {
    // Trigger for item_code field
    item_code: function (frm, cdt, cdn) {
        fill_empty_fields(frm, cdt, cdn);
    },

    // Trigger for qty field
    qty: function (frm, cdt, cdn) {
        fill_empty_fields(frm, cdt, cdn);
    }
});

function fill_empty_fields(frm, cdt, cdn) {
    console.log("Field changed >>>");

    var current_item = locals[cdt][cdn]; // Get the current item

    var parent_doc = locals[frm.doc.doctype][frm.doc.name]; // Get the parent document
    var items_table = parent_doc.items; // Get the entire items child table

    // If the current item has null fields, find values from other rows with the same item_code
    if ((!current_item.so_detail || !current_item.against_sales_order) && current_item.item_code) {
        $.each(items_table, function (index, row) {
            if (row.item_code === current_item.item_code) {  // Check for the same item_code
                if (row.so_detail && !current_item.so_detail) {
                    console.log("Setting so_detail:", row.so_detail, " for current item:", current_item.name);
                    frappe.model.set_value(cdt, cdn, "so_detail", row.so_detail);
                }
            }    
            if (row.against_sales_order && !current_item.against_sales_order) {
                    console.log("Setting against_sales_order:", row.against_sales_order, " for current item:", current_item.name);
                    frappe.model.set_value(cdt, cdn, "against_sales_order", row.against_sales_order);
            }
        });
    }
}