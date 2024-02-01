/*
Sales Invoice Script
--------------------

What this does:
* Handles click on "Add shipping and taxes" button:
    * Empties taxes table
    * Replaces by two items: first item shipping, second item VAT (applies to previous total)

*/
frappe.ui.form.on('Sales Invoice', {
    onload: function(frm) {
        if (frm.doc.customer) {
            frappe.call({
                method: "frappe.client.get",
                args: {
                    doctype: "Customer",
                    name: frm.doc.customer
                },
                callback: function (data) {
                    frm.set_value('accounting_email_invoice', data.message.accounting_email);
                }
            });
        }
    },
    customer: function(frm) {
        frappe.call({
            method: "frappe.client.get",
            args: {
                doctype: "Customer",
                name: frm.doc.customer
            },
            callback: function (data) {
                frm.set_value('accounting_email_invoice', data.message.accounting_email);
            }
        });
    }
});


frappe.ui.form.on('Sales Invoice', {
    refresh: function(frm) {
        if (frm.doc.delivery_note) {
            frappe.call({
                method: "frappe.client.get_value",
                args: {
                    doctype: "Delivery Note",
                    filters: {name: frm.doc.delivery_note},
                    fieldname: "tracking_no"
                },
                callback: function(r) {
                    frm.set_value("delivery_note_tracking_no", r.message.tracking_no);
                }
            });
        }
    }
});

frappe.ui.form.on('Sales Invoice', {
    validate: function(frm) {
        if (frm.doc.delivery_note) {
            if (!frm.doc.delivery_note_tracking_no || frm.doc.delivery_note_tracking_no.length < 5) {
                frappe.throw(__("Please enter a valid Tracking Number in the Delivery Note."));
            }
            // get the delivery note linked to the sales invoice
            var delivery_note = frm.doc.items[0].delivery_note;
            
            // get the value of the tracking number field from the delivery note
            frappe.db.get_value('Delivery Note', delivery_note, 'tracking_no', function(r) {
                var tracking_number = r.tracking_no;
                
                // log the tracking number and the user who modified it
                console.log("Tracking number:", tracking_number);
                console.log("Modified by:", frm.doc.modified_by);
            });
            
            // Check if the user modifying the tracking number field is Madeleine Fryer
            const modified_by = frm.doc.modified_by;
            if (modified_by === 'ferdinand.ativon@amf.ch') {
                //frappe.throw(__("The Tracking Number must be verified by the Logistics Manager."));
            }
        }
    }
});

frappe.ui.form.on("Sales Invoice", {

    refresh: function (frm) {
        frm.add = function (cost, costCenter, VATaccountHead, VATrate, VATdescription) {
            frm.clear_table("taxes");

	if (cost > 0) {
            var shipping = frm.add_child("taxes");
            frappe.model.set_value(shipping.doctype, shipping.name, "charge_type", "Actual");
            frappe.model.set_value(shipping.doctype, shipping.name, "cost_center", costCenter);
            frappe.model.set_value(shipping.doctype, shipping.name, "account_head", "3410 - Transport and commission costs - AMF21");
            frappe.model.set_value(shipping.doctype, shipping.name, "tax_amount", cost);
	}
            var taxes = frm.add_child("taxes");
	if (cost > 0) {
            frappe.model.set_value(taxes.doctype, taxes.name, "charge_type", "On Previous Row Total");
            frappe.model.set_value(taxes.doctype, taxes.name, "row_id", "1");
	} else {
            frappe.model.set_value(taxes.doctype, taxes.name, "charge_type", "On Net Total");
	}
            frappe.model.set_value(taxes.doctype, taxes.name, "cost_center", costCenter);

            frappe.model.set_value(taxes.doctype, taxes.name, "account_head", VATaccountHead);
            setTimeout(function() {
		if (cost > 0){
			frappe.model.set_value(shipping.doctype, shipping.name, "description", "Shipping");
		}
		frappe.model.set_value(taxes.doctype, taxes.name, "rate", VATrate);
            	frappe.model.set_value(taxes.doctype, taxes.name, "description", VATdescription);
             }, 400);

            frm.refresh_field("taxes");
        }
        
        if ((frm.doc.__islocal) && (frm.doc.is_return)) {
            // select SINV-RET- as naming series
            cur_frm.set_value("naming_series", "SINV-RET-");
        }
    },
    add_shipping_and_taxes: function (frm) {
        frappe.prompt([{
                'fieldname': 'cost',
                'fieldtype': 'Currency',
                'label': 'Shipping Cost',
                'reqd': 0,
		'default': 0,
            }, {
                'fieldname': 'costCenter',
                'fieldtype': 'Select',
		'options': 'General - AMF21\n' +
			'Automation - AMF21\n' +
			'Patch - AMF21',
                'label': 'Cost Center',
                'reqd': 1,
                'default': 0,
            },{
                'fieldname': 'vat',
                'fieldtype': 'Select',
		'options': 
			'VAT 8.1%\n' + 
			'VAT 8.1% - Import of Services\n' + 
			'VAT 0%\n' +
			'VAT 0% - Import of Services',
                'label': 'VAT',
                'reqd': 1,
            }],
            function (values) {
                console.log(values);
		var VATaccountHead;
		var VATrate;
		var VATdescription;
		switch (values.vat){
			case 'VAT 8.1%':
				VATaccountHead = '2200 - VAT due - AMF21';
				VATrate = 8.1;
				VATdescription = 'VAT 8.1%';
			break;
			case 'VAT 8.1% - Import of Services':
				VATaccountHead = '2226 - VAT payable on import of services - AMF21';
				VATrate = 8.1;
				VATdescription = 'VAT 8.1%';
			break;
			case 'VAT 0%':
				VATaccountHead = '2200 - VAT due - AMF21';
				VATrate = 0;
				VATdescription = 'VAT 0%';
			break;
			case 'VAT 0% - Import of Services':
				VATaccountHead = '2226 - VAT payable on import of services - AMF21';
				VATrate = 0;
				VATdescription = 'VAT 0%';
			break;
		}
		frm.add(values.cost, values.costCenter, VATaccountHead, VATrate, VATdescription);	
            },
            'Shipping Cost Entry',
            'Add',
        );
    },
});