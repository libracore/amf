const BOM_MANAGED_ITEM_GROUPS = ["Plug", "Valve Seat", "Valve Head"];
const BOM_CREATION_ITEM_GROUPS = ["Plug", "Valve Seat"];
const LEARNED_DEFAULT_ITEM_GROUPS = ["Plug", "Valve Seat", "Valve Head", "Product"];
const SPARE_PART_PREFIXES = ["30"];
const RVM_PREFIXES = ["41", "42", "43", "44", "4D", "51", "52", "53", "54", "5D"];
const SPM_STD_PREFIXES = ["45", "46", "47", "48", "55", "56", "57", "58"];
const SPM_HD_PREFIXES = ["49", "4A", "4B", "4C", "59", "5A", "5B", "5C"];
const SPM_HV_PREFIXES = ["46", "48", "4A", "4C", "56", "58", "5A", "5C"];
const RVM_PRODUCT_LINE_RULES = [
    ["-D-", "RVM D"],
    ["-S-", "RVM S"],
    ["-O-", "RVM O"],
];
const CUSTOM_PRODUCT_LINE_RULES = [
    ["NRE", "NRE"],
    ["CUSTOM VALVE", "Custom Valve"],
    ["VALVE CUSTOM", "Custom Valve"],
    ["CUSTOM SYSTEM", "Custom System"],
    ["CUSTOM CONFIGURATION", "Custom System"],
    ["CUSTOM", "Custom System"],
];

function isBomManagedItemGroup(itemGroup) {
    return BOM_MANAGED_ITEM_GROUPS.includes(itemGroup);
}

function getDefaultBomManagedItemGroup(frm) {
    return isBomManagedItemGroup(frm.doc.item_group) ? frm.doc.item_group : "Plug";
}

function getDefaultHasBom(frm, itemGroup) {
    if (itemGroup === "Valve Head") {
        return 1;
    }

    if (frm.doc.item_type === "Sub-Assembly") {
        return 1;
    }

    return frm.doc.default_bom ? 1 : 0;
}

function fetchBomManagedItemSuggestion(itemGroup, hasBom, callback) {
    frappe.call({
        method: "amf.amf.doctype.item_creation.item_creation.suggest_bom_managed_item_code",
        args: {
            item_group: itemGroup,
            has_bom: hasBom,
        },
        callback: function (r) {
            if (!r.exc && r.message) {
                callback(r.message);
            }
        },
    });
}

function getDefaultBomManagedItemName(itemGroup) {
    switch (itemGroup) {
        case "Valve Head":
            return "VALVE HEAD-A-X-XX-XXX-B-C";
        case "Valve Seat":
            return "SEAT-A-X-XX-XXX-B";
        case "Plug":
            return "PLUG-A-X-XX-XXX-B";
        default:
            return "";
    }
}

function applyBomManagedDefaults(frm, itemGroup) {
    frm.clear_table("uoms");
    frm.clear_table("item_defaults");
    frm.refresh_field("uoms");
    frm.refresh_field("item_defaults");

    if (!isBomManagedItemGroup(itemGroup)) {
        return;
    }

    frm.set_value("default_material_request_type", "Manufacture");
    frm.set_value("has_batch_no", 1);
    frm.set_value("create_new_batch", 0);
    frm.set_value("is_purchase_item", 0);
    frm.set_value("stock_uom", "Nos");
    frm.set_value("item_name", getDefaultBomManagedItemName(itemGroup));

    frm.add_child("uoms", {
        uom: "Nos",
        conversion_factor: 1,
    });
    frm.refresh_field("uoms");

    frm.add_child("item_defaults", {
        company: "Advanced Microfluidics SA",
        default_warehouse: "Main Stock - AMF21",
        expense_account: "4009 - Cost of material: Valve Head - AMF21",
        income_account: "3007 - Valve Head sales revenue - AMF21",
    });
    frm.refresh_field("item_defaults");

    if (itemGroup === "Valve Head") {
        frm.set_value("is_sales_item", 1);
        frm.set_value("sales_uom", "Nos");
    } else {
        frm.set_value("is_sales_item", 0);
        frm.set_value("sales_uom", "");
    }
}

function shouldRequireTagRawMat(itemCode, createBomAfterSave) {
    const prefix = (itemCode || "").slice(0, 2);
    return ["10", "20"].includes(prefix)
        || (createBomAfterSave && ["11", "21"].includes(prefix));
}

function updateTagRawMatRequirement(frm) {
    if (!frm.fields_dict.tag_raw_mat) {
        return;
    }

    frm.set_df_property(
        "tag_raw_mat",
        "reqd",
        shouldRequireTagRawMat(frm.doc.item_code, frm.__create_bom_after_save) ? 1 : 0
    );
}

function startsWithAny(value, prefixes) {
    return prefixes.some(function (prefix) {
        return value.startsWith(prefix);
    });
}

function getProductFamily(itemCode, itemName) {
    const normalizedCode = (itemCode || "").trim().toUpperCase();
    if (startsWithAny(normalizedCode, SPARE_PART_PREFIXES)) {
        return "Spare Part";
    }
    if (startsWithAny(normalizedCode, RVM_PREFIXES)) {
        return "RVM";
    }
    if (startsWithAny(normalizedCode, SPM_STD_PREFIXES.concat(SPM_HD_PREFIXES))) {
        return "SPM";
    }
    if (getCustomProductLine(itemCode, itemName)) {
        return "Custom";
    }

    return "";
}

function getProductLine(productFamily, itemCode, itemName) {
    const normalizedCode = (itemCode || "").trim().toUpperCase();
    const normalizedName = (itemName || "").toUpperCase();

    if (productFamily === "SPM") {
        if (startsWithAny(normalizedCode, SPM_HD_PREFIXES)) {
            return "SPM HD";
        }
        if (startsWithAny(normalizedCode, SPM_STD_PREFIXES)) {
            return "SPM STD";
        }
    }

    if (productFamily === "RVM") {
        for (const rule of RVM_PRODUCT_LINE_RULES) {
            if (normalizedName.includes(rule[0])) {
                return rule[1];
            }
        }
    }

    if (productFamily === "Custom") {
        return getCustomProductLine(itemCode, itemName);
    }

    return "";
}

function getProductVariant(productLine, itemCode, itemName) {
    if (!["SPM HD", "SPM STD"].includes(productLine)) {
        return "";
    }

    const normalizedCode = (itemCode || "").trim().toUpperCase();
    const normalizedName = (itemName || "").toUpperCase();
    const pressure = startsWithAny(normalizedCode, SPM_HV_PREFIXES) || normalizedName.includes("-HV")
        ? "HV"
        : "LV";

    return productLine + " " + pressure;
}

function getCustomProductLine(itemCode, itemName) {
    const value = ((itemCode || "") + " " + (itemName || "")).toUpperCase();
    for (const rule of CUSTOM_PRODUCT_LINE_RULES) {
        if (value.includes(rule[0])) {
            return rule[1];
        }
    }

    return "";
}

function updateItemReportingFields(frm) {
    const productFamily = getProductFamily(frm.doc.item_code, frm.doc.item_name);
    const productLine = getProductLine(productFamily, frm.doc.item_code, frm.doc.item_name);

    if (frm.fields_dict.product_family) {
        frm.set_value("product_family", productFamily);
    }
    if (frm.fields_dict.product_line) {
        frm.set_value("product_line", productLine);
    }
    if (frm.fields_dict.product_variant) {
        frm.set_value("product_variant", getProductVariant(productLine, frm.doc.item_code, frm.doc.item_name));
    }
}

function applyLearnedItemDefaults(frm) {
    if (!frm.is_new() || !LEARNED_DEFAULT_ITEM_GROUPS.includes(frm.doc.item_group)) {
        return Promise.resolve({});
    }

    return new Promise(function (resolve, reject) {
        frappe.call({
            method: "amf.amf.utils.item_learned_defaults.get_new_item_learned_defaults",
            args: {
                item_code: frm.doc.item_code,
                item_name: frm.doc.item_name,
                item_group: frm.doc.item_group,
                item_type: frm.doc.item_type,
                reference_code: frm.doc.reference_code,
            },
            callback: function (r) {
                if (r.exc) {
                    reject();
                    return;
                }

                const defaults = r.message || {};
                const updates = [];
                [
                    "description",
                    "weight_per_unit",
                    "weight_uom",
                    "has_batch_no",
                    "customs_tariff_number",
                ].forEach(function (fieldname) {
                    if (frm.fields_dict[fieldname]
                        && Object.prototype.hasOwnProperty.call(defaults, fieldname)
                        && frm.doc[fieldname] !== defaults[fieldname]) {
                        updates.push(frm.set_value(fieldname, defaults[fieldname]));
                    }
                });
                Promise.all(updates)
                    .then(function () {
                        resolve(defaults);
                    })
                    .catch(reject);
            },
            error: reject,
        });
    });
}

function fillLearnedItemDefaultsFromButton(frm) {
    if (!LEARNED_DEFAULT_ITEM_GROUPS.includes(frm.doc.item_group)) {
        frappe.msgprint(__("Select Plug, Valve Seat, Valve Head, or Product as the Item Group first."));
        return;
    }
    if (!frm.doc.item_code || !frm.doc.item_name) {
        frappe.msgprint(__("Set the Item Code and Item Name before filling the learned fields."));
        return;
    }

    prepareSubAssemblyIdentifiers(frm)
        .then(function () {
            return applyLearnedItemDefaults(frm);
        })
        .then(function (defaults) {
            updateTagRawMatRequirement(frm);
            frappe.msgprint({
                title: __("Learned Item Fields Applied"),
                indicator: "green",
                message: [
                    __("Description: updated"),
                    __("Weight: {0} {1}", [
                        frappe.utils.escape_html(String(defaults.weight_per_unit || 0)),
                        frappe.utils.escape_html(defaults.weight_uom || ""),
                    ]),
                    __("Customs Tariff Number: {0}", [
                        frappe.utils.escape_html(defaults.customs_tariff_number || ""),
                    ]),
                    __("Batch Tracking: {0}", [defaults.has_batch_no ? __("Enabled") : __("Disabled")]),
                ].join("<br>"),
            });
        })
        .catch(function () {
            // Frappe displays the server-side error message.
        });
}

function applyBomManagedSuggestion(frm, suggestion) {
    const itemType = suggestion.item_group === "Valve Head"
        ? "Sub-Assembly"
        : suggestion.item_type;

    frm.set_value("item_group", suggestion.item_group);
    if (frm.fields_dict.item_type) {
        frm.set_value("item_type", itemType);
    }
    frm.set_value("item_code", suggestion.item_code);
    applyBomManagedDefaults(frm, suggestion.item_group);
    updateTagRawMatRequirement(frm);
    updateItemReportingFields(frm);
}

function canCreateItemBom(itemGroup) {
    return BOM_CREATION_ITEM_GROUPS.includes(itemGroup);
}

function isSubAssemblyItemCode(itemCode) {
    const prefix = (itemCode || "").slice(0, 2);
    return ["11", "21"].includes(prefix);
}

function prepareSubAssemblyIdentifiers(frm) {
    if (!isSubAssemblyItemCode(frm.doc.item_code)) {
        return Promise.resolve();
    }

    const updates = [];
    const referenceCode = (frm.doc.reference_code || "").trim();
    if (frm.fields_dict.reference_code
        && referenceCode
        && !referenceCode.toUpperCase().endsWith(".ASM")) {
        updates.push(frm.set_value("reference_code", referenceCode + ".ASM"));
    }

    if (frm.fields_dict.reference_name && frm.doc.item_name) {
        const referenceName = frm.doc.item_code + ": " + frm.doc.item_name;
        if (frm.doc.reference_name !== referenceName) {
            updates.push(frm.set_value("reference_name", referenceName));
        }
    }

    return Promise.all(updates);
}

function fetchBomCreationPlan(frm) {
    return new Promise(function (resolve, reject) {
        frappe.call({
            method: "amf.amf.utils.item_bom_creation.get_bom_creation_plan",
            args: {
                item_code: frm.doc.item_code,
                item_group: frm.doc.item_group,
                tag_raw_mat: frm.doc.tag_raw_mat,
                item_name: frm.doc.item_name,
                raw_material: frm.__bom_raw_material || "",
                accessory_item: frm.__bom_accessory_item || "",
                accessory_qty: frm.__bom_accessory_qty || "",
            },
            callback: function (r) {
                if (r.exc || !r.message) {
                    reject();
                    return;
                }
                resolve(r.message);
            },
            error: reject,
        });
    });
}

function showBomCreationPlan(frm) {
    if (!frm.__create_bom_after_save) {
        return Promise.resolve();
    }

    return prepareSubAssemblyIdentifiers(frm)
        .then(function () {
            return fetchBomCreationPlan(frm);
        })
        .then(function (plan) {
            return new Promise(function (resolve) {
                const candidates = plan.raw_material_candidates || [];
                const candidateNames = candidates.map(function (candidate) {
                    return candidate.name;
                });
                const candidateList = candidates.map(function (candidate) {
                    return frappe.utils.escape_html(
                        candidate.name + ": " + (candidate.item_name || "")
                    );
                }).join("<br>");
                let confirmed = false;

                const dialog = new frappe.ui.Dialog({
                    title: __("Confirm BOM Creation"),
                    fields: [
                        {
                            fieldtype: "HTML",
                            options: plan.is_sub_assembly
                                ? __("Creation order: component Item {0}, its raw-material BOM, then the sub-assembly BOM for {1}.", [
                                    frappe.utils.escape_html(plan.component_item_code),
                                    frappe.utils.escape_html(plan.item_code),
                                ])
                                : __("A raw-material BOM will be created for component Item {0}.", [
                                    frappe.utils.escape_html(plan.component_item_code),
                                ]),
                        },
                        {
                            fieldtype: "Section Break",
                            label: __("Base Layer"),
                        },
                        {
                            fieldtype: "Data",
                            fieldname: "component_item_code",
                            label: __("Component Item"),
                            default: plan.component_item_code,
                            read_only: 1,
                        },
                        {
                            fieldtype: "Data",
                            fieldname: "component_status",
                            label: __("Component Status"),
                            default: plan.component_item_exists ? __("Existing") : __("Will be created"),
                            read_only: 1,
                        },
                        {
                            fieldtype: "Data",
                            fieldname: "item_group",
                            label: __("Item Group"),
                            default: plan.item_group,
                            read_only: 1,
                        },
                        {
                            fieldtype: "Column Break",
                        },
                        {
                            fieldtype: "Data",
                            fieldname: "component_bom",
                            label: __("Component BOM"),
                            default: plan.component_bom || __("Will be created"),
                            read_only: 1,
                        },
                        {
                            fieldtype: "Float",
                            fieldname: "raw_material_qty",
                            label: __("Raw Material Quantity"),
                            default: plan.raw_material_qty,
                            read_only: 1,
                        },
                        {
                            fieldtype: "Section Break",
                            label: __("Raw Material"),
                        },
                        {
                            fieldtype: "Data",
                            fieldname: "tag_raw_mat",
                            label: __("Raw Material Tag"),
                            default: plan.tag_raw_mat,
                            read_only: 1,
                        },
                        {
                            fieldtype: "Link",
                            fieldname: "raw_material",
                            label: __("Raw Material Item"),
                            options: "Item",
                            default: plan.raw_material,
                            reqd: 1,
                            get_query: function () {
                                return {
                                    filters: [["Item", "name", "in", candidateNames]],
                                };
                            },
                        },
                        {
                            fieldtype: "HTML",
                            options: candidateList,
                        },
                        {
                            fieldtype: "Section Break",
                            label: __("Upper Layer"),
                            hidden: plan.is_sub_assembly ? 0 : 1,
                        },
                        {
                            fieldtype: "Data",
                            fieldname: "upper_item_code",
                            label: __("Sub-Assembly Item"),
                            default: plan.item_code,
                            read_only: 1,
                            hidden: plan.is_sub_assembly ? 0 : 1,
                        },
                        {
                            fieldtype: "Data",
                            fieldname: "upper_bom",
                            label: __("Sub-Assembly BOM"),
                            default: plan.upper_bom || __("Will be created"),
                            read_only: 1,
                            hidden: plan.is_sub_assembly ? 0 : 1,
                        },
                        {
                            fieldtype: "Link",
                            fieldname: "accessory_item",
                            label: __("Accessory Item"),
                            options: "Item",
                            default: plan.accessory_item,
                            reqd: plan.is_sub_assembly ? 1 : 0,
                            hidden: plan.is_sub_assembly ? 0 : 1,
                            get_query: function () {
                                return {
                                    filters: {disabled: 0},
                                };
                            },
                        },
                        {
                            fieldtype: "Column Break",
                            hidden: plan.is_sub_assembly ? 0 : 1,
                        },
                        {
                            fieldtype: "Float",
                            fieldname: "component_qty",
                            label: __("Component Quantity"),
                            default: plan.component_qty,
                            read_only: 1,
                            hidden: plan.is_sub_assembly ? 0 : 1,
                        },
                        {
                            fieldtype: "Float",
                            fieldname: "accessory_qty",
                            label: __("Accessory Quantity"),
                            default: plan.accessory_qty,
                            reqd: plan.is_sub_assembly ? 1 : 0,
                            hidden: plan.is_sub_assembly ? 0 : 1,
                        },
                    ],
                    primary_action_label: __("Continue and Save"),
                    primary_action: function (values) {
                        if (plan.is_sub_assembly && Number(values.accessory_qty) <= 0) {
                            frappe.msgprint(__("Accessory Quantity must be greater than zero."));
                            return;
                        }

                        frm.__bom_raw_material = values.raw_material;
                        frm.__bom_accessory_item = plan.is_sub_assembly ? values.accessory_item : "";
                        frm.__bom_accessory_qty = plan.is_sub_assembly ? values.accessory_qty : "";
                        confirmed = true;
                        dialog.hide();
                        resolve();
                    },
                    secondary_action_label: __("Cancel Save"),
                    onhide: function () {
                        if (!confirmed) {
                            frappe.validated = false;
                            resolve();
                        }
                    },
                });

                dialog.show();
            });
        });
}

function createRequestedBomsAfterSave(frm) {
    if (!frm.__create_bom_after_save || frm.__creating_requested_boms) {
        return;
    }

    frm.__creating_requested_boms = true;
    frappe.call({
        method: "amf.amf.utils.item_bom_creation.create_item_boms_after_save",
        args: {
            item_code: frm.doc.item_code,
            raw_material: frm.__bom_raw_material,
            accessory_item: frm.__bom_accessory_item || "",
            accessory_qty: frm.__bom_accessory_qty || "",
        },
        freeze: true,
        freeze_message: __("Creating Item BOM layers..."),
        callback: function (r) {
            if (r.exc || !r.message) {
                frm.__creating_requested_boms = false;
                return;
            }

            const result = r.message;
            const message = result.layer === "sub_assembly"
                ? __("Component Item {0}, component BOM {1}, and sub-assembly BOM {2} are ready.", [
                    result.component_item,
                    result.component_bom,
                    result.upper_bom,
                ])
                : __("Component BOM {0} is ready.", [result.component_bom]);

            frm.__create_bom_after_save = false;
            frm.__creating_requested_boms = false;
            frm.__bom_raw_material = "";
            frm.__bom_accessory_item = "";
            frm.__bom_accessory_qty = "";
            frappe.show_alert({message: message, indicator: "green"});
            frm.reload_doc();
        },
        error: function () {
            frm.__creating_requested_boms = false;
        },
    });
}

function updateBomManagedDialog(dialog) {
    const itemGroup = dialog.get_value("item_group");
    const showHasBom = itemGroup !== "Valve Head";
    const showCreateBom = canCreateItemBom(itemGroup);
    const showTagRawMat = canCreateItemBom(itemGroup);

    if (dialog.get_field("has_bom").df.hidden !== (showHasBom ? 0 : 1)) {
        dialog.set_df_property("has_bom", "hidden", showHasBom ? 0 : 1);
    }
    if (dialog.get_field("create_bom_after_save").df.hidden !== (showCreateBom ? 0 : 1)) {
        dialog.set_df_property("create_bom_after_save", "hidden", showCreateBom ? 0 : 1);
    }
    if (dialog.get_field("tag_raw_mat").df.hidden !== (showTagRawMat ? 0 : 1)) {
        dialog.set_df_property("tag_raw_mat", "hidden", showTagRawMat ? 0 : 1);
    }
    if (dialog.get_field("tag_raw_mat").df.reqd !== (showTagRawMat ? 1 : 0)) {
        dialog.set_df_property("tag_raw_mat", "reqd", showTagRawMat ? 1 : 0);
    }
    if (!showCreateBom && dialog.get_value("create_bom_after_save")) {
        dialog.set_value("create_bom_after_save", 0);
    }
    if (!showTagRawMat && dialog.get_value("tag_raw_mat")) {
        dialog.set_value("tag_raw_mat", "");
    }
}

function showBomManagedItemDialog(frm) {
    let suggestionRequest = 0;
    const tagRawMatDf = frm.fields_dict.tag_raw_mat
        ? frm.fields_dict.tag_raw_mat.df
        : {};
    const dialog = new frappe.ui.Dialog({
        title: __("New BOM Item"),
        fields: [
            {
                fieldtype: "Select",
                fieldname: "item_group",
                label: __("Item Family"),
                options: BOM_MANAGED_ITEM_GROUPS.join("\n"),
                default: getDefaultBomManagedItemGroup(frm),
                reqd: 1,
                change: function () {
                    updateBomManagedDialog(dialog);
                    refreshSuggestion();
                },
            },
            {
                fieldtype: "Check",
                fieldname: "has_bom",
                label: __("Is a sub-assembly"),
                default: getDefaultHasBom(frm, getDefaultBomManagedItemGroup(frm)),
                change: function () {
                    refreshSuggestion();
                },
            },
            {
                fieldtype: "Check",
                fieldname: "create_bom_after_save",
                label: __("Create BOM after saving"),
                description: __("Creates the base BOM and, for a sub-assembly, the upper BOM too."),
                default: frm.__create_bom_after_save ? 1 : 0,
            },
            {
                fieldtype: tagRawMatDf.fieldtype || "Data",
                fieldname: "tag_raw_mat",
                label: tagRawMatDf.label || __("Raw Material Tag"),
                options: tagRawMatDf.options || "",
                default: frm.doc.tag_raw_mat || "",
                description: __("Used to filter the raw materials proposed for the BOM."),
            },
            {
                fieldtype: "Data",
                fieldname: "family_suffix",
                label: __("Shared Last 4 Digits"),
                read_only: 1,
            },
            {
                fieldtype: "Data",
                fieldname: "item_code",
                label: __("Suggested Item Code"),
                read_only: 1,
            },
            {
                fieldtype: "Small Text",
                fieldname: "reserved_codes",
                label: __("Reserved Family Codes"),
                read_only: 1,
            },
        ],
        primary_action_label: __("Use Suggestion"),
        primary_action: function () {
            if (!dialog.__suggestion) {
                frappe.msgprint(__("Please wait until the item code suggestion is loaded."));
                return;
            }

            frm.__create_bom_after_save = canCreateItemBom(dialog.__suggestion.item_group)
                && Boolean(dialog.get_value("create_bom_after_save"));
            frm.__bom_raw_material = "";
            frm.__bom_accessory_item = "";
            frm.__bom_accessory_qty = "";
            applyBomManagedSuggestion(frm, dialog.__suggestion);
            frm.set_value(
                "tag_raw_mat",
                canCreateItemBom(dialog.__suggestion.item_group)
                    ? dialog.get_value("tag_raw_mat")
                    : ""
            );
            dialog.hide();
        },
    });

    const refreshSuggestion = function () {
        const itemGroup = dialog.get_value("item_group");
        const hasBom = itemGroup === "Valve Head" ? 1 : dialog.get_value("has_bom");
        const requestNumber = ++suggestionRequest;

        dialog.__suggestion = null;
        dialog.get_primary_btn().prop("disabled", true);
        fetchBomManagedItemSuggestion(itemGroup, hasBom, function (suggestion) {
            if (requestNumber !== suggestionRequest) {
                return;
            }
            dialog.__suggestion = suggestion;
            dialog.set_value("family_suffix", suggestion.family_suffix);
            dialog.set_value("item_code", suggestion.item_code);
            dialog.set_value("reserved_codes", (suggestion.reserved_codes || []).join(" / "));
            dialog.get_primary_btn().prop("disabled", false);
        });
    };

    dialog.show();
    updateBomManagedDialog(dialog);
    refreshSuggestion();
}

frappe.ui.form.on("Item", {
    refresh: function (frm) {
        updateTagRawMatRequirement(frm);
        if (frm.is_new()) {
            updateItemReportingFields(frm);
        }

        if (!frm.is_new()) {
            return;
        }

        frm.add_custom_button(__("Suggest BOM Code"), function () {
            showBomManagedItemDialog(frm);
        });
        frm.add_custom_button(__("Fill Learned Fields"), function () {
            fillLearnedItemDefaultsFromButton(frm);
        });

        if (!frm.__bom_managed_dialog_shown && !frm.doc.item_code) {
            frm.__bom_managed_dialog_shown = true;
            setTimeout(function () {
                showBomManagedItemDialog(frm);
            }, 150);
        }
    },

    item_code: function (frm) {
        updateTagRawMatRequirement(frm);
        updateItemReportingFields(frm);
    },

    item_group: function (frm) {
        if (!canCreateItemBom(frm.doc.item_group)) {
            frm.__create_bom_after_save = false;
            frm.__bom_raw_material = "";
            frm.__bom_accessory_item = "";
            frm.__bom_accessory_qty = "";
        }
        updateTagRawMatRequirement(frm);
    },

    tag_raw_mat: function (frm) {
        frm.__bom_raw_material = "";
    },

    item_name: function (frm) {
        updateItemReportingFields(frm);
        frm.__bom_accessory_qty = "";
    },

    before_save: function (frm) {
        return showBomCreationPlan(frm);
    },

    after_save: function (frm) {
        createRequestedBomsAfterSave(frm);
    },
});
