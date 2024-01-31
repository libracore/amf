/*
Expense Claim Script
--------------------

What this does:
* Handles click on "Add expense" button:
    * Adds 1 line for the expense without VAT
    * Adds 1 line for the VAT

*/
frappe.ui.form.on("Expense Claim", {

    refresh: function (frm) {
            
            /*
            // Add button on form
            frm.add_custom_button('Upload Excel', function() {
                    
                        frappe.call({
                            method: 'amf.amf.utils.read_file.create_expense_items',
                            args: {
                                expense_claim: frm.doc.name,
                                attach: frm.doc.excel_file
                            },
                            callback: function(response) {
                                if(response.message == 'Expense items created successfully') {
                                    cur_frm.reload_doc();
                                }
                            }
                        });
                    });
            */
        frm.add = function (cost, expenseDate, expenseDescription, expenseAccount, VATaccountHead, VATrate, VATdescription, costCenter) {

            frm.doc.cost_center = costCenter;

            var a = cost * 100 / (100 + VATrate);
            var expenseCost = Math.round(a * 100 + Number.EPSILON) / 100;
            var VATcost = cost - expenseCost;

            var expense = frm.add_child("expenses");
            frappe.model.set_value(expense.doctype, expense.name, "expense_date", expenseDate);
            frappe.model.set_value(expense.doctype, expense.name, "description", expenseDescription);
            frappe.model.set_value(expense.doctype, expense.name, "expense_type", expenseAccount);
            frappe.model.set_value(expense.doctype, expense.name, "default_account", expenseAccount);
            frappe.model.set_value(expense.doctype, expense.name, "amount", cost);
            frappe.model.set_value(expense.doctype, expense.name, "sanctioned_amount", cost);
            frappe.model.set_value(expense.doctype, expense.name, "vat_account_head", VATaccountHead);
            frappe.model.set_value(expense.doctype, expense.name, "vat_included", VATcost);
            
            /* if (VATcost > 0) {
                var taxes = frm.add_child("taxes");
                frappe.model.set_value(taxes.doctype, taxes.name, "account_head", VATaccountHead);
                frappe.model.set_value(taxes.doctype, taxes.name, "description", VATdescription);
                frappe.model.set_value(taxes.doctype, taxes.name, "tax_amount", VATcost);
                frappe.model.set_value(taxes.doctype, taxes.name, "cost_center", costCenter);
            } */

            frm.refresh_field("expenses");
            // frm.refresh_field("taxes");
        };
    },

    add_expense: function (frm) {
        frappe.prompt([{
            'fieldname': 'expenseDate',
            'fieldtype': 'Date',
            'label': 'Expense Date',
            'reqd': 1,
            'default': 0,
        }, {
            'fieldname': 'cost',
            'fieldtype': 'Currency',
            'label': 'Expense Cost',
            'reqd': 1,
            'default': 0,
        }, {
            'fieldname': 'expenseAccount',
            'fieldtype': 'Link',
            'label': 'Expense Account',
            'options': 'Expense Claim Type',
            'reqd': 1,
            'default': 0,
        }, {
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
        }, {
            'fieldname': 'expenseDescription',
            'fieldtype': 'Small Text',
            'label': 'Description',
            'reqd': 1,
            'default': 0,
        }, {
            'fieldname': 'costCenter',
            'fieldtype': 'Select',
            'label': 'Cost Center',
            'options':
                'General - AMF21\n' +
                'Automation - AMF21\n' +
                'Patch - AMF21',
            'reqd': 1,
            'default': 0,
        }],
            function (values) {
                console.log(values);
                var VATaccountHead;
                var VATrate;
                var VATdescription;
                switch (values.vat) {
                    case 'VAT 0% on accounts 1xxx, 5xxx and 6xxx':
                        VATaccountHead = '1171 - VAT on accounts 1xxx, 5xxx and 6xxx - AMF21';
                        VATdescription = 'VAT 0%';
                        VATrate = 0;
                        break;
                    case 'VAT 2.5% on accounts 1xxx, 5xxx and 6xxx':
                        VATaccountHead = '1171 - VAT on accounts 1xxx, 5xxx and 6xxx - AMF21';
                        VATdescription = 'VAT 2.5%';
                        VATrate = 2.5;
                        break;
                    case 'VAT 3.7% on accounts 1xxx, 5xxx and 6xxx':
                        VATaccountHead = '1171 - VAT on accounts 1xxx, 5xxx and 6xxx - AMF21';
                        VATdescription = 'VAT 3.7%';
                        VATrate = 3.7;
                        break;
                    case 'VAT 8.1% on accounts 1xxx, 5xxx and 6xxx':
                        VATaccountHead = '1171 - VAT on accounts 1xxx, 5xxx and 6xxx - AMF21';
                        VATdescription = 'VAT 8.1%';
                        VATrate = 8.1;
                        break;
                    case 'VAT 0% on accounts 4xxx':
                        VATaccountHead = '1170 - VAT on accounts 4xxx - AMF21';
                        VATdescription = 'VAT 0%';
                        VATrate = 0;
                        break;
                    case 'VAT 2.5% on accounts 4xxx':
                        VATaccountHead = '1170 - VAT on accounts 4xxx - AMF21';
                        VATdescription = 'VAT 2.5%';
                        VATrate = 2.5;
                        break;
                    case 'VAT 3.7% on accounts 4xxx':
                        VATaccountHead = '1170 - VAT on accounts 4xxx - AMF21';
                        VATdescription = 'VAT 3.7%';
                        VATrate = 3.7;
                        break;
                    case 'VAT 8.1% on accounts 4xxx':
                        VATaccountHead = '1170 - VAT on accounts 4xxx - AMF21';
                        VATdescription = 'VAT 8.1%';
                        VATrate = 8.1;
                        break;
                }

                frm.add(values.cost, values.expenseDate, values.expenseDescription, values.expenseAccount, VATaccountHead, VATrate, VATdescription, values.costCenter);
                
            },
            'Expense Entry',
            'Add',
        );
    },
    
    before_submit(frm) {
        // check attachments
        if (cur_frm.attachments.get_attachments().length === 0) {
            frappe.throw(__("Please attach the required receipts."));
        }
        // create pretax entry (only if this is approved, otherwise, server-side will trigger a validation error)
        if (frm.doc.approval_status === "Approved") {
            create_pretax_journal_entry(frm);
        }
    },
    before_cancel: function (frm) {
        cancel_pretax_journal_entry(frm);  
    },
});

function create_pretax_journal_entry(frm) {
    frappe.call({
        method: 'erpnextswiss.erpnextswiss.expenses.expense_pretax_various',
        args: {
            expense_claim: frm.doc.name
        },
        callback: function(r) {
            if (r.message) {
                frappe.show_alert("Pretax recorded: " + r.message.name);
                cur_frm.reload_doc();
            } 
        }
    });
}

function cancel_pretax_journal_entry(frm) {
    if (frm.doc.pretax_record) {
        frappe.call({
            method: 'erpnextswiss.erpnextswiss.expenses.cancel_pretax',
            args: {
                expense_claim: frm.doc.name
            },
            callback: function(r) {
                if (r.message) {
                    frappe.show_alert("pretax record cancelled. " + frm.doc.pretax_record);
                } 
            }
        });
    }
}