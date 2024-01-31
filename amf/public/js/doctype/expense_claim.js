/*
Expense Claim Client Custom Script
----------------------------------
*/
frappe.ui.form.on("Expense Claim", {
    refresh: function (frm) {
        frm.add_custom_button(__('Add Expense'), function () {
            promptForExpenseEntry(frm);
        });
    },

    add_expense: function (frm) {
        frappe.prompt(getExpensePromptFields(), function (values) {
            const vatDetails = getVATDetails(values.vat);
            frm.addExpenseEntry({ ...values, ...vatDetails });
        }, 'Expense Entry', 'Add');
    },

    before_submit: function (frm) {
        if (frm.doc.approval_status === "Approved" && cur_frm.attachments.get_attachments().length === 0) {
            frappe.throw(__("Please attach the required receipts."));
        }
        createPretaxJournalEntry(frm);
    },

    before_cancel: function (frm) {
        cancelPretaxJournalEntry(frm);
    },
});

// Function to prompt for expense entry
function promptForExpenseEntry(frm) {
    frm.add_expense(frm);
}

// Function to get fields for the expense prompt
function getExpensePromptFields() {
    return [
        {
            fieldname: 'expenseDate',
            fieldtype: 'Date',
            label: __('Expense Date'),
            reqd: 1,
            default: frappe.datetime.nowdate(),
        },
        {
            fieldname: 'cost',
            fieldtype: 'Currency',
            label: __('Expense Cost'),
            reqd: 1
        },
        {
            fieldname: 'expenseAccount',
            fieldtype: 'Link',
            label: __('Expense Account'),
            options: 'Expense Claim Type',
            reqd: 1
        },
        {
            fieldname: 'vat',
            fieldtype: 'Select',
            label: __('VAT'),
            options: [
                'VAT 0% on accounts 1xxx, 5xxx and 6xxx',
                'VAT 2.5% on accounts 1xxx, 5xxx and 6xxx',
                'VAT 3.7% on accounts 1xxx, 5xxx and 6xxx',
                'VAT 8.1% on accounts 1xxx, 5xxx and 6xxx',
                'VAT 0% on accounts 4xxx',
                'VAT 2.5% on accounts 4xxx',
                'VAT 3.7% on accounts 4xxx',
                'VAT 8.1% on accounts 4xxx'
            ].join('\n'),
            reqd: 1
        },
        {
            fieldname: 'expenseDescription',
            fieldtype: 'Small Text',
            label: __('Description'),
            reqd: 1
        },
        {
            fieldname: 'costCenter',
            fieldtype: 'Select',
            label: __('Cost Center'),
            options: [
                'General - AMF21',
                'Automation - AMF21',
                'Patch - AMF21'
            ].join('\n'),
            reqd: 1
        }
    ];
}

// Function to get VAT details based on the selection
function getVATDetails(vatOption) {
    // Define a mapping object where each VAT option is mapped to its details
    const vatDetailsMapping = {
        'VAT 0% on accounts 1xxx, 5xxx and 6xxx': {
            VATaccountHead: '1171 - VAT on accounts 1xxx, 5xxx and 6xxx - AMF21',
            VATrate: 0,
            VATdescription: 'VAT 0%'
        },
        'VAT 2.5% on accounts 1xxx, 5xxx and 6xxx': {
            VATaccountHead: '1171 - VAT on accounts 1xxx, 5xxx and 6xxx - AMF21',
            VATrate: 2.5,
            VATdescription: 'VAT 2.5%'
        },
        'VAT 3.7% on accounts 1xxx, 5xxx and 6xxx': {
            VATaccountHead: '1171 - VAT on accounts 1xxx, 5xxx and 6xxx - AMF21',
            VATrate: 3.7,
            VATdescription: 'VAT 3.7%'
        },
        'VAT 8.1% on accounts 1xxx, 5xxx and 6xxx': {
            VATaccountHead: '1171 - VAT on accounts 1xxx, 5xxx and 6xxx - AMF21',
            VATrate: 8.1,
            VATdescription: 'VAT 8.1%'
        },
        'VAT 0% on accounts 4xxx': {
            VATaccountHead: '1170 - VAT on accounts 4xxx - AMF21',
            VATrate: 0,
            VATdescription: 'VAT 0%'
        },
        'VAT 2.5% on accounts 4xxx': {
            VATaccountHead: '1170 - VAT on accounts 4xxx - AMF21',
            VATrate: 2.5,
            VATdescription: 'VAT 2.5%'
        },
        'VAT 3.7% on accounts 4xxx': {
            VATaccountHead: '1170 - VAT on accounts 4xxx - AMF21',
            VATrate: 3.7,
            VATdescription: 'VAT 3.7%'
        },
        'VAT 8.1% on accounts 4xxx': {
            VATaccountHead: '1170 - VAT on accounts 4xxx - AMF21',
            VATrate: 8.1,
            VATdescription: 'VAT 8.1%'
        }
    };

    // Check if the selected VAT option is in the mapping
    if (vatDetailsMapping[vatOption]) {
        return vatDetailsMapping[vatOption];
    } else {
        // If the VAT option is not found in the mapping, return a default object
        return {
            VATaccountHead: '',
            VATrate: 0,
            VATdescription: 'VAT Option Not Recognized'
        };
    }
}



// Function to add an expense entry
frappe.ui.form.on("Expense Claim", {
    addExpenseEntry: function ({ cost, expenseDate, expenseDescription, expenseAccount, VATaccountHead, VATrate, VATdescription, costCenter }) {
        this.frm.doc.cost_center = costCenter;

        const [expenseCost, VATcost] = calculateCosts(cost, VATrate);

        const expense = this.frm.add_child("expenses");
        setExpenseFields(expense, { expenseDate, expenseDescription, expenseAccount, cost, VATaccountHead, VATcost });

        this.frm.refresh_field("expenses");
    },
});

// Function to calculate costs (expense cost and VAT cost)
function calculateCosts(cost, VATrate) {
    const expenseCost = roundNumber(cost * 100 / (100 + VATrate), 2);
    const VATcost = roundNumber(cost - expenseCost, 2);
    return [expenseCost, VATcost];
}

// Function to set fields for an expense
function setExpenseFields(expense, fields) {
    Object.entries(fields).forEach(([key, value]) => {
        frappe.model.set_value(expense.doctype, expense.name, key, value);
    });
}

// Function to create a pretax journal entry
function createPretaxJournalEntry(frm) {
    frappe.call({
        method: 'erpnextswiss.erpnextswiss.expenses.expense_pretax_various',
        args: { expense_claim: frm.doc.name },
        callback: function (r) {
            if (r.message) {
                frappe.show_alert("Pretax recorded: " + r.message.name);
                frm.reload_doc();
            }
        },
        error: function (err) {
            frappe.show_alert({ message: __("Failed to create pretax journal entry: ") + err.message, indicator: 'red' });
        }
    });
}

// Function to cancel a pretax journal entry
function cancelPretaxJournalEntry(frm) {
    if (frm.doc.pretax_record) {
        frappe.call({
            method: 'erpnextswiss.erpnextswiss.expenses.cancel_pretax',
            args: { expense_claim: frm.doc.name },
            callback: function (r) {
                if (r.message) {
                    frappe.show_alert("Pretax record cancelled: " + frm.doc.pretax_record);
                }
            },
            error: function (err) {
                frappe.show_alert({ message: __("Failed to cancel pretax journal entry: ") + err.message, indicator: 'red' });
            }
        });
    }
}

// Utility function to round a number to a specific number of decimal places
function roundNumber(num, decimalPlaces) {
    return +(Math.round(num + "e+" + decimalPlaces) + "e-" + decimalPlaces);
}