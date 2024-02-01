/*
Issue Client Custom Script
--------------------------
*/
frappe.ui.form.on('Issue', {
    status: function(frm) {
        if (frm.doc.status === 'Closed') {
            frm.set_value('resolution_date_issue', frappe.datetime.get_today());
        }
    },

    before_save: function(frm) {
        validateInputSelection(frm);
        updateItemGroup(frm);
    },

    refresh: function(frm) {
        updateCustomerIssue(frm);
        updateRaisedByEmail(frm);
        addRepairInvoiceButton(frm);
    },

    issue_type: function(frm) {
        updateProcessAndOwner(frm);
    },

    impact: calculate_priority,
    urgency: calculate_priority,
});

function validateInputSelection(frm) {
    if (frm.doc.input_selection === "-") {
        frappe.msgprint(__("Please select an 'Input Selection' first (Customer, Supplier or Internal Issue)."));
        frappe.throw(__("Input Selection not chosen.")); // This will prevent the document from saving
    }
}

function updateItemGroup(frm) {
    let item_code = frm.doc.item;
    if (item_code) {
        frappe.call({
            method: "frappe.client.get",
            args: {
                doctype: "Item",
                name: item_code
            },
            callback: (r) => {
                if (r.message) {
                    frm.set_value('item_group', r.message.item_group);
                }
            },
            error: (error) => {
                console.error('Error fetching item details:', error);
            }
        });
    }
}

function updateCustomerIssue(frm) {
    if (!frm.doc.customer_issue && frm.doc.customer) {
        frm.set_value('customer_issue', frm.doc.customer);
    }
}

function updateRaisedByEmail(frm) {
    if (!frm.doc.raised_by_email && frm.doc.raised_by) {
        frm.set_value('raised_by_email', frm.doc.raised_by);
    }
}

function addRepairInvoiceButton(frm) {
    frm.add_custom_button(__('Repair Invoice'), function() {
        frm.set_value('status', "Closed");
        frappe.route_options = {
            'customer': frm.doc.customer,
            'project': "Test"
        };
        frappe.set_route('Form', 'Sales Invoice', 'New Sales Invoice 1');
    }, __("Make"));
}

function updateProcessAndOwner(frm) {
    if (frm.doc.issue_type) {
        frappe.db.get_value('Issue Type', frm.doc.issue_type, ['process', 'process_owner'], (r) => {
            if (r) {
                frm.set_value('process_involved', r.process || null);
                frm.set_value('process_owner', r.process_owner || null);
            }
        });
    }
}

function calculate_priority(frm) {
    const impact = frm.doc.impact;
    const urgency = frm.doc.urgency;

    if (impact && urgency) {
        const impact_value = get_value(impact);
        const urgency_value = get_value(urgency);
        const priority = impact_value + urgency_value;
        const priority_label = get_priority_label(priority);
        frm.set_value('priority_result', priority_label);
    }
}

function get_value(level) {
    const values = {
        'Low': 1,
        'Medium': 2,
        'High': 3,
        'Critical': 4
    };
    return values[level];
}

function get_priority_label(numeric_priority) {
    const priority_labels = {
        2: 'Priority 5 - Planning',
        3: 'Priority 4 - Low',
        4: 'Priority 3 - Moderate',
        5: 'Priority 2 - High',
        6: 'Priority 1 - Critical',
        7: 'Priority 1 - Critical'
    };
    return priority_labels[numeric_priority];
}
