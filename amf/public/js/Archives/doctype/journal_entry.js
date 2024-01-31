/*
Journal Entry Script
--------------------

What this does:
* Handles click on "Add entry with VAT" button:
    * Adds 1 line for the expense without VAT
    * Adds 1 line for the VAT

*/
frappe.ui.form.on("Journal Entry", {
    refresh: function (frm) {

        frm.add = function (cost, expenseDate, expenseDescription, expenseAccount, VATtype, VATaccountHead, VATrate, VATdescription) {

	var a = cost*(1-VATrate/100);
	var expenseCost = Math.round(a * 100 + Number.EPSILON) / 100;
	var VATcost = cost-expenseCost ;

        var expense = frm.add_child("expenses");
	frappe.model.set_value(expense.doctype, expense.name, "expense_date", expenseDate);
	frappe.model.set_value(expense.doctype, expense.name, "description", expenseDescription);
	frappe.model.set_value(expense.doctype, expense.name, "expense_type", expenseAccount);
	frappe.model.set_value(expense.doctype, expense.name, "default_account", expenseAccount);
	frappe.model.set_value(expense.doctype, expense.name, "claim_amount", expenseCost);
	frappe.model.set_value(expense.doctype, expense.name, "sanctioned_amount", expenseCost);

	var taxes = frm.add_child("expenses");
	frappe.model.set_value(taxes.doctype, taxes.name, "expense_date", expenseDate);
	frappe.model.set_value(taxes.doctype, taxes.name, "expense_type", VATtype);
	frappe.model.set_value(taxes.doctype, taxes.name, "default_account", VATaccountHead);
	frappe.model.set_value(taxes.doctype, taxes.name, "description", VATdescription);
	frappe.model.set_value(taxes.doctype, taxes.name, "claim_amount", VATcost);
	frappe.model.set_value(taxes.doctype, taxes.name, "sanctioned_amount", VATcost);

        frm.refresh_field("expenses");
        }
    },

    add_expense: function (frm) {
        frappe.prompt([{
                'fieldname': 'expenseDate',
                'fieldtype': 'Date',
                'label': 'Expense Date',
                'reqd': 1,
		'default': 0,
            },{
                'fieldname': 'cost',
                'fieldtype': 'Currency',
                'label': 'Expense Cost',
                'reqd': 1,
		'default': 0,
            },{
                'fieldname': 'vat',
                'fieldtype': 'Select',
		'options': 
		    'VAT 0% on accounts 1xxx, 5xxx and 6xxx\n' + 
		    'VAT 2.5% on accounts 1xxx, 5xxx and 6xxx\n' + 
		    'VAT 3.7% on accounts 1xxx, 5xxx and 6xxx\n' + 
		    'VAT 8.1% on accounts 1xxx, 5xxx and 6xxx\n' +
		    'VAT 0% on accounts 4xxx\n' +
		    'VAT 2.5% on accounts 4xxx\n' +
		    'VAT 3.7% on accounts 4xxx\n' + 
		    'VAT 8.1% on accounts 4xxx',
                'label': 'VAT',
                'reqd': 1,
            },{
                'fieldname': 'expenseAccount',
                'fieldtype': 'Link',
                'label': 'Expense Account',
		'options': 'Expense Claim Type',
                'reqd': 1,
		'default': 0,
            },{
                'fieldname': 'expenseDescription',
                'fieldtype': 'Small Text',
                'label': 'Description',
                'reqd': 1,
		'default': 0,
            }],
            function (values) {
                console.log(values);
		var VATtype;
		var VATaccountHead;
		var VATrate;
		var VATdescription;
		switch (values.vat){
		    case 'VAT 0% on accounts 1xxx, 5xxx and 6xxx':
		        VATtype= '1171 - VAT on accounts 1xxx, 5xxx and 6xxx - AMF21';
			VATaccountHead = '8911 - VAT account 1171 for Expense Claim - AMF21';
			VATdescription = 'VAT 0%';
			VATrate = 0;
		    break;
		    case 'VAT 2.5% on accounts 1xxx, 5xxx and 6xxx':
			VATtype= '1171 - VAT on accounts 1xxx, 5xxx and 6xxx - AMF21';
			VATaccountHead = '8911 - VAT account 1171 for Expense Claim - AMF21';
			VATdescription = 'VAT 2.5%';
			VATrate = 2.5;
		    break;
		    case 'VAT 3.7% on accounts 1xxx, 5xxx and 6xxx':
			VATtype= '1171 - VAT on accounts 1xxx, 5xxx and 6xxx - AMF21';
			VATaccountHead = '8911 - VAT account 1171 for Expense Claim - AMF21';
			VATdescription = 'VAT 3.7%';
			VATrate = 3.7;
		    break;
		    case 'VAT 8.1% on accounts 1xxx, 5xxx and 6xxx':
			VATtype= '1171 - VAT on accounts 1xxx, 5xxx and 6xxx - AMF21';
			VATaccountHead = '8911 - VAT account 1171 for Expense Claim - AMF21';
			VATdescription = 'VAT 8.1%';
			VATrate = 7.7;
		    break;
	   	    case 'VAT 0% on accounts 4xxx':
			VATtype= '1170 - VAT on accounts 4xxx - AMF21';
			VATaccountHead = '8910 - VAT account 1170 for Expense Claim - AMF21';
			VATdescription = 'VAT 0%';
			VATrate = 0;
		    break;
		    case 'VAT 2.5% on accounts 4xxx':
			VATtype= '1170 - VAT on accounts 4xxx - AMF21';
			VATaccountHead = '8910 - VAT account 1170 for Expense Claim - AMF21';
			VATdescription = 'VAT 2.5%';
			VATrate = 2.5;
		    break;
		    case 'VAT 3.7% on accounts 4xxx':
			VATtype= '1170 - VAT on accounts 4xxx - AMF21';
			VATaccountHead = '8910 - VAT account 1170 for Expense Claim - AMF21';
			VATdescription = 'VAT 3.7%';
			VATrate = 3.7;
		    break;
		    case 'VAT 8.1% on accounts 4xxx':
			VATtype= '1170 - VAT on accounts 4xxx - AMF21';
			VATaccountHead = '8910 - VAT account 1170 for Expense Claim - AMF21';
			VATdescription = 'VAT 8.1%';
			VATrate = 7.7;
		    break;
		}
		frm.add(values.cost, values.expenseDate, values.expenseDescription, values.expenseAccount, VATtype, VATaccountHead, VATrate, VATdescription);	
            },
            'Expense Entry',
            'Add',
        );
    },
    validate: function(frm) {
        frm.doc.posting_date = frm.doc.cheque_date;
        frm.doc.title = frm.doc.cheque_no;

    },
});