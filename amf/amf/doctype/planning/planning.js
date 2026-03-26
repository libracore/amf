// Copyright (c) 2024, libracore AG and contributors
// For license information, please see license.txt

frappe.ui.form.on('Planning', {
    refresh: function (frm) {
        set_item_queries(frm);
        ensurePlanningRawMaterialCostingLoaded(frm);
        // syncCostingTable(frm);
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

        ensurePlanningRawMaterialCostingLoaded(frm);
        // syncCostingTable(frm);
    },

    on_submit: function (frm) {
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

    // Trigger batch fetch when the user picks a matiere
    matiere: function (frm) {
        frm.set_value('batch_matiere', '');
        frm.refresh_field('batch_matiere');
        if (frm.doc.matiere) {
            // frm.doc.matiere now holds the raw material's "name" (internal code),
            // so we can fetch enabled batches
            frm.set_query("batch_matiere", function () {
                return {
                    filters: {
                        "item": frm.doc.matiere,  // or whichever field you want to match
                        "disabled": 0
                    }
                };
            });
        }
    },
    batch_matiere: function (frm) {
        frm.set_value('available_qty', 0);
        frm.refresh_field('available_qty');

        if (!frm.doc.batch_matiere) {
            frm._planning_raw_material_costing = null;
            if (frm.doc.batch) {
                // syncCostingTable(frm);
            }
            return;
        }

        frappe.call({
            method: "amf.amf.utils.batch.get_batch_quantity_in_warehouse",
            args: {
                batch_no: frm.doc.batch_matiere,
                warehouse: "Main Stock - AMF21"
            },
            callback: function (r) {
                if (r.message) {
                    frm.set_value('available_qty', r.message);
                    frm.refresh_field('available_qty');
                }
            }
        });

        fetchPlanningRawMaterialCosting(frm);
    },

    suivi_usinage: function (frm) {
        frm.set_value('name_id', frm.doc.suivi_usinage);
    },

    batch: function (frm) {
        // The costing row should only start existing once the finished batch is known.
        // As soon as the batch is filled, rebuild the single computed child-table row.
        // syncCostingTable(frm);
    },

    // quantite_validee: function (frm) {
    //     syncCostingTable(frm);
    // },

    // quantite_scrap: function (frm) {
    //     syncCostingTable(frm);
    // },

    // temps_de_cycle_min: function (frm) {
    //     syncCostingTable(frm);
    // },

    // temps_de_programmation_hr: function (frm) {
    //     syncCostingTable(frm);
    // },

    // temps_de_reglage_hr: function (frm) {
    //     syncCostingTable(frm);
    // },

    // used_qty: function (frm) {
    //     syncCostingTable(frm);
    // },
});

const PLANNING_COSTING_HOURLY_RATE = 75;
const MINUTES_PER_HOUR = 60;
function hasPlanningCostingInputs(doc) {
    // Mirror the server rule: the costing table should not exist before the
    // finished batch is assigned on the Planning document.
    return !!doc.batch;
}

function ensurePlanningRawMaterialCostingLoaded(frm) {
    if (!frm.doc.batch_matiere) {
        frm._planning_raw_material_costing = null;
        return;
    }

    if (
        frm._planning_raw_material_costing
        && frm._planning_raw_material_costing.batch_matiere === frm.doc.batch_matiere
    ) {
        return;
    }

    fetchPlanningRawMaterialCosting(frm);
}

function fetchPlanningRawMaterialCosting(frm) {
    if (!frm.doc.batch_matiere) {
        frm._planning_raw_material_costing = null;
        if (frm.doc.batch) {
            syncCostingTable(frm);
        }
        return;
    }

    const requestedBatch = frm.doc.batch_matiere;
    frappe.call({
        method: 'amf.amf.doctype.planning.planning.get_planning_raw_material_costing',
        args: {
            batch_matiere: requestedBatch,
            used_qty: frm.doc.used_qty,
        },
        callback: function (r) {
            if (frm.doc.batch_matiere !== requestedBatch) {
                return;
            }

            frm._planning_raw_material_costing = Object.assign(
                { batch_matiere: requestedBatch },
                r.message || {}
            );

            if (frm.doc.batch) {
                syncCostingTable(frm);
            }
        }
    });
}

function getPlanningRawMaterialCostingFromCache(frm) {
    const cachedCostPerMeter = flt(
        frm._planning_raw_material_costing && frm._planning_raw_material_costing.raw_material_cost_per_meter
    );

    return {
        raw_material_prec: (frm._planning_raw_material_costing && frm._planning_raw_material_costing.raw_material_prec) || '',
        raw_material_cost_per_meter: cachedCostPerMeter,
        raw_material_cost: flt(cachedCostPerMeter * flt(frm.doc.used_qty), 2),
    };
}

function syncCostingTable(frm) {
    if (!frm.fields_dict.costing) {
        return;
    }

    // Keep the child table strictly computed from the parent document.
    // We always rebuild the table from scratch so there is only one reliable row.
    frm.clear_table('costing');

    if (!hasPlanningCostingInputs(frm.doc)) {
        frm.refresh_field('costing');
        return;
    }

    const processCost = calculatePlanningCost(frm.doc);
    const rawMaterialCosting = getPlanningRawMaterialCostingFromCache(frm);
    const totalCost = calculatePlanningTotalCost(processCost, rawMaterialCosting.raw_material_cost);

    frm.add_child('costing', {
        batch_no: frm.doc.batch || '',
        raw_material_prec: rawMaterialCosting.raw_material_prec,
        raw_material_cost_per_meter: rawMaterialCosting.raw_material_cost_per_meter,
        raw_material_cost: rawMaterialCosting.raw_material_cost,
        total_cost: totalCost,
        cost_per_part: calculatePlanningCostPerPart(frm.doc, totalCost),
    });

    frm.refresh_field('costing');
}

function calculatePlanningCost(doc) {
    // Step 1:
    // Count every processed part, including scrap.
    // Scrap pieces still consumed machine time, so they must be included in the process cost.
    const totalProcessedQty = flt(doc.quantite_validee) + flt(doc.quantite_scrap);

    // Step 2:
    // Convert the repetitive production effort into cost.
    // - `temps_de_cycle_min` is stored in minutes per piece
    // - multiplying by the processed quantity gives total production minutes
    // - multiplying by 75 applies the hourly machine/shop rate
    // - dividing by 60 converts minutes into hours before pricing them
    const cycleCost =
        (totalProcessedQty * flt(doc.temps_de_cycle_min) * PLANNING_COSTING_HOURLY_RATE) / MINUTES_PER_HOUR;

    // Step 3:
    // Setup and programming are fixed preparation activities.
    // They are already stored in hours, so we simply add them together
    // and multiply once by the same hourly rate.
    const fixedPreparationHours = flt(doc.temps_de_reglage_hr) + flt(doc.temps_de_programmation_hr);
    const fixedPreparationCost = fixedPreparationHours * PLANNING_COSTING_HOURLY_RATE;

    // Step 4:
    // The process cost is the sum of:
    // - the variable cycle-based production cost
    // - the fixed setup + programming cost
    return flt(cycleCost + fixedPreparationCost, 2);
}

function calculatePlanningTotalCost(processCost, rawMaterialCost) {
    // Step 5:
    // Add the raw material consumption cost to the machining/setup cost
    // to get the final total production cost.
    return flt(flt(processCost) + flt(rawMaterialCost), 2);
}

function calculatePlanningCostPerPart(doc, totalCost) {
    // Step 6:
    // Spread the full production cost across the validated pieces only.
    // This makes scrap cost visible inside the finished part cost.
    const validatedQty = flt(doc.quantite_validee);
    if (validatedQty <= 0) {
        return 0;
    }

    return flt(flt(totalCost) / validatedQty, 2);
}

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
        method: "amf.amf.doctype.planning.planning.get_next_suivi_usinage",
        callback: function (r) {
            if (r && r.message) {
                frm.set_value("suivi_usinage", r.message);
            }
        },
        error: function (err) {
            frappe.msgprint({
                title: __("Server Error"),
                message: __("Unable to fetch the next 'suivi_usinage'. Please try again later."),
                indicator: "red"
            });
            console.error("Error fetching suivi_usinage:", err);
        }
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
                frm.reload_doc();
                frappe.msgprint({
                    title: __('Planning confirmé'),
                    indicator: 'green',
                    message: __('Ordre de Fabrication crée avec succès.')
                });
                frappe.show_alert(__("Fichier mis à jour"));

                if (response.message.work_order) {
                    frappe.set_route("Form", "Work Order", response.message.work_order);
                }
            } else {
                // Error handling
                frappe.validated = false;
                console.error('Failed to create work order');
                alert('Failed to create work order. Error: ' + (response.message ? response.message : 'Unknown error'));
            }
        }
    });
}
