// Copyright (c) 2024, libracore AG and contributors
// For license information, please see license.txt

frappe.ui.form.on('Item Creation', {
    head_name: function (frm) {
        if (frm.doc.head_name) {
            frappe.call({
                method: 'amf.amf.doctype.item_creation.item_creation.populate_fields',  // Replace with the correct path to your Python method
                args: {
                    head_name: frm.doc.head_name  // Pass the entire document (form) to the method
                },
                callback: function (r) {
                    if (!r.exc) {
                        // Update the fields 'seat_name' and 'plug_name' after Python method executes successfully
                        frm.set_value('seat_name', r.message.seat_name);
                        frm.set_value('plug_name', r.message.plug_name);
                        frm.set_value('head_rnd', r.message.head_rnd);
                    }
                }
            });
        }
    },

    head_check: function(frm) {
        if (frm.doc.head_check === 'Yes') {
            frappe.call({
                method: 'amf.amf.doctype.item_creation.item_creation.get_last_item_code',  // Replace with the correct path to your method
                callback: function(r) {
                    if (!r.exc) {
                        console.log("Last 6-digit item code: " + r.message);
                        frm.set_value('head_code', '3000' + r.message);
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
                let last_two_digits = head_code.slice(-2);  // Get the last two characters
                
                if (!isNaN(last_two_digits)) {
                    // Convert last two digits to a number and add 2100
                    let result = '2000' + parseInt(last_two_digits, 10);
                    
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
                let last_two_digits = head_code.slice(-2);  // Get the last two characters
                
                if (!isNaN(last_two_digits)) {
                    // Convert last two digits to a number and add 2100
                    let result = '1000' + parseInt(last_two_digits, 10);
                    
                    // Set the result into a target field, assuming 'seat_code' is the target field
                    frm.set_value('plug_code', result);
                } else {
                    frappe.msgprint("Invalid head_code format. Last two characters should be digits.");
                }
            }
        }
    },

});

function createPlug(frm) {
    frappe.call({
        method: 'amf.amf.doctype.item_creation.item_creation.create_item',
        args: {
            'doc': frm.doc,
            'item_type': 'plug'
        },
        freeze: true,
        freeze_message: __("Item <strong>PLUG</strong> creation in process...<br>Mise à jour des entrées de stock...<br>Merci de patienter..."),
        callback: function (response) {
            console.log(response);
            if (response && response.message.success) {
                // Set the values returned from the response
                
                // Display a popup
                frappe.msgprint({
                    title: __('New Item Creation'),
                    indicator: 'green',
                    message: __('New Plug successfully created.')
                });
                frm.save('Update');
            } else {
                frappe.validated = false;
                console.error('Failed to create Plug');
                alert('Error: ' + (response.message ? response.message : 'Unknown error'));
            }
        }
    });
}
