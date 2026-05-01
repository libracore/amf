frappe.ui.form.on("Stock Entry", {
    refresh: function(frm) {
        if (frm.doc.docstatus === 1 && frm.doc.purpose === "Manufacture") {
            frm.add_custom_button(__("Correct Manufacture Qty"), function() {
                show_manufacture_qty_correction_dialog(frm);
            }, __("Repair"));
        }
    },
});

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
