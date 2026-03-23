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

function applyBomManagedSuggestion(frm, suggestion) {
    const itemType = suggestion.item_group === "Valve Head"
        ? "Sub-Assembly"
        : suggestion.item_type;

    frm.set_value("item_group", suggestion.item_group);
    if (frm.fields_dict.item_type) {
        frm.set_value("item_type", itemType);
    }
    frm.set_value("item_code", suggestion.item_code);
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
});
