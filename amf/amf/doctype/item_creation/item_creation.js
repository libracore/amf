// Item Creation: one read-only plan shared with engineering review and execution.
const itemCreationWorkflow = "amf.amf.utils.item_creation_workflow.";
const itemCreationController = "amf.amf.doctype.item_creation.item_creation.";

function itemCreationEscape(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, character =>
        ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[character]));
}

function itemCreationLink(doctype, name) {
    if (!name) return "—";
    const route = "#Form/" + encodeURIComponent(doctype) + "/" + encodeURIComponent(name);
    return '<a href="' + route + '">' + itemCreationEscape(name) + '</a>';
}

function itemCreationInputs(frm) {
    // Exclude review/status fields. This stamp also rejects responses to unsaved edits.
    const values = {};
    Object.keys(frm.doc).sort().forEach(key => {
        if (!key.startsWith("_") && !["modified", "review_history", "creation_result", "review_status",
            "reviewed_by", "reviewed_at", "approved_plan_hash", "approved_input_hash"].includes(key)) {
            values[key] = frm.doc[key];
        }
    });
    return JSON.stringify(values);
}

function itemCreationMaterials(rows, scrap, itemMap) {
    if (!rows || !rows.length) return '<p class="text-muted">' + __("None") + '</p>';
    const body = rows.map(row => {
        const item = (itemMap || {})[row.item_code] || {};
        const dependency = (row.bom_no || "").startsWith("@new:")
            ? __("New BOM for {0}", [itemCreationEscape(row.bom_no.slice(5))])
            : row.bom_no ? itemCreationLink("BOM", row.bom_no) : "—";
        const name = item.item_name ? '<br><small>' + itemCreationEscape(item.item_name) + '</small>' : '';
        return '<tr><td>' + itemCreationLink("Item", row.item_code) + name + '</td><td>' +
            itemCreationEscape(scrap ? row.stock_qty : row.qty) + '</td><td>' +
            itemCreationEscape(scrap ? row.stock_uom : row.uom) + '</td><td>' + dependency + '</td><td>' +
            (scrap ? "—" : row.include_item_in_manufacturing ? __("Yes") : __("No")) + '</td></tr>';
    }).join("");
    return '<table class="table table-bordered table-condensed"><thead><tr><th>' + __("Material") +
        '</th><th>' + __("Quantity per unit") + '</th><th>' + __("UOM") + '</th><th>' +
        __("Child BOM") + '</th><th>' + __("Include in manufacturing") + '</th></tr></thead><tbody>' + body + '</tbody></table>';
}

function itemCreationRecipe(recipe, itemMap) {
    if (!recipe) return '<p class="text-muted">' + __("No existing recipe") + '</p>';
    let html = '<p>' + itemCreationEscape(recipe.company) + ' · ' + itemCreationEscape(recipe.uom) + '</p>';
    html += itemCreationMaterials(recipe.materials, false, itemMap);
    if (recipe.scraps && recipe.scraps.length) html += '<b>' + __("Scrap outputs") + '</b>' + itemCreationMaterials(recipe.scraps, true, itemMap);
    if (recipe.operations && recipe.operations.length) {
        html += '<b>' + __("Operations") + '</b><ul>' + recipe.operations.map(row => '<li>' +
            itemCreationEscape(row.operation) + ' · ' + itemCreationEscape(row.workstation || '') + ' · ' +
            itemCreationEscape(row.time_in_mins) + ' min</li>').join("") + '</ul>';
    }
    return html;
}

function renderItemCreationPlan(plan) {
    const summary = plan.summary || {};
    const itemMap = Object.create(null);
    ((plan.dependencies || {}).items || []).forEach(item => { itemMap[item.name] = item; });
    (plan.actions || []).forEach(action => { itemMap[action.item.item_code] = action.item; });
    let html = '<div class="item-creation-plan"><p><strong>' + __("Complete creation plan") + '</strong> · ' +
        __("{0} Items, {1} new BOMs, {2} replacement BOMs, {3} reused BOMs", [summary.items || 0,
            summary.new_boms || 0, summary.replacement_boms || 0, summary.reused_boms || 0]) + '</p>';
    if (plan.errors && plan.errors.length) html += '<div class="alert alert-danger"><b>' + __("Resolve before review") +
        '</b><ul>' + plan.errors.map(row => '<li>' + itemCreationEscape(row.message) + '</li>').join("") + '</ul></div>';
    if (plan.warnings && plan.warnings.length) html += '<div class="alert alert-warning">' +
        plan.warnings.map(itemCreationEscape).join('<br>') + '</div>';
    html += (plan.actions || []).map(action => {
        const title = itemCreationEscape(action.item.item_code + " · " + action.item.item_name);
        let detail = '<details' + (action.bom_action === "replace" ? ' open' : '') + '><summary><b>' + title + '</b> · ' +
            itemCreationEscape(__(action.item_action)) + ' Item · ' + itemCreationEscape(__(action.bom_action)) + ' BOM</summary>';
        if (action.existing_bom) detail += '<p>' + __("Existing BOM") + ': ' + itemCreationLink("BOM", action.existing_bom) + '</p>';
        if (action.bom_action === "replace") {
            const before = Object.assign({}, action.proposed);
            Object.keys(action.diff || {}).forEach(key => { before[key] = action.diff[key].before; });
            detail += '<div class="row"><div class="col-sm-6"><b>' + __("Existing definition") + '</b>' +
                itemCreationRecipe(before, itemMap) + '</div><div class="col-sm-6"><b>' + __("Proposed replacement") + '</b>' +
                itemCreationRecipe(action.proposed, itemMap) + '</div></div>';
        } else detail += itemCreationRecipe(action.proposed, itemMap);
        return detail + '</details><hr>';
    }).join("");
    if (plan.dependency_boms && plan.dependency_boms.length) html += '<details><summary><b>' +
        __("Existing dependency BOMs") + '</b></summary>' + plan.dependency_boms.map(row =>
        '<details><summary>' + itemCreationLink("BOM", row.name) + ' · ' + itemCreationLink("Item", row.item) +
        '</summary>' + itemCreationRecipe(row.recipe, itemMap) + '</details>').join("") + '</details><hr>';
    if (plan.affected_parents && plan.affected_parents.length) html += '<p><b>' + __("Parents retaining their existing revisions") +
        '</b></p><ul>' + plan.affected_parents.map(row => '<li>' + itemCreationLink("BOM", row.bom) + ' · ' +
            itemCreationLink("Item", row.item) + ' · ' + itemCreationLink("BOM", row.child_bom) + '</li>').join("") + '</ul>';
    if (plan.result) html += '<div class="alert alert-success">' + __("Creation and verification completed") + '</div><ul>' +
        (plan.result.records || []).map(row => '<li>' + itemCreationLink("Item", row.item_code) + ' · ' +
            itemCreationLink("BOM", row.bom) + '</li>').join("") + '</ul>';
    return html + '</div>';
}

function refreshItemCreationPlan(frm) {
    const sequence = (frm.__plan_sequence || 0) + 1;
    frm.__plan_sequence = sequence;
    const stamp = itemCreationInputs(frm);
    frm.__creation_plan = null;
    frm.set_df_property("plan_preview", "options", '<p class="text-muted">' + __("Checking the complete plan…") + '</p>');
    return frappe.call({method: itemCreationWorkflow + "get_creation_plan", args: {document: frm.doc},
        callback: response => {
            if (sequence !== frm.__plan_sequence || stamp !== itemCreationInputs(frm)) return;
            if (!response.message || response.exc) {
                frm.set_df_property("plan_preview", "options", '<p class="text-danger">' + __("The plan could not be loaded. Refresh after resolving the error.") + '</p>');
                return;
            }
            frm.__creation_plan = response.message;
            frm.set_df_property("plan_preview", "options", renderItemCreationPlan(response.message));
            if (frm.doc.docstatus === 0 && frm.doc.approved_plan_hash &&
                    frm.doc.approved_plan_hash !== response.message.fingerprint) {
                frm.set_intro(__("The recorded review is stale because the plan or its dependencies changed. Review the refreshed plan before submission."));
            }
        },
        error: () => {
            if (sequence === frm.__plan_sequence && stamp === itemCreationInputs(frm)) {
                frm.set_df_property("plan_preview", "options", '<p class="text-danger">' + __("The plan could not be loaded.") + '</p>');
            }
        },
    });
}

function scheduleItemCreationPlan(frm) {
    frm.__creation_plan = null;
    frm.__plan_sequence = (frm.__plan_sequence || 0) + 1;
    clearTimeout(frm.__plan_timer);
    frm.__plan_timer = setTimeout(() => refreshItemCreationPlan(frm), 350);
}

function updateItemCreationFamilyCodes(frm) {
    const code = (frm.doc.head_code || "").trim().toUpperCase();
    if (code && !/^30[0-9A-Z]{4}$/.test(code)) frappe.throw(__("The head code must contain six letters/digits starting with 30."));
    const values = {};
    if (frm.doc.seat_check === "Yes") values.seat_code = code ? "20" + code.slice(2) : "";
    if (frm.doc.plug_check === "Yes") values.plug_code = code ? "10" + code.slice(2) : "";
    frm.set_value(values);
    scheduleItemCreationPlan(frm);
}

function updateItemCreationStockUom(frm, group) {
    const code = frm.doc[group + "_raw_material"];
    frm.set_value(group + "_raw_uom", "");
    if (!code) return scheduleItemCreationPlan(frm);
    frappe.call({method: "frappe.client.get_value", args: {doctype: "Item", filters: {name: code}, fieldname: ["stock_uom"]},
        callback: response => {
            if (frm.doc[group + "_raw_material"] !== code) return;
            frm.set_value(group + "_raw_uom", response.message ? response.message.stock_uom : "");
            scheduleItemCreationPlan(frm);
        }});
}

function chooseItemCreationVariants(frm) {
    const stamp = itemCreationInputs(frm);
    frappe.call({method: itemCreationWorkflow + "get_compatible_variants", args: {document: frm.doc}, callback: response => {
        if (stamp !== itemCreationInputs(frm) || !response.message) return;
        const variants = response.message;
        if (!variants.length) return frappe.msgprint(__("Select an eligible product family and head first. HV heads support HV variants; standard heads support RVM/LV variants."));
        const selected = new Set((frm.doc.product_variants || []).filter(row => row.selected).map(row => row.body + ":" + (row.syringe || "")));
        const dialog = new frappe.ui.Dialog({title: __("Choose Supported Product Configurations"), fields: [{
            fieldname: "variants", fieldtype: "MultiCheck", label: __("Configurations"), columns: 2, select_all: true,
            options: variants.map(row => ({value: row.body + ":" + row.syringe,
                label: itemCreationEscape(row.configuration), checked: selected.has(row.body + ":" + row.syringe)})),
        }], primary_action_label: __("Apply Selection"), primary_action: values => {
            if (stamp !== itemCreationInputs(frm)) return frappe.msgprint(__("The definition changed. Open the configuration selection again."));
            const choices = new Set(values.variants || []);
            frm.clear_table("product_variants");
            variants.filter(row => choices.has(row.body + ":" + row.syringe)).forEach(row => {
                Object.assign(frm.add_child("product_variants"), row, {selected: 1});
            });
            frm.refresh_field("product_variants");
            frm.dirty();
            dialog.hide();
            scheduleItemCreationPlan(frm);
        }});
        dialog.show();
    }});
}

function reviewItemCreationPlan(frm) {
    if (frm.is_dirty()) return frappe.msgprint(__("Save the definition, then refresh and review its complete plan."));
    const plan = frm.__creation_plan;
    if (!plan || !plan.ready) return frappe.msgprint(__("Refresh the plan and resolve all errors before engineering review."));
    const stamp = itemCreationInputs(frm);
    const dialog = new frappe.ui.Dialog({title: __("Record Engineering Review"), fields: [{
        fieldname: "notes", fieldtype: "Small Text", label: __("Engineering Review Notes"), reqd: 1,
        description: __("Confirm stock dimensions/grades, quantities, configuration compatibility and any replacement decisions shown in the plan."),
    }], primary_action_label: __("Approve This Plan"), primary_action: values => {
        if (stamp !== itemCreationInputs(frm) || frm.is_dirty()) return frappe.msgprint(__("The definition changed. Save and refresh the plan before reviewing."));
        frappe.call({method: itemCreationWorkflow + "record_engineering_review", type: "POST", freeze: true,
            args: {name: frm.doc.name, fingerprint: plan.fingerprint, review_notes: values.notes},
            callback: response => {
                if (response.exc || !response.message) return;
                dialog.hide();
                frm.reload_doc();
            }});
    }});
    dialog.show();
}

frappe.ui.form.on("Item Creation", {
    refresh(frm) {
        frm.set_query("default_warehouse", () => ({filters: {company: frm.doc.company, is_group: 0, disabled: 0}}));
        frm.set_query("head_item", () => ({filters: {item_group: "Valve Head", disabled: 0}}));
        // Each underscore matches one character, preserving six-character item codes.
        frm.set_query("body", "product_variants", () => ({filters: {item_code: ["like", "5_1___"]}}));
        frm.set_query("syringe", "product_variants", () => ({filters: {item_code: ["like", "70____"]}}));
        ["plug", "seat"].forEach(group => {
            frm.set_query(group + "_item", () => ({filters: {item_group: group === "plug" ? "Plug" : "Valve Seat", disabled: 0}}));
            frm.set_query(group + "_raw_material", () => ({filters: {item_group: "Raw Material", tag_raw_mat: frm.doc[group + "_mat"], disabled: 0}}));
        });
        // Fasteners may belong to child groups; avoid the former exact Part filter.
        frm.set_query("screw_type", () => ({filters: [["Item", "item_name", "like", "%Screw%"], ["Item", "disabled", "=", 0]]}));
        frm.set_query("cap_type", () => ({filters: {name: ["in", ["RVM.3038", "RVM.3039", "RVM.3040"]], disabled: 0}}));
        frm.add_custom_button(__("Refresh Complete Plan"), () => refreshItemCreationPlan(frm));
        if (frm.doc.docstatus === 0) {
            frm.add_custom_button(__("Choose Product Configurations"), () => chooseItemCreationVariants(frm));
            if ((frappe.user_roles || []).includes("System Manager") || frappe.session.user === "Administrator") {
                frm.add_custom_button(__("Record Engineering Review"), () => reviewItemCreationPlan(frm));
            }
        }
        frm.set_intro(frm.doc.review_status === "Reviewed"
            ? __("Engineering review recorded. Submission will recheck the exact plan and automatically submit its BOMs.")
            : __("Define the parts and raw stock, choose supported configurations, save, then review the complete plan before submission."));
        scheduleItemCreationPlan(frm);
    },
    head_name(frm) {
        scheduleItemCreationPlan(frm);
        const name = frm.doc.head_name;
        const sequence = (frm.__head_request || 0) + 1;
        frm.__head_request = sequence;
        if (frm.doc.head_check !== "Yes" || !name || name === "VALVE HEAD-") return;
        const current = () => sequence === frm.__head_request && frm.doc.head_name === name && frm.doc.head_check === "Yes";
        frappe.call({method: itemCreationController + "populate_fields", args: {head_name: name}, callback: response => {
            if (!current() || !response.message || response.exc) return;
            if (!response.message.custom_definition) {
                const values = Object.assign({}, response.message);
                delete values.custom_definition;
                frm.set_value(values);
            }
            else frm.set_intro(__("Custom design: enter explicit component names, references and material tags for engineering review."));
        }});
        frappe.call({method: itemCreationController + "suggest_bom_managed_item_code",
            args: {item_group: "Valve Head", has_bom: 1, source_document: frm.doc.__islocal ? null : frm.doc.name},
            callback: response => { if (current() && response.message && !response.exc) frm.set_value("head_code", response.message.item_code); }});
    },
    head_item(frm) {
        const item = frm.doc.head_item;
        if (frm.doc.head_check !== "No" || !item) return;
        frappe.call({method: itemCreationController + "populate_fields_from_existing_item", args: {item_code: item}, callback: response => {
            if (frm.doc.head_item !== item || frm.doc.head_check !== "No" || !response.message || response.exc) return;
            const values = Object.assign({}, response.message, {plug_check: "No", seat_check: "No",
                plug_item: response.message.plug_code, seat_item: response.message.seat_code});
            frm.set_value(values);
            scheduleItemCreationPlan(frm);
        }});
    },
    head_check(frm) {
        frm.__head_request = (frm.__head_request || 0) + 1;
        frm.set_value({head_item: "", head_code: "", head_name: "VALVE HEAD-", head_rnd: "", head_description: "",
            plug_item: "", seat_item: "", plug_check: "", seat_check: "", plug_code: "", seat_code: "", replace_boms: 0});
        scheduleItemCreationPlan(frm);
    },
    head_code: updateItemCreationFamilyCodes,
    seat_check: updateItemCreationFamilyCodes,
    plug_check: updateItemCreationFamilyCodes,
    seat_item(frm) { frm.set_value("seat_code", frm.doc.seat_item || ""); scheduleItemCreationPlan(frm); },
    plug_item(frm) { frm.set_value("plug_code", frm.doc.plug_item || ""); scheduleItemCreationPlan(frm); },
    plug_raw_material(frm) { updateItemCreationStockUom(frm, "plug"); },
    seat_raw_material(frm) { updateItemCreationStockUom(frm, "seat"); },
    company(frm) { frm.set_value("default_warehouse", ""); scheduleItemCreationPlan(frm); },
    head_description_check(frm) { frm.set_df_property("head_description", "read_only", !frm.doc.head_description_check); },
    on_submit(frm) { frm.reload_doc(); },
});

// All recipe-affecting fields invalidate the cached plan immediately, then debounce IO.
const itemCreationPlanEvents = {};
["head_rnd", "head_description", "plug_name", "plug_rnd", "plug_mat", "plug_acc", "plug_drawing", "seat_name",
    "seat_rnd", "seat_mat", "seat_acc", "seat_drawing", "plug_raw_qty", "plug_raw_uom", "seat_raw_qty", "seat_raw_uom",
    "screw_type", "screw_quantity", "cap_type", "rvm_check", "pump_check", "pump_hv_check", "replace_boms", "default_warehouse"]
    .forEach(field => { itemCreationPlanEvents[field] = scheduleItemCreationPlan; });
frappe.ui.form.on("Item Creation", itemCreationPlanEvents);
frappe.ui.form.on("Item Creation Variant", {selected: scheduleItemCreationPlan, body: scheduleItemCreationPlan,
    syringe: scheduleItemCreationPlan, product_variants_remove: scheduleItemCreationPlan});
