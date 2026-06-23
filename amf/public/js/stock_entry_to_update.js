/*
Stock Entry Client Script
-------------------------

Refactored from the Desk Custom Script version. This file is intentionally
standalone so it can be copied back to a Custom Script or merged into
public/js/stock_entry.js.
*/

(function () {
    const SETTINGS = {
        main_warehouse: "Main Stock - AMF21",
        wip_warehouse: "Work In Progress - AMF21",
        scrap_warehouse: "Scrap - AMF21",
        expense_account: "4900 - Stock variation - AMF21",
        cost_center: "Automation - AMF21",
    };

    frappe.ui.form.on("Stock Entry", {
        refresh: function (frm) {
            add_label_buttons(frm);

            if (frm.is_new() && frm.doc.work_order) {
                apply_warehouse_defaults(frm, { refresh: true, notify: true });
            }
        },

        onload: function (frm) {
            initialise_auto_batch_flags(frm);
        },

        work_order: function (frm) {
            frm._amf_work_order_context = null;
            return apply_warehouse_defaults(frm, { refresh: true, notify: true });
        },

        purpose: function (frm) {
            return apply_warehouse_defaults(frm, { refresh: true });
        },

        before_save: async function (frm) {
            await apply_warehouse_defaults(frm);
            apply_accounting_defaults(frm);
        },

        before_submit: async function (frm) {
            await apply_manufacture_batch(frm);
            await assign_auto_batches(frm);
            frm.refresh_field("items");
        },

        update_rate_and_availability: function (frm) {
            return update_rate_and_availability(frm);
        },
    });

    frappe.ui.form.on("Stock Entry Detail", {
        batch_no: function (frm, cdt, cdn) {
            return sync_component_batch_to_finished_row(frm, cdt, cdn);
        },

        manual_source_warehouse_selection: function (frm) {
            return apply_warehouse_defaults(frm, { refresh: true });
        },

        manual_target_warehouse_selection: function (frm) {
            return apply_warehouse_defaults(frm, { refresh: true });
        },
    });

    function add_label_buttons(frm) {
        if (frm.doc.docstatus !== 1) {
            return;
        }

        if (is_manufacture(frm)) {
            frm.add_custom_button(__('<i class="fa fa-print"></i> QR Code'), function () {
                open_label_url(frm, "Serial No Item", "Labels 35x55mm");
            });
        }

        frm.add_custom_button(__('<i class="fa fa-print"></i> Sticker'), function () {
            open_label_url(frm, "Stock Entry Sticker", "Labels 45x55mm");
        });
    }

    function open_label_url(frm, print_format, label_reference) {
        const url = frappe.urllib.get_full_url(
            "/api/method/amf.amf.utils.labels.download_label_for_doc"
            + "?doctype=" + encodeURIComponent(frm.doc.doctype)
            + "&docname=" + encodeURIComponent(frm.doc.name)
            + "&print_format=" + encodeURIComponent(print_format)
            + "&label_reference=" + encodeURIComponent(label_reference)
        );
        const opened = window.open(url, "_blank");

        if (!opened) {
            frappe.msgprint(__("Please enable pop-ups."));
        }
    }

    function initialise_auto_batch_flags(frm) {
        if (!frm.doc.auto_batch_generation_method) {
            return;
        }

        (frm.doc.items || []).forEach(function (row) {
            if (row.auto_batch_no_generation === undefined || row.auto_batch_no_generation === null) {
                row.auto_batch_no_generation = 1;
            }
        });
    }

    async function apply_warehouse_defaults(frm, options) {
        options = options || {};

        if (!can_apply_warehouse_defaults(frm)) {
            return false;
        }

        const work_order = await get_work_order_context(frm);
        const plan = get_warehouse_plan(frm, work_order);

        if (!plan) {
            return false;
        }

        let changed = false;
        changed = set_doc_value(frm.doc, "from_warehouse", plan.from_warehouse) || changed;
        changed = set_doc_value(frm.doc, "to_warehouse", plan.to_warehouse) || changed;

        if (plan.mode === "manufacture") {
            changed = apply_manufacture_warehouses(frm, work_order, plan) || changed;
        } else {
            changed = apply_simple_warehouse_plan(frm, plan) || changed;
        }

        if (changed && options.refresh) {
            frm.refresh_field("from_warehouse");
            frm.refresh_field("to_warehouse");
            frm.refresh_field("items");
        }

        if (changed && options.notify) {
            frappe.show_alert({
                message: get_warehouse_message(plan),
                indicator: "green",
            });
        }

        return changed;
    }

    function can_apply_warehouse_defaults(frm) {
        return frm.doc.docstatus === 0
            && frm.doc.work_order
            && (frm.doc.items || []).length > 0;
    }

    async function get_work_order_context(frm) {
        const cache_key = frm.doc.work_order;
        if (frm._amf_work_order_context && frm._amf_work_order_context.cache_key === cache_key) {
            return frm._amf_work_order_context;
        }

        const response = await frappe.db.get_value("Work Order", frm.doc.work_order, [
            "production_item",
            "wip_step",
            "skip_transfer",
            "spare_part_production",
            "spare_batch_no",
        ]);

        frm._amf_work_order_context = Object.assign(
            { cache_key: cache_key },
            response && response.message ? response.message : {}
        );
        return frm._amf_work_order_context;
    }

    function get_warehouse_plan(frm, work_order) {
        if (!work_order || !is_warehouse_managed_work_order(work_order)) {
            return null;
        }

        if (frm.doc.purpose === "Manufacture") {
            const raw_source = uses_wip_raw_material_source(work_order)
                ? SETTINGS.wip_warehouse
                : SETTINGS.main_warehouse;
            return {
                mode: "manufacture",
                from_warehouse: raw_source,
                to_warehouse: SETTINGS.main_warehouse,
                raw_source: raw_source,
                finished_target: SETTINGS.main_warehouse,
            };
        }

        if (frm.doc.purpose === "Material Transfer for Manufacture") {
            return {
                mode: "transfer",
                from_warehouse: SETTINGS.main_warehouse,
                to_warehouse: SETTINGS.wip_warehouse,
                row_source: SETTINGS.main_warehouse,
                row_target: SETTINGS.wip_warehouse,
            };
        }

        if (frm.doc.purpose === "Material Issue") {
            return {
                mode: "issue",
                from_warehouse: SETTINGS.main_warehouse,
                to_warehouse: "",
                row_source: SETTINGS.main_warehouse,
                row_target: "",
            };
        }

        if (frm.doc.purpose === "Material Receipt") {
            return {
                mode: "receipt",
                from_warehouse: "",
                to_warehouse: SETTINGS.main_warehouse,
                row_source: "",
                row_target: SETTINGS.main_warehouse,
            };
        }

        return null;
    }

    function is_warehouse_managed_work_order(work_order) {
        const production_item = work_order.production_item || "";
        return Boolean(production_item);
    }

    function uses_wip_raw_material_source(work_order) {
        return cint(work_order.wip_step) === 0 || cint(work_order.skip_transfer) === 0;
    }

    function apply_manufacture_warehouses(frm, work_order, plan) {
        const finished_row = get_finished_good_row(frm, work_order);
        let changed = false;

        (frm.doc.items || []).forEach(function (row) {
            if (is_dynamic_scrap_row(row)) {
                return;
            }

            if (is_same_row(row, finished_row)) {
                changed = set_row_warehouse(row, "s_warehouse", "", "manual_source_warehouse_selection") || changed;
                changed = set_row_warehouse(row, "t_warehouse", plan.finished_target, "manual_target_warehouse_selection") || changed;
                return;
            }

            if (is_incoming_only_row(row)) {
                return;
            }

            changed = set_row_warehouse(row, "s_warehouse", plan.raw_source, "manual_source_warehouse_selection") || changed;
            changed = set_row_warehouse(row, "t_warehouse", "", "manual_target_warehouse_selection") || changed;
        });

        return changed;
    }

    function apply_simple_warehouse_plan(frm, plan) {
        let changed = false;

        (frm.doc.items || []).forEach(function (row) {
            if (is_dynamic_scrap_row(row)) {
                return;
            }

            changed = set_row_warehouse(row, "s_warehouse", plan.row_source, "manual_source_warehouse_selection") || changed;
            changed = set_row_warehouse(row, "t_warehouse", plan.row_target, "manual_target_warehouse_selection") || changed;
        });

        return changed;
    }

    function get_finished_good_row(frm, work_order) {
        const rows = (frm.doc.items || []).filter(function (row) {
            return !is_dynamic_scrap_row(row);
        });
        const production_item = work_order && work_order.production_item;

        if (production_item) {
            const production_rows = rows.filter(function (row) {
                return row.item_code === production_item;
            });

            const incoming_production_row = production_rows.find(is_incoming_or_unset_row);
            if (incoming_production_row) {
                return incoming_production_row;
            }

            if (production_rows.length) {
                return production_rows[production_rows.length - 1];
            }
        }

        const incoming_rows = rows.filter(is_incoming_only_row);
        if (incoming_rows.length) {
            return incoming_rows[incoming_rows.length - 1];
        }

        return rows.length ? rows[rows.length - 1] : null;
    }

    function set_doc_value(doc, fieldname, value) {
        value = value || "";
        if ((doc[fieldname] || "") === value) {
            return false;
        }
        doc[fieldname] = value;
        return true;
    }

    function is_same_row(row, other_row) {
        return Boolean(other_row && (row === other_row || (row.name && row.name === other_row.name)));
    }

    function set_row_warehouse(row, fieldname, value, manual_fieldname) {
        if (cint(row[manual_fieldname])) {
            return false;
        }

        value = value || "";
        if ((row[fieldname] || "") === value) {
            return false;
        }

        row[fieldname] = value;
        return true;
    }

    function get_warehouse_message(plan) {
        if (plan.mode === "manufacture") {
            return __("Manufacture warehouses set: raw materials from {0}, finished goods to {1}.", [
                plan.raw_source,
                plan.finished_target,
            ]);
        }

        return __("Warehouses set: {0} to {1}.", [
            plan.row_source || __("empty"),
            plan.row_target || __("empty"),
        ]);
    }

    function apply_accounting_defaults(frm) {
        (frm.doc.items || []).forEach(function (row) {
            row.expense_account = SETTINGS.expense_account;
            if (["Manufacture", "Material Transfer for Manufacture"].indexOf(frm.doc.purpose) !== -1) {
                row.cost_center = SETTINGS.cost_center;
            }
        });
    }

    async function apply_manufacture_batch(frm) {
        if (!is_manufacture(frm) || !frm.doc.work_order) {
            return;
        }

        const work_order = await get_work_order_context(frm);
        const target_row = get_finished_good_row(frm, work_order);

        if (!target_row || !target_row.item_code) {
            return;
        }

        if (cint(work_order.spare_part_production) && work_order.spare_batch_no) {
            target_row.auto_batch_no_generation = 0;
            target_row.batch_no = work_order.spare_batch_no;
            return;
        }

        await assign_auto_batch_for_row(frm, target_row);
    }

    async function assign_auto_batches(frm) {
        const rows = (frm.doc.items || []).filter(row_needs_auto_batch);
        if (!rows.length) {
            return;
        }

        const item_batch_map = await get_item_batch_map(rows.map(function (row) {
            return row.item_code;
        }));

        for (const row of rows) {
            await assign_auto_batch_for_row(frm, row, item_batch_map);
        }
    }

    function row_needs_auto_batch(row) {
        return row
            && row.item_code
            && !row.batch_no
            && cint(row.auto_batch_no_generation) === 1
            && is_incoming_only_row(row);
    }

    async function get_item_batch_map(item_codes) {
        const unique_items = Array.from(new Set(item_codes.filter(Boolean)));
        const item_batch_map = {};

        if (!unique_items.length) {
            return item_batch_map;
        }

        const items = await frappe.db.get_list("Item", {
            filters: { name: ["in", unique_items] },
            fields: ["name", "has_batch_no"],
            limit_page_length: unique_items.length,
        });

        (items || []).forEach(function (item) {
            item_batch_map[item.name] = cint(item.has_batch_no);
        });

        return item_batch_map;
    }

    async function assign_auto_batch_for_row(frm, row, item_batch_map) {
        if (!row_needs_auto_batch(row)) {
            return;
        }

        let has_batch_no = item_batch_map && Object.prototype.hasOwnProperty.call(item_batch_map, row.item_code)
            ? item_batch_map[row.item_code]
            : null;

        if (has_batch_no === null) {
            const item = await frappe.db.get_value("Item", row.item_code, "has_batch_no");
            has_batch_no = item && item.message ? cint(item.message.has_batch_no) : 0;
        }

        if (has_batch_no !== 1) {
            return;
        }

        const batch_id = await get_internal_production_batch_id();
        if (!batch_id) {
            frappe.throw(__("Could not generate a batch number for {0}.", [row.item_code]));
        }

        const exists = await frappe.db.exists("Batch", batch_id);
        if (exists) {
            row.batch_no = batch_id;
            return;
        }

        const created = await frappe.call({
            method: "frappe.client.insert",
            args: {
                doc: {
                    doctype: "Batch",
                    item: row.item_code,
                    batch_id: batch_id,
                    reference_doctype: frm.doc.doctype,
                    reference_name: frm.doc.name,
                },
            },
        });

        row.batch_no = created && created.message ? created.message.name : batch_id;
    }

    async function get_internal_production_batch_id() {
        const response = await frappe.call({
            method: "amf.amf.utils.batch_naming.make_internal_production_batch_id_api",
        });
        return response && response.message;
    }

    async function sync_component_batch_to_finished_row(frm, cdt, cdn) {
        const row = locals[cdt] && locals[cdt][cdn];
        const finished_row = get_finished_good_row(frm, frm._amf_work_order_context || {});

        if (!row || !row.item_code || !row.batch_no || !finished_row || row.name === finished_row.name) {
            return;
        }

        const [source_item, finished_item] = await Promise.all([
            frappe.db.get_value("Item", row.item_code, "item_group"),
            frappe.db.get_value("Item", finished_row.item_code, "item_group"),
        ]);

        const source_group = source_item && source_item.message ? source_item.message.item_group : "";
        const finished_group = finished_item && finished_item.message ? finished_item.message.item_group : "";

        if (source_group === "Plug" && ["Plug", "Valve Head"].indexOf(finished_group) !== -1) {
            await frappe.model.set_value(finished_row.doctype, finished_row.name, "plug_batch_no", row.batch_no);
        } else if (source_group === "Valve Seat" && ["Valve Seat", "Valve Head"].indexOf(finished_group) !== -1) {
            await frappe.model.set_value(finished_row.doctype, finished_row.name, "seat_batch_no", row.batch_no);
        }
    }

    function update_rate_and_availability(frm) {
        return frappe.call({
            method: "amf.amf.utils.stock_entry.get_stock_and_rate_override",
            args: { doc: frm.doc },
            callback: function () {
                frm.reload_doc();
            },
        });
    }

    function is_manufacture(frm) {
        return frm.doc.purpose === "Manufacture" || frm.doc.stock_entry_type === "Manufacture";
    }

    function is_dynamic_scrap_row(row) {
        return cint(row && row.amf_dynamic_usage_scrap) === 1;
    }

    function is_incoming_only_row(row) {
        return !!(row && row.t_warehouse && !row.s_warehouse);
    }

    function is_incoming_or_unset_row(row) {
        return !!(row && (!row.s_warehouse || row.t_warehouse));
    }
})();
