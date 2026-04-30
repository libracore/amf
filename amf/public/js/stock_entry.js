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
                reqd: 1,
            },
            {
                fieldname: "dry_run",
                fieldtype: "Check",
                label: __("Preview only"),
                default: 1,
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
                fieldname: "reason",
                fieldtype: "Small Text",
                label: __("Reason"),
            },
        ],
        primary_action_label: __("Run"),
        primary_action: function(values) {
            if (!values.dry_run) {
                frappe.confirm(
                    __("This will update a submitted Stock Entry and repost stock/accounting ledgers. Continue?"),
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

function run_manufacture_qty_correction(frm, dialog, values) {
    frappe.call({
        method: "amf.amf.utils.stock_entry.correct_submitted_manufacture_qty",
        args: values,
        freeze: true,
        freeze_message: values.dry_run ? __("Preparing preview...") : __("Reposting ledgers..."),
        callback: function(response) {
            if (!response.exc && response.message) {
                show_manufacture_qty_correction_result(response.message);

                if (!values.dry_run && response.message.status === "updated") {
                    dialog.hide();
                    if (values.stock_entry_name === frm.doc.name) {
                        frm.reload_doc();
                    }
                }
            }
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
