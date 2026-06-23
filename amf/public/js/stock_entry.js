frappe.ui.form.on("Stock Entry", {
    refresh: function(frm) {
        if (can_review_amf_raw_material_usage(frm)) {
            frm.add_custom_button(__("Add Scrap"), function() {
                show_amf_raw_material_usage_dialog(frm, {
                    force: true,
                    save_after_apply: true,
                    save_action: "Save",
                });
            }, __("Manufacture"));
        }

        if (frm.doc.docstatus === 1 && frm.doc.purpose === "Manufacture") {
            frm.add_custom_button(__("Correct Manufacture Qty"), function() {
                show_manufacture_qty_correction_dialog(frm);
            }, __("Repair"));
        }
    },
    before_save: function(frm) {
        return validate_amf_raw_material_usage_review(frm, {
            save_after_apply: true,
            abort_current_save: true,
            save_action: "Save",
        });
    },
    before_submit: function(frm) {
        return validate_amf_raw_material_usage_review(frm);
    },
});

var AMF_USAGE_SCRAP_SOURCE_WAREHOUSE = "Main Stock - AMF21";
var AMF_USAGE_SCRAP_TARGET_WAREHOUSE = "Scrap - AMF21";

function validate_amf_raw_material_usage_review(frm, options) {
    if (!should_show_amf_raw_material_usage_review(frm, options)) {
        return Promise.resolve();
    }

    return show_amf_raw_material_usage_dialog(frm, options);
}

function can_review_amf_raw_material_usage(frm) {
    return frm.doc.docstatus === 0
        && frm.doc.purpose === "Manufacture"
        && frm.doc.work_order
        && get_amf_raw_material_usage_rows(frm).length;
}

function should_show_amf_raw_material_usage_review(frm, options) {
    options = options || {};

    if (
        !can_review_amf_raw_material_usage(frm)
        || frm._amf_raw_material_usage_dialog_open
    ) {
        return false;
    }

    if (options.force) {
        return true;
    }

    var current_signature = get_amf_stock_entry_usage_signature(frm.doc);
    if (frm._amf_raw_material_usage_review_signature === current_signature) {
        return false;
    }

    var review = get_existing_amf_raw_material_usage_review(frm);
    if (review && review.review_signature === current_signature) {
        return false;
    }

    return true;
}

function get_existing_amf_raw_material_usage_review(frm) {
    if (!frm.doc.amf_raw_material_usage_json) {
        return null;
    }

    try {
        return JSON.parse(frm.doc.amf_raw_material_usage_json);
    } catch (error) {
        return null;
    }
}

function show_amf_raw_material_usage_dialog(frm, options) {
    options = options || {};

    var usage_rows = get_amf_raw_material_usage_rows(frm);

    if (!usage_rows.length) {
        if (options.force) {
            frappe.msgprint(__("No raw material rows are available for usage scrap."));
        }
        return Promise.resolve();
    }

    frm._amf_raw_material_usage_dialog_open = true;

    return new Promise(function(resolve, reject) {
        var settled = false;
        var dialog = new frappe.ui.Dialog({
            title: __("Raw Material Usage"),
            size: "large",
            static: true,
            fields: [
                {
                    fieldtype: "Table",
                    fieldname: "items",
                    label: __("Raw Materials"),
                    cannot_add_rows: true,
                    in_place_edit: true,
                    data: usage_rows,
                    get_data: function() {
                        return usage_rows;
                    },
                    fields: [
                        {
                            fieldtype: "Data",
                            fieldname: "item_code",
                            label: __("Item Code"),
                            read_only: 1,
                            in_list_view: 1,
                        },
                        {
                            fieldtype: "Data",
                            fieldname: "item_name",
                            label: __("Item Name"),
                            read_only: 1,
                            in_list_view: 1,
                        },
                        {
                            fieldtype: "Float",
                            fieldname: "planned_qty",
                            label: __("Default Qty"),
                            read_only: 1,
                            in_list_view: 1,
                        },
                        {
                            fieldtype: "Float",
                            fieldname: "actual_qty",
                            label: __("Used Qty"),
                            in_list_view: 1,
                        },
                        {
                            fieldtype: "Data",
                            fieldname: "uom",
                            label: __("UOM"),
                            read_only: 1,
                            in_list_view: 1,
                        },
                    ],
                },
            ],
            primary_action_label: __("Continue"),
            primary_action: function() {
                var reviewed_usage = get_amf_reviewed_usage(frm, dialog, usage_rows);
                if (!reviewed_usage) {
                    return;
                }

                apply_amf_reviewed_usage_to_stock_entry(frm, reviewed_usage);
                if (options.abort_current_save) {
                    frappe.validated = false;
                }
                if (options.save_after_apply) {
                    schedule_amf_raw_material_usage_save(frm, options.save_action || "Save");
                }

                settled = true;
                dialog.hide();
                resolve();
            },
        });

        dialog.get_close_btn()
            .html(__("Cancel"))
            .show()
            .off("click.amf_raw_material_usage")
            .on("click.amf_raw_material_usage", function(event) {
                event.preventDefault();
                event.stopImmediatePropagation();
                settled = true;
                frappe.validated = false;
                dialog.hide();
                reject();
                return false;
            });

        dialog.$wrapper.on("hidden.bs.modal", function() {
            frm._amf_raw_material_usage_dialog_open = false;
            if (!settled) {
                frappe.validated = false;
                reject();
            }
        });

        dialog.show();
    });
}

function get_amf_raw_material_usage_rows(frm) {
    var rows = [];
    var existing_usage_by_row = get_existing_amf_raw_material_usage_by_row(frm);

    (frm.doc.items || []).forEach(function(row) {
        if (!is_amf_raw_material_row(row)) {
            return;
        }

        var planned_qty = flt(row.qty, precision("qty"));
        var existing_usage = existing_usage_by_row[get_amf_stock_entry_row_key(row)]
            || existing_usage_by_row[get_amf_usage_row_fallback_key(row)];
        var actual_qty = planned_qty;
        if (existing_usage) {
            planned_qty = flt(existing_usage.planned_qty, precision("qty"));
            actual_qty = flt(existing_usage.actual_qty, precision("qty"));
        }

        rows.push({
            stock_entry_row_name: row.name,
            stock_entry_idx: row.idx,
            item_code: row.item_code,
            item_name: row.item_name,
            description: row.description,
            planned_qty: planned_qty,
            actual_qty: actual_qty,
            uom: row.uom || row.stock_uom,
            stock_uom: row.stock_uom,
            conversion_factor: flt(row.conversion_factor) || 1,
            expense_account: row.expense_account,
            cost_center: row.cost_center,
            allow_zero_valuation_rate: row.allow_zero_valuation_rate,
            batch_no: row.batch_no,
            stock_entry_source_warehouse: row.s_warehouse,
        });
    });

    return rows;
}

function get_existing_amf_raw_material_usage_by_row(frm) {
    var usage_by_row = {};
    var review = get_existing_amf_raw_material_usage_review(frm);

    if (!review || !review.items) {
        return usage_by_row;
    }

    review.items.forEach(function(row) {
        usage_by_row[get_amf_usage_row_key(row)] = row;
        usage_by_row[get_amf_usage_row_fallback_key(row)] = row;
    });

    return usage_by_row;
}

function is_amf_raw_material_row(row) {
    return row && row.item_code && row.s_warehouse && !row.t_warehouse && !row.amf_dynamic_usage_scrap;
}

function get_amf_reviewed_usage(frm, dialog, original_rows) {
    var grid = dialog.fields_dict.items && dialog.fields_dict.items.grid;
    var dialog_rows = grid ? grid.get_data() : original_rows;
    var usage_items = [];
    var has_changes = false;

    for (var i = 0; i < original_rows.length; i++) {
        var original = original_rows[i];
        var dialog_row = dialog_rows[i] || original;
        var actual_qty = flt(dialog_row.actual_qty, precision("qty"));
        var planned_qty = flt(original.planned_qty, precision("qty"));

        if (actual_qty < 0) {
            frappe.msgprint(__("Used Qty cannot be negative for item {0}.", [original.item_code]));
            return null;
        }

        if (Math.abs(actual_qty - planned_qty) > 0.000001) {
            has_changes = true;
        }

        usage_items.push({
            stock_entry_row_name: original.stock_entry_row_name,
            stock_entry_idx: original.stock_entry_idx,
            item_code: original.item_code,
            item_name: original.item_name,
            description: original.description,
            planned_qty: planned_qty,
            actual_qty: actual_qty,
            manufacture_qty: Math.min(actual_qty, planned_qty),
            scrap_qty: Math.max(actual_qty - planned_qty, 0),
            uom: original.uom,
            stock_uom: original.stock_uom,
            conversion_factor: original.conversion_factor,
            expense_account: original.expense_account,
            cost_center: original.cost_center,
            allow_zero_valuation_rate: original.allow_zero_valuation_rate,
            batch_no: original.batch_no,
            scrap_source_warehouse: AMF_USAGE_SCRAP_SOURCE_WAREHOUSE,
            scrap_target_warehouse: AMF_USAGE_SCRAP_TARGET_WAREHOUSE,
            stock_entry_source_warehouse: original.stock_entry_source_warehouse,
        });
    }

    return {
        source: "stock_entry_before_save",
        work_order: frm.doc.work_order,
        company: frm.doc.company,
        has_changes: has_changes,
        items: usage_items,
    };
}

function apply_amf_reviewed_usage_to_stock_entry(frm, reviewed_usage) {
    var usage_by_row = {};
    reviewed_usage.items.forEach(function(row) {
        usage_by_row[get_amf_usage_row_key(row)] = row;
    });

    var adjusted_items = [];
    var removed_items = [];
    (frm.doc.items || []).forEach(function(row) {
        if (row.amf_dynamic_usage_scrap) {
            removed_items.push(row);
            return;
        }

        var usage = usage_by_row[get_amf_stock_entry_row_key(row)];
        if (usage && is_amf_raw_material_row(row)) {
            var new_qty = flt(usage.manufacture_qty, precision("qty"));
            if (new_qty <= 0) {
                removed_items.push(row);
                return;
            }

            row.qty = new_qty;
            row.transfer_qty = flt(new_qty * (flt(row.conversion_factor) || 1), precision("qty"));
        }

        adjusted_items.push(row);
    });

    adjusted_items.forEach(function(row, index) {
        row.idx = index + 1;
    });

    frm.doc.items = adjusted_items;
    removed_items.forEach(remove_amf_stock_entry_detail_from_locals);

    reviewed_usage.items.forEach(function(usage) {
        if (flt(usage.scrap_qty, precision("qty")) <= 0) {
            return;
        }

        make_amf_dynamic_usage_scrap_row(frm, usage);
    });

    (frm.doc.items || []).forEach(function(row, index) {
        row.idx = index + 1;
    });

    reviewed_usage.review_signature = get_amf_stock_entry_usage_signature(frm.doc);
    frm._amf_raw_material_usage_review_signature = reviewed_usage.review_signature;
    frm.doc.amf_raw_material_usage_json = JSON.stringify(reviewed_usage);
    frm.refresh_field("items");
    frm.dirty();
}

function schedule_amf_raw_material_usage_save(frm, save_action) {
    if (frm._amf_raw_material_usage_save_timeout) {
        clearTimeout(frm._amf_raw_material_usage_save_timeout);
    }

    frm._amf_raw_material_usage_save_timeout = setTimeout(function() {
        frm._amf_raw_material_usage_save_timeout = null;
        frm.save(save_action || "Save");
    }, 0);
}

function remove_amf_stock_entry_detail_from_locals(row) {
    if (row && row.doctype && row.name) {
        frappe.model.clear_doc(row.doctype, row.name);
    }
}

function make_amf_dynamic_usage_scrap_row(frm, usage) {
    var conversion_factor = flt(usage.conversion_factor) || 1;
    var qty = flt(usage.scrap_qty, precision("qty"));
    var row = frappe.model.add_child(frm.doc, "Stock Entry Detail", "items");

    $.extend(row, {
        item_code: usage.item_code,
        item_name: usage.item_name,
        description: usage.description,
        qty: qty,
        transfer_qty: flt(qty * conversion_factor, precision("qty")),
        uom: usage.uom || usage.stock_uom,
        stock_uom: usage.stock_uom,
        conversion_factor: conversion_factor,
        s_warehouse: usage.scrap_source_warehouse || AMF_USAGE_SCRAP_SOURCE_WAREHOUSE,
        t_warehouse: usage.scrap_target_warehouse || AMF_USAGE_SCRAP_TARGET_WAREHOUSE,
        expense_account: usage.expense_account,
        cost_center: usage.cost_center,
        allow_zero_valuation_rate: usage.allow_zero_valuation_rate,
        batch_no: usage.batch_no,
        amf_dynamic_usage_scrap: 1,
    });

    return row;
}

function get_amf_stock_entry_usage_signature(doc) {
    return (doc.items || [])
        .filter(is_amf_raw_material_row)
        .map(function(row) {
            return [
                row.idx || "",
                row.item_code || "",
                row.s_warehouse || "",
                flt(row.qty, precision("qty")),
                flt(row.conversion_factor) || 1,
            ].join(":");
        })
        .join("|");
}

function get_amf_usage_row_key(row) {
    return [row.stock_entry_row_name || "", row.stock_entry_idx || "", row.item_code || ""].join("::");
}

function get_amf_stock_entry_row_key(row) {
    return [row.name || "", row.idx || "", row.item_code || ""].join("::");
}

function get_amf_usage_row_fallback_key(row) {
    return [row.stock_entry_idx || row.idx || "", row.item_code || ""].join("::");
}

function show_manufacture_qty_correction_dialog(frm) {
    const dialog = new frappe.ui.Dialog({
        title: __("Correct Manufacture Qty"),
        fields: [
            {
                fieldname: "stock_entry_name",
                fieldtype: "Link",
                options: "Stock Entry",
                label: __("Stock Entry"),
                default: frm.doc.name,
                reqd: 1,
            },
            {
                fieldname: "new_fg_completed_qty",
                fieldtype: "Float",
                label: __("Correct Qty"),
            },
            {
                fieldname: "dry_run",
                fieldtype: "Check",
                label: __("Preview only"),
                default: 0,
            },
            {
                fieldname: "allow_negative_stock",
                fieldtype: "Check",
                label: __("Allow negative stock while reposting"),
                default: 1,
            },
            {
                fieldname: "update_work_order_qty",
                fieldtype: "Check",
                label: __("Update Work Order qty when safe"),
                default: 1,
            },
            {
                fieldname: "balance_value_difference",
                fieldtype: "Check",
                label: __("Balance incoming/outgoing values"),
                default: 1,
            },
            {
                fieldname: "reason",
                fieldtype: "Small Text",
                label: __("Reason"),
            },
            {
                fieldname: "parameters_preview",
                fieldtype: "HTML",
            },
        ],
        primary_action_label: __("Run"),
        primary_action: function(values) {
            show_manufacture_qty_correction_parameters(dialog, values);

            if (!values.dry_run) {
                frappe.confirm(
                    [
                        get_manufacture_qty_correction_parameters_html(values),
                        "<p>",
                        __("This will update a submitted Stock Entry and repost stock/accounting ledgers. Continue?"),
                        "</p>",
                    ].join(""),
                    function() {
                        run_manufacture_qty_correction(frm, dialog, values);
                    }
                );
                return;
            }

            run_manufacture_qty_correction(frm, dialog, values);
        },
    });

    dialog.show();
}

function show_manufacture_qty_correction_parameters(dialog, values) {
    const preview = dialog.fields_dict.parameters_preview;
    if (preview && preview.$wrapper) {
        preview.$wrapper.html(get_manufacture_qty_correction_parameters_html(values));
    }
}

function get_manufacture_qty_correction_parameters_html(values) {
    const rows = [
        [__("Stock Entry"), values.stock_entry_name || ""],
        [__("Correct Qty"), format_manufacture_qty_correction_qty(values.new_fg_completed_qty)],
        [__("Preview only"), values.dry_run ? __("Yes") : __("No")],
        [__("Allow negative stock"), values.allow_negative_stock ? __("Yes") : __("No")],
        [__("Update Work Order qty"), values.update_work_order_qty ? __("Yes") : __("No")],
        [__("Balance values"), values.balance_value_difference ? __("Yes") : __("No")],
        [__("Reason"), values.reason || ""],
    ];

    return [
        "<table class='table table-bordered table-condensed'>",
        "<tbody>",
        rows.map(function(row) {
            return [
                "<tr>",
                "<th style='width: 40%'>", frappe.utils.escape_html(row[0]), "</th>",
                "<td>", frappe.utils.escape_html(row[1]), "</td>",
                "</tr>",
            ].join("");
        }).join(""),
        "</tbody>",
        "</table>",
    ].join("");
}

function format_manufacture_qty_correction_qty(value) {
    if (value === undefined || value === null || value === "") {
        return __("Current submitted qty");
    }
    return frappe.format(value, {fieldtype: "Float"});
}

function get_manufacture_qty_correction_freeze_message(values) {
    const stock_entry = values.stock_entry_name || "";
    if (values.dry_run) {
        return __("Preparing preview for {0}", [stock_entry]);
    }
    return __("Reposting ledgers for {0}", [stock_entry]);
}

function run_manufacture_qty_correction(frm, dialog, values) {
    dialog.$wrapper.find(".btn-primary").prop("disabled", true);
    show_manufacture_qty_correction_parameters(dialog, values);

    frappe.call({
        method: "amf.amf.utils.stock_entry.correct_submitted_manufacture_qty",
        args: values,
        freeze: true,
        freeze_message: get_manufacture_qty_correction_freeze_message(values),
        callback: function(response) {
            if (!response.exc && response.message) {
                show_manufacture_qty_correction_result(response.message);

                if (!values.dry_run && response.message.status === "updated") {
                    if (values.stock_entry_name === frm.doc.name) {
                        frm.reload_doc();
                    }
                }
            }
        },
        always: function() {
            dialog.$wrapper.find(".btn-primary").prop("disabled", false);
        },
    });
}

function show_manufacture_qty_correction_result(result) {
    const indicator = result.status === "updated"
        ? "green"
        : result.status === "blocked"
            ? "red"
            : "blue";

    const rows = (result.rows || []).slice(0, 12).map(function(row) {
        return [
            "<tr>",
            "<td>" + frappe.utils.escape_html(row.idx || "") + "</td>",
            "<td>" + frappe.utils.escape_html(row.item_code || "") + "</td>",
            "<td class='text-right'>" + frappe.format(row.old_qty, {fieldtype: "Float"}) + "</td>",
            "<td class='text-right'>" + frappe.format(row.new_qty, {fieldtype: "Float"}) + "</td>",
            "<td>" + frappe.utils.escape_html(row.batch_no || "") + "</td>",
            "<td class='text-right'>" + frappe.utils.escape_html(row.serial_count || 0) + "</td>",
            "</tr>",
        ].join("");
    }).join("");

    const serial_conflicts = (result.serial_conflicts || []).map(function(row) {
        return __("Row {0}: {1}, qty {2}, serials {3}", [
            row.row,
            row.item_code,
            row.new_transfer_qty,
            row.serial_count,
        ]);
    }).join("<br>");

    const work_order = result.work_order_result || {};
    const work_order_qty = result.work_order_qty_before !== null && result.work_order_qty_before !== undefined
        ? "<br>" + __("WO Qty") + ": "
            + frappe.format(result.work_order_qty_before, {fieldtype: "Float"})
            + (result.work_order_qty_will_update ? " (" + __("will update") + ")" : " (" + __("unchanged") + ")")
        : "";
    const value_difference = result.value_difference_after !== null && result.value_difference_after !== undefined
        ? "<br>" + __("Value Difference") + ": "
            + frappe.format(result.value_difference_before, {fieldtype: "Currency"})
            + " &rarr; "
            + frappe.format(result.value_difference_after, {fieldtype: "Currency"})
        : "";
    const totals = result.total_incoming_value_after !== null && result.total_incoming_value_after !== undefined
        ? "<br>" + __("Incoming / Outgoing") + ": "
            + frappe.format(result.total_incoming_value_after, {fieldtype: "Currency"})
            + " / "
            + frappe.format(result.total_outgoing_value_after, {fieldtype: "Currency"})
        : "";
    const value_balance = result.value_balance || {};
    const balance_row = value_balance.status === "balanced"
        ? "<br>" + __("Balanced Row") + ": "
            + frappe.utils.escape_html(value_balance.row || "")
            + " (" + frappe.format(value_balance.adjustment, {fieldtype: "Currency"}) + ")"
        : "";
    const message = [
        "<p><b>" + frappe.utils.escape_html(result.message || result.status) + "</b></p>",
        "<p>",
        __("Stock Entry") + ": <b>" + frappe.utils.escape_html(result.stock_entry || "") + "</b><br>",
        __("Quantity") + ": " + frappe.format(result.current_fg_completed_qty, {fieldtype: "Float"}),
        " &rarr; ",
        frappe.format(result.new_fg_completed_qty, {fieldtype: "Float"}),
        result.work_order ? "<br>" + __("Work Order") + ": <b>" + frappe.utils.escape_html(result.work_order) + "</b>" : "",
        work_order_qty,
        work_order.work_order ? "<br>" + __("WO Produced Qty") + ": " + frappe.format(work_order.produced_qty_after, {fieldtype: "Float"}) : "",
        value_difference,
        totals,
        balance_row,
        "</p>",
        serial_conflicts ? "<p class='text-danger'>" + serial_conflicts + "</p>" : "",
        rows ? [
            "<table class='table table-bordered table-condensed'>",
            "<thead><tr>",
            "<th>" + __("Row") + "</th>",
            "<th>" + __("Item") + "</th>",
            "<th class='text-right'>" + __("Old Qty") + "</th>",
            "<th class='text-right'>" + __("New Qty") + "</th>",
            "<th>" + __("Batch") + "</th>",
            "<th class='text-right'>" + __("Serials") + "</th>",
            "</tr></thead>",
            "<tbody>",
            rows,
            "</tbody></table>",
        ].join("") : "",
        result.rows && result.rows.length > 12 ? "<p>" + __("Showing first 12 rows.") + "</p>" : "",
        result.new_stock_ledger_entries !== undefined ? "<p>" + __("SLE") + ": " + result.new_stock_ledger_entries + " / " + __("GL") + ": " + result.new_gl_entries + "</p>" : "",
    ].join("");

    frappe.msgprint({
        title: __("Manufacture Qty Correction"),
        indicator: indicator,
        message: message,
    });
}
