/*
Purchase Receipt Script
--------------------

What this does:
* Handles click on "Add shipping and taxes" button:
    * Empties taxes table
    * Replaces by two items: first item shipping, second item VAT (applies to previous total)

*/
frappe.ui.form.on("Purchase Receipt", {
    
    before_submit: function(frm) {
        let created_batches = {};
        $.each(frm.doc.items || [], async function(i, d) {
            console.log(d);
            
            if (created_batches[d.item_code]) {
                d.batch_no = created_batches[d.item_code];
                return;  // Skip to next iteration if batch already created for this item
            }
            
            let item = await frappe.db.get_value('Item', d.item_code, 'has_batch_no');
            if (item.message.has_batch_no) {
                let batch_id = d.item_code + " • " + frm.doc.posting_date + " • " + frm.doc.supplier + " • " + frm.doc.purchase_order_ + " • " + frm.doc.total_qty;
                //d.batch_no = d.item_code + "/" + frm.doc.posting_date + "/" + frm.doc.supplier;
                
                frappe.call({
                    method: "frappe.client.insert",
                    args: {
                        doc: {
                            doctype: "Batch",
                            item: d.item_code,
                            batch_id: batch_id,
                        }
                    },
                    callback: function(response) {
                        d.batch_no = response.message.name;
                        created_batches[d.item_code] = response.message.name;
                    }
                });
            }
        });
    },

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
        };
        
        if ((frm.doc.__islocal) && (frm.doc.is_return)) {
            // select PREC-RET- as naming series
            cur_frm.set_value("naming_series", "PREC-RET-");
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