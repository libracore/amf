/*
Quotation Script
--------------------

What this does:
* Handles click on "Add shipping and taxes" button:
    * Empties taxes table
    * Replaces by two items: first item shipping, second item VAT (applies to previous total)

*/
frappe.ui.form.on("Quotation", {

    //onload: function (frm) {
    //    frm.doc.currency = '';
    //},


    validate: function (frm) {
        calculate_total_price_discounted(frm);
    },

    /*before_save: function(frm) {
        // Check if there are items
        if (frm.doc.items && frm.doc.items.length) {
            calculate_total_price_discounted(frm);
        }
    },*/

    refresh: function (frm) {
        frm.doc.letter_head = "Standard for Sales Order";
        //frm.clear_table("taxes");
        frm.add = function (cost, costCenter, VATaccountHead, VATrate, VATdescription) {
            frm.clear_table("taxes");
            if (cost > 0) {
                var shipping = frm.add_child("taxes");
                frappe.model.set_value(shipping.doctype, shipping.name, "charge_type", "Actual");
                frappe.model.set_value(shipping.doctype, shipping.name, "cost_center", costCenter);
                frappe.model.set_value(shipping.doctype, shipping.name, "account_head", "3410 - Transport and commission costs - AMF21");
                frappe.model.set_value(shipping.doctype, shipping.name, "tax_amount", cost);
            }
            if (frm.doc.currency == 'CHF') {
                var taxes = frm.add_child("taxes");

                if (cost > 0) {
                    frappe.model.set_value(taxes.doctype, taxes.name, "charge_type", "On Previous Row Total");
                    frappe.model.set_value(taxes.doctype, taxes.name, "row_id", "1");
                } else {
                    frappe.model.set_value(taxes.doctype, taxes.name, "charge_type", "On Net Total");
                }
                frappe.model.set_value(taxes.doctype, taxes.name, "cost_center", costCenter);

                frappe.model.set_value(taxes.doctype, taxes.name, "account_head", VATaccountHead);
                setTimeout(function () {
                    if (cost > 0) {
                        frappe.model.set_value(shipping.doctype, shipping.name, "description", "Shipping");
                    }
                    frappe.model.set_value(taxes.doctype, taxes.name, "rate", VATrate);
                    frappe.model.set_value(taxes.doctype, taxes.name, "description", VATdescription);
                }, 400);
                frm.refresh_field("taxes");
            }
        };
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
        }, {
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
                switch (values.vat) {
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

function calculate_total_price_discounted(frm) {
    // Go through each item in the child table
    $.each(frm.doc.items || [], function (i, item) {
        // Calculate discounted price: rate * (1 - discount_percentage / 100)
        item.total_price_disc = flt((item.price_list_rate * item.qty) * (1 - item.discount_percentage / 100));

        // Refresh fields to update the UI
        refresh_field("total_price_disc", item.name, "items");
    });
}