// Copyright (c) 2024, libracore AG and contributors
// For license information, please see license.txt

frappe.ui.form.on('Item Creation', {

    /*
    onload: function(frm) {
        if (frm.is_new()) {
            frm.set_value('item_group', 'Product');
        }
    },
    */

    before_submit: async function (frm) {
        frappe.dom.freeze("Processing item creation, please wait...");
        try {
            if (frm.doc.plug_check)
                await createPlug(frm)
            if (frm.doc.seat_check)
                await createSeat(frm)
            
            if (frm.doc.head_check)
                await createHead(frm)

            if (frm.doc.rvm_check)
                await createRVM(frm)
            if (frm.doc.pump_check)
                await createPump(frm)
            if (frm.doc.pump_hv_check)
                await createPumpHV(frm)

            
        } catch (error) {
            // If any server call fails, the process stops and logs the error.
            console.error("Item creation failed:", error);
            frappe.throw("An error occurred during item creation. See console for details.");
        } finally {
            frappe.dom.unfreeze();
        }
    },

    refresh: function (frm) {
        frm.set_query("body", () => ({
            filters: [
                ['Item', 'item_group', '=', 'Body'],
                ['Item', 'has_serial_no', '=', '1'],
                ['Item', 'disabled', '=', 'No'],
            ],
        }));
        frm.set_query("head_item", () => ({
            filters: [
                ['Item', 'item_group', '=', 'Valve Head'],
                ['Item', 'item_code', 'like', '3_%'],
                ['Item', 'disabled', '=', 'No'],
            ],
        }));
        frm.set_query("seat_item", () => ({
            filters: [
                ['Item', 'item_group', '=', 'Valve Seat'],
                ['Item', 'item_code', 'like', '21_%'],
                ['Item', 'disabled', '=', 'No'],
            ],
        }));
        frm.set_query("plug_item", () => ({
            filters: [
                ['Item', 'item_group', '=', 'Plug'],
                ['Item', 'item_code', 'like', '11_%'],
                ['Item', 'disabled', '=', 'No'],
            ],
        }));
        frm.set_query("cap_type", () => ({
            filters: [
                ['Item', 'item_code', 'in', ['RVM.3038', 'RVM.3039', 'RVM.3040']]
            ],
        }));
        frm.set_query("screw_type", () => ({
            filters: [
                ['Item', 'item_group', '=', 'Part'],
                ['Item', 'item_name', 'like', 'Screw_%'],
                ['Item', 'disabled', '=', 'No'],
            ],
        }));
    },

    head_name: function (frm) {
        if (frm.doc.head_name && frm.doc.head_check == 'Yes' && frm.doc.head_name != 'VALVE HEAD-') {
            frappe.call({
                method: 'amf.amf.doctype.item_creation.item_creation.populate_fields',
                args: {
                    head_name: frm.doc.head_name  // Pass the entire document (form) to the method
                },
                callback: function (r) {
                    if (!r.exc) {
                        // Update the fields 'seat_name' and 'plug_name' after Python method executes successfully
                        frm.set_value('seat_name', r.message.seat_name);
                        frm.set_value('plug_name', r.message.plug_name);
                        frm.set_value('head_rnd', r.message.head_rnd);
                        frm.set_value('head_group', r.message.head_group);
                        frm.set_value('head_description', r.message.head_description);
                    }
                }
            });

            frappe.call({
            method: 'amf.amf.doctype.item_creation.item_creation.get_last_item_code',
            callback: function(r) {
                if (!r.exc) {
                    console.log("Last 6-digit item code: " + r.message);
                    frm.set_value('head_code', '300' + r.message);
                    /*frm.set_value('seat_code', '200' + r.message);
                    frm.set_value('plug_code', '100' + r.message);*/
                }
            }
            });
        }
    },


    head_item: function (frm) {
        if (frm.doc.head_item && frm.doc.head_check == 'No') {
            frappe.call({method: 'amf.amf.doctype.item_creation.item_creation.populate_fields_from_existing_item',
                args: { item_code: frm.doc.head_item },
                callback: function (r) {
                    if (!r.exc) {
                        // Update the head fields 
                        frm.set_value('head_code', r.message.head_code);
                        frm.set_value('head_name', r.message.head_name);
                        frm.set_df_property('head_name', 'read_only', 1);
                        frm.set_value('head_rnd', r.message.head_rnd);
                        frm.set_value('head_group', r.message.head_group);
                        frm.set_value('head_description', r.message.head_description);
                        
                        // Update the seat and plug fields
                        frm.set_value('seat_check', 'No');
                        frm.set_value('plug_check', 'No');
                        frm.set_df_property('seat_check', 'read_only', 1);
                        frm.set_df_property('plug_check', 'read_only', 1);
                        frm.set_value('seat_name', r.message.seat_name);
                        frm.set_value('plug_name', r.message.plug_name);
                        frm.set_value('seat_code', r.message.seat_code);
                        frm.set_value('plug_code', r.message.plug_code);
                        frm.set_value('seat_item', r.message.seat_code);
                        frm.set_value('plug_item', r.message.plug_code);
                        frm.set_df_property('seat_item', 'read_only', 1);
                        frm.set_df_property('plug_item', 'read_only', 1);
                    }
                }
            });
        }
    },

    
    head_description_check: function(frm) {
        // Use frm.doc.head_description_check to get the value of the checkbox (0 or 1)
        if (frm.doc.head_description_check) {
            // If checked, make the field editable (read_only = 0)
            frm.set_df_property('head_description', 'read_only', 0);
        } else {
            // If not checked, make the field read-only (read_only = 1)
            frm.set_df_property('head_description', 'read_only', 1);
        }
        // Refresh the field to apply the change to the UI
        frm.refresh_field('head_description');
    },

    
    head_check: function(frm) {   
       // Update the head fields 
        frm.set_value('head_code', "");
        frm.set_value('head_name', "VALVE HEAD-");
        frm.set_df_property('head_name', 'read_only', 0);
        frm.set_value('head_rnd', "");
        frm.set_value('head_group', "");
        frm.set_value('head_description', "");
        frm.set_value('head_item', "");

        // Update the seat and plug fields
        frm.set_value('seat_check', '');
        frm.set_value('plug_check', '');
        frm.set_df_property('seat_check', 'read_only', 0);
        frm.set_df_property('plug_check', 'read_only', 0);
        frm.set_value('seat_name', "");
        frm.set_value('plug_name', "");
        frm.set_value('seat_code', "");
        frm.set_value('plug_code', "");
        frm.set_value('seat_item', "");
        frm.set_value('plug_item', "");
        frm.set_df_property('seat_item', 'read_only', 0);
        frm.set_df_property('plug_item', 'read_only', 0);
    },
    

    seat_check: function(frm) {
        if (frm.doc.seat_check === 'Yes' && frm.doc.head_code) {
            // Extract the last three digits from head_code
            let head_code = frm.doc.head_code;
            let last_three_digits = head_code.slice(-3);  // Get the last three characters
                
            if (!isNaN(last_three_digits)) {
                // Convert last three digits to a number and add 2100
                let result = '200' + parseInt(last_three_digits, 10);
                
                // Set the result into a target field, assuming 'seat_code' is the target field
                frm.set_value('seat_code', result);
            } else {
                frappe.msgprint("Invalid head_code format. Last three characters should be digits.");
            }
        }
    },

    plug_check: function(frm) {
        if (frm.doc.plug_check === 'Yes' && frm.doc.head_code) {
            // Extract the last three digits from head_code
            let head_code = frm.doc.head_code;
            let last_three_digits = head_code.slice(-3);  // Get the last three characters
            
            if (!isNaN(last_three_digits)) {
                // Convert last three digits to a number and add 2100
                let result = '100' + parseInt(last_three_digits, 10);
                
                // Set the result into a target field, assuming 'seat_code' is the target field
                frm.set_value('plug_code', result);
            } else {
                frappe.msgprint("Invalid head_code format. Last three characters should be digits.");
            }
        }
    },

    rvm_check: function(frm) {
        if (frm.doc.rvm_check && frm.doc.head_code) {
            frappe.call({
                method: 'amf.amf.doctype.item_creation.item_creation.get_data_for_preview',
                args: {
                    'doc': frm.doc,
                    'group': 'rvm'
                },
                callback: function(r) {
                    if (r.message) {
                        // Construire une liste HTML avec item_name + item_code
                        let html = "<ul>";
                        r.message.forEach(it => {
                            html += `<li>${it.item_name} (${it.item_code})</li>`;
                        });
                        html += "</ul>";
                        frm.set_df_property("rvm_preview", "options", html);
                    } else {
                        frm.set_value("rvm_preview", "No preview available");
                        }
                    }
            });
        } else {
            frm.set_value("rvm_preview", "Invalid format");
        }
    },

    pump_check: function(frm) {
        if (frm.doc.pump_check && frm.doc.head_code) {
            frappe.call({
                method: 'amf.amf.doctype.item_creation.item_creation.get_data_for_preview',
                args: {
                    'doc': frm.doc,
                    'group': 'pump'
                },
                callback: function(r) {
                    if (r.message) {
                        // Construire une liste HTML avec item_name + item_code
                        let html = "<ul>";
                        r.message.forEach(it => {
                            html += `<li>${it.item_name} (${it.item_code})</li>`;
                        });
                        html += "</ul>";
                        frm.set_df_property("pump_preview", "options", html);
                    } else {
                        frm.set_value("pump_preview", "No preview available");
                        }
                    }
            });
        } else {
            frm.set_value("pump_preview", "Invalid format");
        }
    },

    pump_hv_check: function(frm) {
        if (frm.doc.pump_check && frm.doc.head_code) {
            frappe.call({
                method: 'amf.amf.doctype.item_creation.item_creation.get_data_for_preview',
                args: {
                    'doc': frm.doc,
                    'group': 'pump_hv'
                },
                callback: function(r) {
                    if (r.message) {
                        // Construire une liste HTML avec item_name + item_code
                        let html = "<ul>";
                        r.message.forEach(it => {
                            html += `<li>${it.item_name} (${it.item_code})</li>`;
                        });
                        html += "</ul>";
                        frm.set_df_property("pump_hv_preview", "options", html);
                    } else {
                        frm.set_value("pump_hv_preview", "No preview available");
                        }
                    }
            });
        } else {
            frm.set_value("pump_hv_preview", "Invalid format");
        }
    },

    /*
    item_group: function(frm) {
        if (frm.doc.item_group === 'Product') {
            frm.set_value('item_type', 'Finished Good');
            frm.set_value('body_check', 'Yes');
        }
        else {
            frm.set_value('item_type', '');
            frm.set_value('body_check', '');
        }
    },
    */
    /*
    body: function(frm) {
        //get value of body and map it
        //send the code as args
        frappe.call({
            method: 'amf.amf.doctype.item_creation.item_creation.get_last_item_code',
            callback: function(r) {
                if (!r.exc) {
                    console.log("Last 6-digit item code: " + r.message);
                }
            }
        });
    }*/
});

async function createPlug(frm) {
    await frappe.call({
        method: 'amf.amf.doctype.item_creation.item_creation.create_item_from_doc',
        args: {
            'doc': frm.doc,
            'group': 'plug'
        },
        callback: function (response) {
            console.log(response);
            if (response) {
                frappe.show_alert(__("New Plug successfully created.", [response]));
                // frm.save('Update');
            } else {
                frappe.validated = false;
                console.error('Failed to create Plug');
                alert('Error: ' + (response.message ? response.message : 'Unknown error'));
            }
        }
    });
}

async function createSeat(frm) {
    await frappe.call({
        method: 'amf.amf.doctype.item_creation.item_creation.create_item_from_doc',
        args: {
            'doc': frm.doc,
            'group': 'seat'
        },
        callback: function (response) {
            console.log(response);
            if (response) {
                frappe.show_alert(__("New Seat successfully created.", [response]));
                // frm.save('Update');
            } else {
                frappe.validated = false;
                console.error('Failed to create Seat');
                alert('Error: ' + (response.message ? response.message : 'Unknown error'));
            }
        }
    });
}

async function createHead(frm) {
    await frappe.call({
        method: 'amf.amf.doctype.item_creation.item_creation.create_item_from_doc',
        args: {
            'doc': frm.doc,
            'group': 'head'
        },
        callback: function (response) {
            console.log(response);
            if (response) {
                frappe.show_alert(__("New Head successfully created.", [response]));
                // frm.save('Update');
            } else {
                frappe.validated = false;
                console.error('Failed to create Head');
                alert('Error: ' + (response.message ? response.message : 'Unknown error'));
            }
        }
    });
}


async function createRVM(frm) {
    await frappe.call({
        method: 'amf.amf.doctype.item_creation.item_creation.create_item_from_doc',
        args: {
            'doc': frm.doc,
            'group': 'rvm'
        },
        callback: function (response) {
            console.log(response);
            if (response) {
                frappe.show_alert(__("New RVM successfully created.", [response]));
                // frm.save('Update');
            } else {
                frappe.validated = false;
                console.error('Failed to create RVM');
                alert('Error: ' + (response.message ? response.message : 'Unknown error'));
            }
        }
    });
}


async function createPump(frm) {
    await frappe.call({
        method: 'amf.amf.doctype.item_creation.item_creation.create_item_from_doc',
        args: {
            'doc': frm.doc,
            'group': 'pump'
        },
        callback: function (response) {
            console.log(response);
            if (response) {
                frappe.show_alert(__("New Pump successfully created.", [response]));
                // frm.save('Update');
            } else {
                frappe.validated = false;
                console.error('Failed to create Pump');
                alert('Error: ' + (response.message ? response.message : 'Unknown error'));
            }
        }
    });
}


async function createPumpHV(frm) {
    await frappe.call({
        method: 'amf.amf.doctype.item_creation.item_creation.create_item_from_doc',
        args: {
            'doc': frm.doc,
            'group': 'pump_hv'
        },
        callback: function (response) {
            console.log(response);
            if (response) {
                frappe.show_alert(__("New Pump HV successfully created.", [response]));
                // frm.save('Update');
            } else {
                frappe.validated = false;
                console.error('Failed to create Pump HV');
                alert('Error: ' + (response.message ? response.message : 'Unknown error'));
            }
        }
    });
}

