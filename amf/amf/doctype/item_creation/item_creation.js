// Copyright (c) 2024, libracore AG and contributors
// For license information, please see license.txt

frappe.ui.form.on('Item Creation', {

    onload: function(frm) {
        if (frm.is_new()) {
            frm.set_value('item_group', 'Product');
        }
    },

    before_submit: function (frm) {
        if (frm.doc.plug_check)
            createPlug(frm)
        // if (frm.doc.seat_check)
            // createSeat(frm)
        // if (frm.doc.head_check)
            // createHead(frm)
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
    },

    head_name: function (frm) {
        if (frm.doc.head_name) {
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
                        frm.set_value('head_description', r.message.head_description);
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
        if (frm.doc.head_check === 'Yes') {
            frappe.call({
                method: 'amf.amf.doctype.item_creation.item_creation.get_last_item_code',
                callback: function(r) {
                    if (!r.exc) {
                        console.log("Last 6-digit item code: " + r.message);
                        frm.set_value('head_code', '300' + r.message);
                    }
                }
            });
        }
    },

    seat_check: function(frm) {
        if (frm.doc.seat_check === 'Yes') {
            if (frm.doc.seat_check === 'Yes' && frm.doc.head_code) {
                // Extract the last two digits from head_code
                let head_code = frm.doc.head_code;
                let last_two_digits = head_code.slice(-3);  // Get the last two characters
                
                if (!isNaN(last_two_digits)) {
                    // Convert last two digits to a number and add 2100
                    let result = '200' + parseInt(last_two_digits, 10);
                    
                    // Set the result into a target field, assuming 'seat_code' is the target field
                    frm.set_value('seat_code', result);
                } else {
                    frappe.msgprint("Invalid head_code format. Last two characters should be digits.");
                }
            }
        }
    },

    plug_check: function(frm) {
        if (frm.doc.plug_check === 'Yes') {
            if (frm.doc.plug_check === 'Yes' && frm.doc.head_code) {
                // Extract the last two digits from head_code
                let head_code = frm.doc.head_code;
                let last_two_digits = head_code.slice(-3);  // Get the last two characters
                
                if (!isNaN(last_two_digits)) {
                    // Convert last two digits to a number and add 2100
                    let result = '100' + parseInt(last_two_digits, 10);
                    
                    // Set the result into a target field, assuming 'seat_code' is the target field
                    frm.set_value('plug_code', result);
                } else {
                    frappe.msgprint("Invalid head_code format. Last two characters should be digits.");
                }
            }
        }
    },

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

    body: function(frm) {
        //get value of body and map it
        //send the code as args
        frappe.call({
            method: 'amf.amf.doctype.item_creation.item_creation.get_last_item_code',
            args: {
                'code_body': 1
            },
            callback: function(r) {
                if (!r.exc) {
                    console.log("Last 6-digit item code: " + r.message);
                }
            }
        });
    }
});

function createPlug(frm) {
    frappe.call({
        method: 'amf.amf.doctype.item_creation.item_creation.create_plug_from_doc',
        args: {
            'doc': frm.doc,
        },
        freeze: true,
        freeze_message: __("Item <strong>PLUG</strong> en cours de création...<br>Mise à jour des entrées de stock...<br>Merci de patienter..."),
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

function createSeat(frm) {
    frappe.call({
        method: 'amf.amf.doctype.item_creation.item_creation.create_seat_from_doc',
        args: {
            'doc': frm.doc,
        },
        freeze: true,
        freeze_message: __("Item <strong>SEAT</strong> en cours de création...<br>Mise à jour des entrées de stock...<br>Merci de patienter..."),
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

function createHead(frm) {
    frappe.call({
        method: 'amf.amf.doctype.item_creation.item_creation.create_item',
        args: {
            'doc': frm.doc,
            'item_type': 'valve_head'
        },
        freeze: true,
        freeze_message: __("Item <strong>HEAD</strong> en cours de création...<br>Mise à jour des entrées de stock...<br>Merci de patienter..."),
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
