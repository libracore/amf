frappe.ui.form.on('Item', {
    refresh: function (frm) {
        addCustomButtons(frm);
        manageItemDefaults(frm);
    },

    before_save: function (frm) {
        //manageItemDefaults(frm);
    },

    onload: function (frm) {
        if (!frm.is_new() && (frm.doc.default_bom != frm.doc.item_default_bom)) { loadDefaultBOM(frm); } // Load default BOM if item already exists
    },
});

function addCustomButtons(frm) {
    // Projected Stock button
    frm.add_custom_button("Projected Stock", function () {
        frappe.route_options = {
            item_code: frm.doc.name,
            warehouse: frm.doc.item_defaults?.[0]?.default_warehouse,
        };
        frappe.set_route("query-report", "Projected Stock");
    });

    // Generate QR Code PDF menu item
    frm.page.add_menu_item('Generate QR Code PDF', function () {
        generateQRCodePDF();
    });

    // QR Code for Item menu item
    frm.page.add_menu_item('<i class="fa fa-print"></i>&nbsp;&nbsp;•&nbsp;&nbsp;QR Code For Item', function () {
        print_custom_format(frm);
    });

    // Create Job Card menu item
    frm.add_custom_button(__("Create Job Card"), function () {
        show_job_card_dialog(frm);
    });
}

function manageItemDefaults(frm) {
    console.log("manageItemDefaults(frm)");

    // Check if item_defaults is not undefined
    if (frm.doc.item_defaults !== undefined) {
        console.log("1");
        // Check if the specific company exists in item_defaults
        var companyExists = frm.doc.item_defaults.some(row => row.company === "Advanced Microfluidics SA");
    
        // If the company doesn't exist, add it
        if (!companyExists) {
            console.log("2");
            createItemDefaultRow(frm);
        }
    } else {
        console.log("3");
        // If item_defaults is undefined, create it and add a new row
        frm.doc.item_defaults = [];
        createItemDefaultRow(frm);  // Call the function to create a new item_defaults row
        console.log("X");
    }
}

function createItemDefaultRow(frm) {
    console.log("5");
    // Add a new row to item_defaults
    var child = frm.add_child("item_defaults");
    frappe.model.set_value(child.doctype, child.name, "company", "Advanced Microfluidics SA");

    // Determine the warehouse based on item_group
    let warehouse = "Main Stock - AMF21";
    if (["Assemblies", "Sub Assemblies", "Syringe", "Valve Head", "Products"].includes(frm.doc.item_group)) {
        warehouse = "Assemblies - AMF21";
    }

    // Set default_warehouse
    frappe.model.set_value(child.doctype, child.name, "default_warehouse", warehouse);
    frm.refresh_field("item_defaults");
}

function loadDefaultBOM(frm) {
    frm.clear_table("bom_table");
    frm.refresh_field("bom_table");
    frappe.model.set_value(frm.doc.doctype, frm.doc.name, 'item_default_bom', frm.doc.default_bom);

    frappe.call({
        method: "frappe.client.get",
        args: {
            doctype: "BOM",
            filters: { 'item': frm.doc.item_code, 'is_default': 1 }
        },
        callback: function (response) {
            var bom = response.message;
            if (bom) {
                bom.items.forEach(function (bom_item) {
                    var child = frm.add_child("bom_table");
                    ["item_code", "item_name", "qty", "uom", "rate"].forEach(field => {
                        frappe.model.set_value(child.doctype, child.name, field, bom_item[field]);
                    });
                });
                frm.refresh_field("bom_table");
                frm.save();
            }
        }
    });
}

function generateQRCodePDF() {
    frappe.call({
        method: 'amf.amf.utils.qr_code_generator.generate_pdf_with_qr_codes',
        callback: function (r) {
            if (!r.exc) {
                // Download the PDF file
                const link = document.createElement('a');
                link.href = `data:application/pdf;base64,${r.message}`;
                link.download = 'qrcodes.pdf';
                link.click();
            }
        }
    });
}

function print_custom_format(frm) {
    const print_format = "Item QR Code"
    const label_format = "Labels 35x55mm"

    window.open(
        frappe.urllib.get_full_url(
            "/api/method/amf.amf.utils.labels.download_label_for_doc"
            + "?doctype=" + encodeURIComponent(frm.doc.doctype)
            + "&docname=" + encodeURIComponent(frm.doc.name)
            + "&print_format=" + encodeURIComponent(print_format)
            + "&label_reference" + encodeURIComponent(label_format)
        ),
        "_blank"
    );
}

function show_job_card_dialog(frm) {
    const d = new frappe.ui.Dialog({
        title: __("Create Job Card for {0}", [frm.doc.item_name]),
        fields: [
            {
                fieldtype: "Link",
                fieldname: "work_order",
                label: __("Work Order"),
                options: "Work Order",
                default: "OF-00072",
                reqd: 1,
            },
            {
                'label': __(''),
                'fieldname': 'work_order_description',
                'fieldtype': 'HTML',
                'options': '<div style="font-size: 11px; color: #888; margin-top: -10px; margin-bottom: -5px;">If your Job Card is not linked to any Work Order, use by default: OF-00072.</div>'
            },
            {
                fieldtype: "Link",
                fieldname: "workstation",
                label: __("Workstation"),
                options: "Workstation",
                reqd: 1,
            },
            {
                fieldtype: "Link",
                fieldname: "operation",
                label: __("Operation"),
                options: "Operation",
                reqd: 1,
            },
            {
                fieldtype: "Float",
                fieldname: "for_quantity",
                label: __("Quantity"),
                reqd: 1,
            },
            {
                fieldtype: "Small Text",
                fieldname: "description_operation",
                label: __("Description"),
                reqd: 0,
            },
        ],
        primary_action_label: __("Create"),
        primary_action: function () {
            const args = d.get_values();
            if (args) {
                create_job_card(frm, args);
                d.hide();
            }
        },
    });
    d.show();
}

function create_job_card(frm, args) {
    frappe.call({
        method: "frappe.client.insert",
        args: {
            doc: {
                doctype: "Job Card",
                work_order: args.work_order,
                product_item: frm.doc.name,
                workstation: args.workstation,
                operation: args.operation,
                for_quantity: args.for_quantity,
                description_operation: args.description_operation,
            },
        },
        callback: function (r) {
            if (!r.exc) {
                frappe.show_alert(__("Job Card {0} created", [r.message.name]));
                frappe.set_route("Form", "Job Card", r.message.name);
            }
        },
    });
}