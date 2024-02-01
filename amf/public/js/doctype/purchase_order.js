/*
Purchase Order Script
--------------------

What this does:
* Handles click on "Add shipping and taxes" button:
    * Empties taxes table
    * Replaces by two items: first item shipping, second item VAT (applies to previous total)

*/
frappe.ui.form.on("Purchase Order", {
    
    onload: function(frm) {},
    
    after_save: function(frm) {
        //console.log("before_save");
        if(!frm.doc.payment_terms_template) {
            console.log("!frm.doc.payment_terms_template");
            frm.doc.payment_schedule = null;
            frm.clear_table("payment_schedule");
            refresh_field("payment_schedule");
            console.log("Cleared payment_schedule.");
            frm.set_value('payment_terms_template', '30 days after invoice');
            refresh_field("payment_terms_template");
            console.log("Set payment_terms_template to '30 days after invoice'.");
        }
        if(frm.doc.payment_terms_template) {
            console.log("frm.doc.payment_terms_template");
            frappe.call({
                method: 'amf.amf.utils.document_notifcation.generate_payment_schedule',
                args: {
                    'po_name': frm.doc.name
                },
                callback: function(response) {
                    // handle any post-call actions here
                    console.log(response.message);
                    // use setTimeout to delay the form reload
                    setTimeout(function() {
                        // reload the document to fetch the latest version from the server
                        frm.reload_doc();
                    }, 500); // delay of 0.5 seconds (500 milliseconds)
                }
            });
        } else {
            // If the payment_terms_template field does not have a value, clear the Payment Terms child table
            frm.doc.payment_terms = [];
            frm.doc.payment_schedule = [];
            refresh_field("payment_terms");
            refresh_field("payment_schedule");
        }
    },
    

    refresh: function (frm) {

        frm.add = function (costCenter, VATaccountHead, VATrate, VATdescription) {
            frm.clear_table("taxes");

            var taxes = frm.add_child("taxes");
            frappe.model.set_value(taxes.doctype, taxes.name, "charge_type", "On Net Total");
            frappe.model.set_value(taxes.doctype, taxes.name, "cost_center", costCenter);
            frappe.model.set_value(taxes.doctype, taxes.name, "account_head", VATaccountHead);
            setTimeout(function () {
                frappe.model.set_value(taxes.doctype, taxes.name, "rate", VATrate);
                frappe.model.set_value(taxes.doctype, taxes.name, "description", VATdescription);
            }, 400);

            frm.refresh_field("taxes");
        };
        /*
        if (frm.doc.payment_schedule && frm.doc.payment_schedule.length > 0) {
            frm.doc.payment_schedule.sort((a, b) => (a.due_date > b.due_date) ? 1 : -1);
            frm.set_value('schedule_payment_date', frappe.datetime.add_days(frm.doc.payment_schedule[0].due_date, -3));
        }
        
        if (frm.doc.schedule_payment_date && frm.doc.status === 'To Bill') {
            // Set check_payment_reminder to 1
            frm.set_value('payment_reminder', 1);
        }
        */
        
    },
    add_shipping_and_taxes: function (frm) {
        frappe.prompt([{
            'fieldname': 'costCenter',
            'fieldtype': 'Select',
            'options': 'General - AMF21\n' +
                'Automation - AMF21\n' +
                'Patch - AMF21',
            'label': 'Cost Center',
            'reqd': 1,
            'default': 0,
        }, {
            'fieldname': 'vat',
            'fieldtype': 'Select',
            'options':
                'VAT 0% on accounts 1xxx, 5xxx and 6xxx\n' +
                'VAT 2.5% on accounts 1xxx, 5xxx and 6xxx\n' +
                'VAT 8.1% on accounts 1xxx, 5xxx and 6xxx\n' +
                'VAT 0% on accounts 4xxx\n' +
                'VAT 2.5% on accounts 4xxx\n' +
                'VAT 8.1% on accounts 4xxx',
            'label': 'VAT',
            'reqd': 1,
        }],
            function (values) {
                console.log(values);
                var VATaccountHead;
                var VATrate;
                var VATdescription;
                switch (values.vat) {
                    case 'VAT 0% on accounts 1xxx, 5xxx and 6xxx':
                        VATaccountHead = '1171 - VAT on accounts 1xxx, 5xxx and 6xxx - AMF21';
                        VATrate = 0;
                        VATdescription = 'VAT 0%';
                        break;
                    case 'VAT 2.5% on accounts 1xxx, 5xxx and 6xxx':
                        VATaccountHead = '1171 - VAT on accounts 1xxx, 5xxx and 6xxx - AMF21';
                        VATrate = 2.5;
                        VATdescription = 'VAT 2.5%';
                        break;
                    case 'VAT 8.1% on accounts 1xxx, 5xxx and 6xxx':
                        VATaccountHead = '1171 - VAT on accounts 1xxx, 5xxx and 6xxx - AMF21';
                        VATrate = 8.1;
                        VATdescription = 'VAT 8.1%';
                        break;
                    case 'VAT 0% on accounts 4xxx':
                        VATaccountHead = '1170 - VAT on accounts 4xxx - AMF21';
                        VATrate = 0;
                        VATdescription = 'VAT 0%';
                        break;
                    case 'VAT 2.5% on accounts 4xxx':
                        VATaccountHead = '1170 - VAT on accounts 4xxx - AMF21';
                        VATrate = 2.5;
                        VATdescription = 'VAT 2.5%';
                        break;
                    case 'VAT 8.1% on accounts 4xxx':
                        VATaccountHead = '1170 - VAT on accounts 4xxx - AMF21';
                        VATrate = 8.1;
                        VATdescription = 'VAT 8.1%';
                        break;
                }
                frm.add(values.costCenter, VATaccountHead, VATrate, VATdescription);
            },
            'Taxes Entry',
            'Add',
        );
    },
});