// Copyright (c) 2024, libracore AG and contributors
// For license information, please see license.txt

frappe.ui.form.on('Planning', {
    refresh: function (frm) {
        set_item_queries(frm);
        if (frm.doc.docstatus === 1) {
            frm.add_custom_button(__('<i class="fa fa-print"></i>&nbsp;&nbsp;•&nbsp;&nbsp;Sticker'), function () {
                printSticker(frm)
            });
        }
    },

    onload(frm) {
        // Only set defaults if this is a brand new document (not saved yet)
        if (frm.is_new()) {
            if (frm.doc.amended_from) {
                frm.trigger('item_code'); 
            }
            set_default_values(frm);
            fetch_suivi_usinage(frm);
        }
    },

    on_submit: function (frm) {
        createWorkOrder(frm);
    },

    after_submit: function (frm) {
        
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

    // Trigger batch fetch when the user picks a matiere
    matiere: function(frm) {
        frm.set_value('batch_matiere', '')
        frm.refresh_field('batch_matiere');
        if (frm.doc.matiere) {
            // frm.doc.matiere now holds the raw material's "name" (internal code),
            // so we can fetch enabled batches
            frm.set_query("batch_matiere", function() {
                return {
                    filters: {
                        "item": frm.doc.matiere,  // or whichever field you want to match
                        "disabled": 0
                    }
                };
            });
        }
    },

    suivi_usinage: function (frm) {
        frm.set_value('name_id', frm.doc.suivi_usinage);
    },
});

/**
 * Sets default values for a new Planning form.
 * @param {FrappeForm} frm - The form object.
 */
function set_default_values(frm) {
    frm.set_value("date_de_fin", frappe.datetime.now_datetime());
    frm.set_value("responsable", frappe.session.user);
    frm.set_value("entreprise", "Advanced Microfluidics SA");
    
    // Set all these fields to null or empty as needed
    
    const fieldsToClear = ["stock_entry", "batch", "item_code", "item_name", "batch_matiere", "matiere", "dimension_matiere"];
    const fieldsToClear_ = ["work_order"];
    if (!frm.doc.amended_from)
        fieldsToClear.forEach(field => frm.set_value(field, null));
    fieldsToClear_.forEach(field => frm.set_value(field, null));
}

/**
 * Fetches the next 'suivi_usinage' from the server and sets it on the form.
 * @param {FrappeForm} frm - The form object.
 */
function fetch_suivi_usinage(frm) {
    frappe.call({
        method: "amf.amf.doctype.planning.planning.get_next_suivi_usinage"
    })
    .then(r => {
        if (r && r.message) {
            frm.set_value("suivi_usinage", r.message);
        }
    })
    .catch(err => {
        frappe.msgprint({
            title: __("Server Error"),
            message: __("Unable to fetch the next 'suivi_usinage'. Please try again later."),
            indicator: "red"
        });
        console.error("Error fetching suivi_usinage:", err);
    });
}

function printSticker(frm) {
    const print_format = "Sticker_USI";
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
}

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
    frm.set_df_property('matiere', 'options', '');
    frm.set_value('batch_matiere', '')
    frm.refresh_field('matiere');
    frm.refresh_field('batch_matiere');
    // Fetch the raw materials associated with the item_code
    frappe.call({
        method: 'amf.amf.doctype.planning.planning.get_rawmat_items_',
        args: { 'item_code': frm.doc.item_code },
        callback: function (response) {
            if (response.message && response.message.items) {
                console.log(response.message.items)
                // Clear the current options of the 'matiere' field
                // Build array of label/value pairs
                const rawMaterialOptions = response.message.items.map(item => {
                    return {
                        label: item.item_name,  // what user sees
                        value: item.name        // stored in frm.doc.matiere
                    }
                });

                // Make sure 'matiere' is a Select-type field
                frm.set_df_property('matiere', 'options', rawMaterialOptions);
                frm.refresh_field('matiere');

                
                // frm.set_df_property('matiere', 'options', response.message.items.join('\n'));
                // frm.refresh_field('matiere');
            }
        }
    });
}

function createWorkOrder(frm) {
    frappe.call({
        method: 'amf.amf.doctype.planning.planning.create_work_order',
        args: {
            'form_data': frm.doc,
            'wo': frm.doc.work_order,
        },
        freeze: true,  // Freeze the UI during the call
        freeze_message: __("Création de l'ordre de fabrication en cours...<br>Mise à jour des entrées de stock...<br>Merci de patienter..."),
        callback: function (response) {
            console.log(response);
            if (response && response.message.success) {
                // Set the values returned from the response
                frm.set_value('work_order', response.message.work_order);
                frm.set_value('stock_entry', response.message.stock_entry);
                frm.set_value('batch', response.message.batch);
                frm.set_df_property(frm.doc.work_order, "read_only", 1);
                frappe.msgprint({
                    title: __('Planning confirmé'),
                    indicator: 'green',
                    message: __('Ordre de Fabrication crée avec succès.')
                });
                frm.save('Update');
                frappe.show_alert( __("Fichier mis à jour") );

                frappe.set_route("Form", "Work Order", frm.doc.work_order);
            } else {
                // Error handling
                frappe.validated = false;
                console.error('Failed to create work order');
                alert('Failed to create work order. Error: ' + (response.message ? response.message : 'Unknown error'));
            }
        }
    });
}