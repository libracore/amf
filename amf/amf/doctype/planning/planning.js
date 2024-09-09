// Copyright (c) 2024, libracore AG and contributors
// For license information, please see license.txt

frappe.ui.form.on('Planning', {
    refresh: function (frm) {
        set_item_queries(frm);
        if (frm.doc.docstatus === 1) {
            frm.add_custom_button(__('<i class="fa fa-print"></i>&nbsp;&nbsp;•&nbsp;&nbsp;Sticker'), function () {
                const print_format = "Sticker USI";
                const label_format = "Labels 62x100mm";

                var w = window.open(
                    frappe.urllib.get_full_url(
                        "/api/method/amf.amf.utils.labels.download_label_for_doc"
                        + "?doctype=" + encodeURIComponent(frm.doc.doctype)
                        + "&docname=" + encodeURIComponent(frm.doc.name)
                        + "&print_format=" + encodeURIComponent(print_format)
                        + "&label_reference=" + encodeURIComponent(label_format)
                    ),
                    "_blank"
                );
                if (!w) {
                    frappe.msgprint(__("Please enable pop-ups")); return;
                }
            });
        }
    },

    onload: function (frm) {
        if (frm.doc.__islocal) {
            // Set the 'date_de_fin' field to the current date and time
            frm.set_value('date_de_fin', frappe.datetime.now_datetime());
            frm.set_value('responsable', frappe.session.user);
            frm.set_value('entreprise', 'Advanced Microfluidics SA');
            frm.set_value('work_order', null);
            frm.set_value('stock_entry', null);
            frm.set_value('batch', null);
        }
    },

    on_submit: function (frm) {
        if (!frm.doc.work_order)
            createWorkOrder(frm);
    },

    item_code: function (frm) {
        if (frm.doc.item_code) {
            // Fetch the item_name for the selected item_code
            frappe.db.get_value('Item', frm.doc.item_code, 'item_name', function (r) {
                if (r && r.item_name) {
                    frm.set_value('item_name', r.item_name);
                } else {
                    frm.set_value('item_name', null);
                }
            });
        }
        fetchMaterials(frm);
    },

    suivi_usinage: function (frm) {
        frm.set_value('name_id', frm.doc.suivi_usinage);
    },

});

function set_item_queries(frm) {
    frm.set_query("item_code", () => ({
        filters: [
            ['Item', 'item_code', 'Like', '_0%'],
            ['Item', 'disabled', '=', 'No'],
            ['Item', 'item_group', 'in', ['Plug', 'Valve Seat']],
        ],
    }));
}

function fetchMaterials(frm) {
    // Fetch the raw materials associated with the item_code
    frappe.call({
        method: 'amf.amf.doctype.planning.planning.get_rawmat_items',
        args: { 'item_code': frm.doc.item_code },
        callback: function (response) {
            if (response.message && response.message.items) {
                // Clear the current options of the 'matiere' field
                frm.set_df_property('matiere', 'options', '');
                frm.set_df_property('matiere', 'options', response.message.items.join('\n'));
                frm.set_df_property('matiere', 'read_only', 0)
                frm.refresh_field('matiere');
            }
        }
    });
}

function createWorkOrder(frm) {
    frappe.call({
        method: 'amf.amf.doctype.planning.planning.create_work_order',
        args: {
            'form_data': frm.doc
        },
        callback: function (response) {
            console.log(response);
            if (response && response.message.success) {
                // Set the values returned from the response
                frm.set_value('work_order', response.message.work_order);
                frm.set_value('stock_entry', response.message.stock_entry);
                frm.set_value('batch', response.message.batch);
                frappe.msgprint({
                    title: __('Planning confirmé'),
                    indicator: 'green',
                    message: __('Ordre de Fabrication crée avec succès.')
                });
                frm.save('Update');
            
            } else {
                // Error handling
                frappe.validated = false;
                console.error('Failed to create work order');
                alert('Failed to create work order. Error: ' + (response.message ? response.message : 'Unknown error'));

            }
        }
    });
}