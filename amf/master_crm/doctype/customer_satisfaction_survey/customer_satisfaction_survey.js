// Copyright (c) 2025, libracore AG and contributors
// For license information, please see license.txt

frappe.ui.form.on('Customer Satisfaction Survey', {
    refresh: function (frm) {
        set_item_queries(frm)
        _reset_ratings(frm)
    },
    before_submit: function (frm) {
        if (frm.doc.contact_name && frm.doc.organization_name) {
            frm.set_value("title", frm.doc.contact_name + " for " + frm.doc.organization_name);
        }
    },
    contact_person: function (frm) {
        if (!frm.doc.contact_person) {
            frm.set_value("contact_name", "");
        }
    },
    customer: function (frm) {
        if (!frm.doc.customer) {
            frm.set_value("organization_name", "");
        }
    },
});

function set_item_queries(frm) {
    frm.set_query("contact_person", () => ({
        filters: [
            ['Contact', 'company_name', 'Like', frm.doc.organization_name],
        ],
    }));
}

function _reset_ratings(frm) {
    // add our reset button
    frm.add_custom_button(__('Reset Ratings'), () => {
        // 1) Grab all Rating fields and build maps
        const ratingFields = frappe.meta
            .get_docfields(frm.doc.doctype)
            .filter(df => df.fieldtype === 'Rating')
            .map(df => ({ fieldname: df.fieldname, label: df.label }));

        if (!ratingFields.length) {
            frappe.msgprint(__('No Rating fields found.'));
            return;
        }

        // map label → fieldname
        const labelToField = {};
        ratingFields.forEach(r => {
            labelToField[r.label] = r.fieldname;
        });

        // only labels in the dropdown
        const labelsList = ratingFields.map(r => r.label).join('\n');

        // 2) Build the dialog
        const dialog = new frappe.ui.Dialog({
            title: __('Reset Rating Fields'),
            fields: [
                {
                    fieldtype: 'Select',
                    fieldname: 'mode',
                    label: __('Which ratings to reset?'),
                    options: 'All\nSelected',
                    default: 'All',
                    reqd: 1
                },
                {
                    fieldtype: 'MultiSelect',
                    fieldname: 'fields_to_reset',
                    label: __('Fields to Reset'),
                    options: labelsList,
                    hidden: true
                }
            ],
            primary_action_label: __('Reset'),
            primary_action() {
                const values = this.get_values();
                if (!values) return;

                // 3) Decide which fieldnames to reset
                let to_reset = [];
                if (values.mode === 'All') {
                    to_reset = ratingFields.map(r => r.fieldname);
                } else {
                    const selectedLabels = Array.isArray(values.fields_to_reset)
                        ? values.fields_to_reset
                        : (values.fields_to_reset || '')
                            .split(',')
                            .map(s => s.trim())
                            .filter(Boolean);

                    to_reset = selectedLabels
                        .map(label => labelToField[label])
                        .filter(fn => !!fn);
                }

                // 4) Clear them
                to_reset.forEach(fn => {
                    frm.set_value(fn, null);
                    frm.refresh_field(fn);
                });

                frm.dirty();
                this.hide();
            }
        });

        dialog.show();

        // 5) Show/hide the multiselect when mode changes
        dialog.fields_dict.mode.$input.on('change', () => {
            const mode = dialog.get_value('mode');
            dialog.set_df_property(
                'fields_to_reset',
                'hidden',
                mode === 'All'
            );
        });
    });
}
