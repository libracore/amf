// Accessory review for Quotation and Sales Order.
// ERPNext/Frappe v12 compatible client script.

(function () {
    var ACCESSORY_REQUIRED_PREFIXES = [
        "41", "42", "43", "44", "45", "46", "47", "48", "49",
        "4A", "4B", "4C", "4D"
    ];

    var ACCESSORY_ITEM_CODES = [
        "C100", "C101", "C102", "C103", "C104", "C105",
        "C106", "C107", "C108", "C109", "C110",
        "C201", "C202", "C203", "C204"
    ];

    function normalized_item_code(item_code) {
        return (item_code || "").toString().toUpperCase();
    }

    function item_requires_accessory_review(item_code) {
        var code = normalized_item_code(item_code);

        for (var i = 0; i < ACCESSORY_REQUIRED_PREFIXES.length; i++) {
            if (code.indexOf(ACCESSORY_REQUIRED_PREFIXES[i]) === 0) {
                return true;
            }
        }

        return false;
    }

    function is_accessory_item(item_code) {
        return ACCESSORY_ITEM_CODES.indexOf(normalized_item_code(item_code)) !== -1;
    }

    function get_matching_product_rows(frm) {
        var rows = [];

        $.each(frm.doc.items || [], function (idx, row) {
            if (row.item_code && item_requires_accessory_review(row.item_code)) {
                rows.push(row);
            }
        });

        return rows;
    }

    function get_matching_product_signature(frm) {
        var parts = [];

        $.each(get_matching_product_rows(frm), function (idx, row) {
            parts.push([
                row.idx || idx + 1,
                normalized_item_code(row.item_code),
                flt(row.qty)
            ].join(":"));
        });

        return parts.join("|");
    }

    function has_matching_product_rows(frm) {
        return get_matching_product_rows(frm).length > 0;
    }

    function current_products_were_reviewed(frm) {
        var signature = get_matching_product_signature(frm);
        return Boolean(
            signature &&
            frm._accessory_review_done &&
            frm._accessory_review_signature === signature
        );
    }

    function mark_accessory_review_done(frm) {
        frm._accessory_review_done = true;
        frm._accessory_review_signature = get_matching_product_signature(frm);
    }

    function reset_accessory_review(frm) {
        frm._accessory_review_done = false;
        frm._accessory_review_signature = null;
    }

    function get_existing_accessory_map(frm) {
        var existing = {};

        $.each(frm.doc.items || [], function (idx, row) {
            if (row.item_code && is_accessory_item(row.item_code)) {
                existing[normalized_item_code(row.item_code)] = row;
            }
        });

        return existing;
    }

    function make_default_item_name_map() {
        var item_names_by_code = {};

        $.each(ACCESSORY_ITEM_CODES, function (idx, item_code) {
            item_names_by_code[item_code] = item_code;
        });

        return item_names_by_code;
    }

    function fetch_accessory_item_names(frm) {
        if (frm._accessory_item_name_map) {
            return Promise.resolve(frm._accessory_item_name_map);
        }

        return new Promise(function (resolve) {
            var item_names_by_code = make_default_item_name_map();
            var request = frappe.call({
                method: "frappe.client.get_list",
                args: {
                    doctype: "Item",
                    fields: ["name", "item_code", "item_name"],
                    filters: [["Item", "item_code", "in", ACCESSORY_ITEM_CODES]],
                    limit_page_length: ACCESSORY_ITEM_CODES.length
                },
                callback: function (response) {
                    $.each(response.message || [], function (idx, item) {
                        var item_code = normalized_item_code(item.item_code || item.name);
                        item_names_by_code[item_code] = item.item_name || item.name;
                    });

                    frm._accessory_item_name_map = item_names_by_code;
                    resolve(item_names_by_code);
                }
            });

            if (request && request.fail) {
                request.fail(function () {
                    frm._accessory_item_name_map = item_names_by_code;
                    resolve(item_names_by_code);
                });
            }
        });
    }

    function get_price_list_context_key(frm) {
        return [
            frm.doc.selling_price_list || "",
            frm.doc.customer || frm.doc.party_name || "",
            frm.doc.quotation_to || "",
            frm.doc.customer_group || "",
            frm.doc.territory || "",
            frm.doc.currency || "",
            frm.doc.price_list_currency || "",
            flt(frm.doc.conversion_rate),
            flt(frm.doc.plc_conversion_rate),
            frm.doc.company || "",
            frm.doc.transaction_date || frm.doc.posting_date || ""
        ].join("|");
    }

    function get_child_item_doctype(frm) {
        return frm.doc.doctype + " Item";
    }

    function make_accessory_price_list_args(frm) {
        var child_doctype = get_child_item_doctype(frm);
        var items = [];

        $.each(ACCESSORY_ITEM_CODES, function (idx, item_code) {
            items.push({
                doctype: child_doctype,
                name: "accessory-default-" + idx,
                child_docname: "accessory-default-" + idx,
                item_code: item_code,
                qty: 1,
                conversion_factor: 1,
                parenttype: frm.doc.doctype,
                parent: frm.doc.name
            });
        });

        return {
            items: items,
            customer: frm.doc.customer || frm.doc.party_name,
            quotation_to: frm.doc.quotation_to,
            customer_group: frm.doc.customer_group,
            territory: frm.doc.territory,
            currency: frm.doc.currency,
            conversion_rate: frm.doc.conversion_rate,
            price_list: frm.doc.selling_price_list,
            selling_price_list: frm.doc.selling_price_list,
            price_list_currency: frm.doc.price_list_currency,
            plc_conversion_rate: frm.doc.plc_conversion_rate,
            company: frm.doc.company,
            transaction_date: frm.doc.transaction_date || frm.doc.posting_date,
            campaign: frm.doc.campaign,
            sales_partner: frm.doc.sales_partner,
            ignore_pricing_rule: frm.doc.ignore_pricing_rule,
            doctype: frm.doc.doctype,
            name: frm.doc.name,
            is_return: cint(frm.doc.is_return),
            update_stock: 0
        };
    }

    function fetch_accessory_price_list_rates(frm) {
        var price_list = frm.doc.selling_price_list;
        var context_key = get_price_list_context_key(frm);

        if (!price_list) {
            return Promise.resolve({});
        }

        if (
            frm._accessory_price_rate_cache &&
            frm._accessory_price_rate_cache.key === context_key
        ) {
            return Promise.resolve(frm._accessory_price_rate_cache.rates);
        }

        return new Promise(function (resolve) {
            var rates_by_code = {};
            var request = frappe.call({
                method: "erpnext.stock.get_item_details.apply_price_list",
                args: {
                    args: make_accessory_price_list_args(frm)
                },
                callback: function (response) {
                    response = response || {};

                    if (!response.exc && response.message && response.message.children) {
                        $.each(response.message.children, function (idx, child) {
                            var item_code = ACCESSORY_ITEM_CODES[idx];
                            rates_by_code[item_code] = flt(child.price_list_rate || child.rate);
                        });
                    }

                    frm._accessory_price_rate_cache = {
                        key: context_key,
                        rates: rates_by_code
                    };
                    resolve(rates_by_code);
                }
            });

            if (request && request.fail) {
                request.fail(function () {
                    resolve(rates_by_code);
                });
            }
        });
    }

    function make_accessory_dialog_data(item_names_by_code, rates_by_code) {
        var rows = [];

        $.each(ACCESSORY_ITEM_CODES, function (idx, item_code) {
            rows.push({
                idx: idx + 1,
                item_code: item_code,
                item_name: item_names_by_code[item_code] || item_code,
                qty: 0,
                rate: flt(rates_by_code[item_code])
            });
        });

        return rows;
    }

    function get_accessories_with_quantity(dialog) {
        var rows = [];
        var values = dialog.get_values(true) || {};
        var accessories = values.accessories || [];

        $.each(accessories, function (idx, row) {
            if (flt(row.qty) !== 0) {
                rows.push(row);
            }
        });

        return rows;
    }

    function build_matching_products_html(frm) {
        var products = get_matching_product_rows(frm);
        var html = [
            "<p>",
            __("The selected product may require accessories. Enter a quantity for each accessory to add to this document. Accessories with quantity 0 will not be added. You may skip this step only after confirming."),
            "</p>"
        ];

        if (products.length) {
            html.push("<p><b>" + __("Matching product rows") + "</b></p>");
            html.push("<ul>");
            $.each(products, function (idx, row) {
                html.push(
                    "<li>" +
                    frappe.utils.escape_html(row.item_code || "") +
                    " (" + __("Qty") + ": " + flt(row.qty) + ")" +
                    "</li>"
                );
            });
            html.push("</ul>");
        }

        return html.join("");
    }

    function set_child_value_if_exists(row, fieldname, value) {
        if (frappe.meta.has_field(row.doctype, fieldname)) {
            return frappe.model.set_value(row.doctype, row.name, fieldname, value);
        }

        return Promise.resolve();
    }

    function make_add_accessory_task(row, accessory, item_code) {
        return function () {
            var qty = flt(accessory.qty) || 1;
            var rate = flt(accessory.rate);
            var item_name = accessory.item_name || item_code;

            return frappe.run_serially([
                function () {
                    return frappe.model.set_value(row.doctype, row.name, "item_code", item_code);
                },
                function () {
                    return frappe.after_ajax();
                },
                function () {
                    return set_child_value_if_exists(row, "qty", qty);
                },
                function () {
                    return set_child_value_if_exists(row, "price_list_rate", rate);
                },
                function () {
                    return set_child_value_if_exists(row, "rate", rate);
                },
                function () {
                    if (!row.item_name) {
                        return set_child_value_if_exists(row, "item_name", item_name);
                    }
                },
                function () {
                    if (!row.description) {
                        return set_child_value_if_exists(row, "description", item_name);
                    }
                },
                function () {
                    return frappe.after_ajax();
                }
            ]);
        };
    }

    function add_accessories_with_quantity(frm, accessories_to_add) {
        var existing = get_existing_accessory_map(frm);
        var added = [];
        var skipped = [];
        var tasks = [];

        $.each(accessories_to_add, function (idx, accessory) {
            var item_code = normalized_item_code(accessory.item_code);

            if (!item_code) {
                return;
            }

            if (existing[item_code]) {
                skipped.push(item_code);
                return;
            }

            var row = frm.add_child("items");
            existing[item_code] = row;
            added.push(item_code);
            tasks.push(make_add_accessory_task(row, accessory, item_code));
        });

        return frappe.run_serially(tasks).then(function () {
            frm.refresh_field("items");

            if (added.length) {
                frappe.show_alert({
                    message: __("Accessories added: {0}", [added.join(", ")]),
                    indicator: "green"
                });
            }

            if (skipped.length) {
                frappe.msgprint({
                    title: __("Accessories already present"),
                    indicator: "orange",
                    message: __("These accessory rows already exist and were not changed: {0}", [skipped.join(", ")])
                });
            }
        });
    }

    function show_accessory_review_dialog(frm) {
        if (!has_matching_product_rows(frm)) {
            return Promise.resolve();
        }

        if (frm._accessory_review_dialog_open) {
            return frm._accessory_review_dialog_promise || Promise.resolve();
        }

        frm._accessory_review_dialog_open = true;
        frm._accessory_review_dialog_promise = Promise.all([
            fetch_accessory_item_names(frm),
            fetch_accessory_price_list_rates(frm)
        ]).then(function (defaults) {
            return new Promise(function (resolve, reject) {
                var dialog_data = make_accessory_dialog_data(defaults[0], defaults[1]);
                var dialog = new frappe.ui.Dialog({
                    title: __("Accessory Review"),
                    size: "large",
                    static: true,
                    fields: [
                        {
                            fieldtype: "HTML",
                            fieldname: "instructions",
                            options: build_matching_products_html(frm)
                        },
                        {
                            fieldtype: "Table",
                            fieldname: "accessories",
                            label: __("Accessories"),
                            cannot_add_rows: true,
                            in_place_edit: true,
                            data: dialog_data,
                            get_data: function () {
                                return dialog_data;
                            },
                            fields: [
                                {
                                    fieldtype: "Data",
                                    fieldname: "item_code",
                                    label: __("Accessory Item Code"),
                                    read_only: 1,
                                    in_list_view: 1
                                },
                                {
                                    fieldtype: "Data",
                                    fieldname: "item_name",
                                    label: __("Item Name"),
                                    read_only: 1,
                                    in_list_view: 1
                                },
                                {
                                    fieldtype: "Float",
                                    fieldname: "qty",
                                    label: __("Qty"),
                                    in_list_view: 1
                                },
                                {
                                    fieldtype: "Currency",
                                    fieldname: "rate",
                                    label: __("Rate"),
                                    in_list_view: 1
                                }
                            ]
                        }
                    ],
                    primary_action_label: __("Add Accessories"),
                    primary_action: function () {
                        var accessories_to_add = get_accessories_with_quantity(dialog);

                        if (!accessories_to_add.length) {
                            frappe.msgprint(__("Please enter a non-zero quantity for at least one accessory, or use Skip Accessories and confirm."));
                            return;
                        }

                        dialog.get_primary_btn().prop("disabled", true);
                        add_accessories_with_quantity(frm, accessories_to_add).then(function () {
                            mark_accessory_review_done(frm);
                            dialog.hide();
                            resolve();
                        }).then(null, function () {
                            dialog.get_primary_btn().prop("disabled", false);
                            frappe.msgprint(__("Could not add accessories. Please try again or contact your system administrator."));
                            reject();
                        });
                    }
                });

                dialog.get_close_btn()
                    .html(__("Skip Accessories"))
                    .show()
                    .off("click.accessory_review")
                    .on("click.accessory_review", function (event) {
                        event.preventDefault();
                        event.stopImmediatePropagation();

                        frappe.confirm(
                            __("Are you sure you want to skip accessories for the selected product?"),
                            function () {
                                mark_accessory_review_done(frm);
                                dialog.hide();
                                resolve();
                            }
                        );

                        return false;
                    });

                dialog.$wrapper.on("hidden.bs.modal", function () {
                    frm._accessory_review_dialog_open = false;
                    frm._accessory_review_dialog_promise = null;
                });

                dialog.show();
            });
        });

        return frm._accessory_review_dialog_promise;
    }

    function validate_accessory_review(frm) {
        if (!has_matching_product_rows(frm)) {
            mark_accessory_review_done(frm);
            return Promise.resolve();
        }

        if (current_products_were_reviewed(frm)) {
            return Promise.resolve();
        }

        return show_accessory_review_dialog(frm);
    }

    function handle_child_item_code_change(frm, cdt, cdn) {
        var row = locals[cdt] && locals[cdt][cdn];

        if (!row || !row.item_code) {
            reset_accessory_review(frm);
            return;
        }

        if (item_requires_accessory_review(row.item_code)) {
            reset_accessory_review(frm);
            return;
        }

        if (!has_matching_product_rows(frm)) {
            reset_accessory_review(frm);
        }
    }

    function handle_child_qty_change(frm, cdt, cdn) {
        var row = locals[cdt] && locals[cdt][cdn];

        if (row && item_requires_accessory_review(row.item_code)) {
            reset_accessory_review(frm);
        }
    }

    function register_parent_doctype(doctype) {
        frappe.ui.form.on(doctype, {
            refresh: function (frm) {
                if (!has_matching_product_rows(frm)) {
                    reset_accessory_review(frm);
                }
            },
            validate: function (frm) {
                return validate_accessory_review(frm);
            },
            before_submit: function (frm) {
                return validate_accessory_review(frm);
            }
        });
    }

    function register_child_doctype(child_doctype) {
        frappe.ui.form.on(child_doctype, {
            item_code: function (frm, cdt, cdn) {
                handle_child_item_code_change(frm, cdt, cdn);
            },
            qty: function (frm, cdt, cdn) {
                handle_child_qty_change(frm, cdt, cdn);
            }
        });
    }

    window.amf_accessory_review = {
        ACCESSORY_REQUIRED_PREFIXES: ACCESSORY_REQUIRED_PREFIXES,
        ACCESSORY_ITEM_CODES: ACCESSORY_ITEM_CODES,
        item_requires_accessory_review: item_requires_accessory_review,
        show_accessory_review_dialog: show_accessory_review_dialog,
        validate_accessory_review: validate_accessory_review
    };

    register_parent_doctype("Quotation");
    register_parent_doctype("Sales Order");
    register_child_doctype("Quotation Item");
    register_child_doctype("Sales Order Item");
}());
