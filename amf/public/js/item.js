const BOM_MANAGED_ITEM_GROUPS = ["Plug", "Valve Seat", "Valve Head"];

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
        frm.set_value("customs_tariff_number", "8481 80 90 05");
    } else {
        frm.set_value("is_sales_item", 0);
        frm.set_value("sales_uom", "");
        frm.set_value("customs_tariff_number", "");
    }
}

function shouldRequireTagRawMat(itemCode) {
    return (itemCode || "").startsWith("10") || (itemCode || "").startsWith("20");
}

function updateTagRawMatRequirement(frm) {
    if (!frm.fields_dict.tag_raw_mat) {
        return;
    }

    frm.set_df_property("tag_raw_mat", "reqd", shouldRequireTagRawMat(frm.doc.item_code) ? 1 : 0);
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
}

function updateBomManagedDialog(dialog) {
    const itemGroup = dialog.get_value("item_group");
    const showHasBom = itemGroup !== "Valve Head";

    dialog.set_df_property("has_bom", "hidden", showHasBom ? 0 : 1);
    if (!showHasBom) {
        dialog.set_value("has_bom", 1);
    }
}

function showBomManagedItemDialog(frm) {
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
            },
            {
                fieldtype: "Check",
                fieldname: "has_bom",
                label: __("Is a sub-assembly"),
                default: getDefaultHasBom(frm, getDefaultBomManagedItemGroup(frm)),
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

            applyBomManagedSuggestion(frm, dialog.__suggestion);
            dialog.hide();
        },
    });

    const refreshSuggestion = function () {
        const itemGroup = dialog.get_value("item_group");
        const hasBom = itemGroup === "Valve Head" ? 1 : dialog.get_value("has_bom");

        dialog.get_primary_btn().prop("disabled", true);
        fetchBomManagedItemSuggestion(itemGroup, hasBom, function (suggestion) {
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

    dialog.get_field("item_group").$input.on("change", function () {
        updateBomManagedDialog(dialog);
        refreshSuggestion();
    });

    dialog.get_field("has_bom").$input.on("change", refreshSuggestion);
}

frappe.ui.form.on("Item", {
    refresh: function (frm) {
        updateTagRawMatRequirement(frm);

        if (!frm.is_new()) {
            return;
        }

        frm.add_custom_button(__("Suggest BOM Code"), function () {
            showBomManagedItemDialog(frm);
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
    },
});
