/*
Supplier Quotation Script
--------------------

What this does:
* Handles click on "Add shipping and taxes" button:
    * Empties taxes table
    * Replaces by two items: first item shipping, second item VAT (applies to previous total)

*/
frappe.ui.form.on("Supplier Quotation", {

    refresh: function (frm) {

        frm.add = function (costCenter, VATaccountHead, VATrate, VATdescription) {
            frm.clear_table("taxes");

        var taxes = frm.add_child("taxes");
        frappe.model.set_value(taxes.doctype, taxes.name, "charge_type", "On Net Total");
        frappe.model.set_value(taxes.doctype, taxes.name, "cost_center", costCenter);
        frappe.model.set_value(taxes.doctype, taxes.name, "account_head", VATaccountHead);
        setTimeout(function() {
             frappe.model.set_value(taxes.doctype, taxes.name, "rate", VATrate);
             frappe.model.set_value(taxes.doctype, taxes.name, "description", VATdescription);
         }, 400);

            frm.refresh_field("taxes");
        }
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
            },{
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
		switch (values.vat){
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
				VATrate = 7.7;
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
				VATrate = 7.7;
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