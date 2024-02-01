/*
Issue Script
------------------
What this does:
* Adds a custom button in header
* Custom button opens Sales Invoice
* ON_GOING: Automatically fill Naming Series, Customer, Check Update Stock, Items Table
* TODO: set cost to 0 in SINV if underguarantee checked in Issue
* TODO: automatically put total in Issue

*/

frappe.ui.form.on('Issue', 'status', function(frm) {
    if (frm.doc.status === 'Closed') {
        // Set resolution_date_issue to the current date
        frm.set_value('resolution_date_issue', frappe.datetime.get_today());
    }
});

frappe.ui.form.on('Issue', {
    
    before_save: function(frm) {
        if (frm.doc.input_selection === "-") {
            frappe.msgprint("Please select an 'Input Selection' first (Customer, Supplier or Internal Issue).");
            throw new Error("Input Selection not chosen.");  // This will prevent the document from saving
        }
        var item_code = frm.doc.item;

        if(item_code) {
            frappe.call({
                method: "frappe.client.get",
                args: {
                    doctype: "Item",
                    name: item_code
                },
                callback: function(r) {
                    if(r.message) {
                        frm.set_value('item_group', r.message.item_group);
                    }
                }
            });
        }
    },
    
    refresh: function(frm) {
        if (!frm.doc.customer_issue && frm.doc.customer) {
            frm.set_value('customer_issue', frm.doc.customer);
            //frm.save();
        }
        if (!frm.doc.raised_by_email && frm.doc.raised_by) {
            frm.set_value('raised_by_email', frm.doc.raised_by);
            //frm.save();
        }
        
        frm.add_custom_button(__('Repair Invoice'), function() {
	        frm.doc.status = "Closed";
	        frappe.route_options = {
        		'customer': frm.doc.customer,
        		'project': "Test"
	        };
	        frappe.set_route('Form','Sales Invoice','New Sales Invoice 1');
        }, __("Make"));
    },
    
    issue_type: function(frm) {
        // Check if issue_type has been set
        if (frm.doc.issue_type) {
            // Fetch the corresponding 'process' and 'process_owner' from the 'Issue Type' DocType
            frappe.db.get_value('Issue Type', frm.doc.issue_type, ['process', 'process_owner'], function(r) {
                if (r) {
                    // Set the 'process_involved' field with the fetched 'process' value
                    if (r.process) {
                        frm.set_value('process_involved', r.process);
                    } else {
                        frm.set_value('process_involved', null);
                    }
                    // Set the 'process_owner' field with the fetched 'process_owner' value
                    if (r.process_owner) {
                        frm.set_value('process_owner', r.process_owner);
                    } else {
                        frm.set_value('process_owner', null);
                    }
                }
            });
        }
    },
    
    impact: function(frm) {calculate_priority(frm);},
    urgency: function(frm) {calculate_priority(frm);},
});

function calculate_priority(frm) {
    let impact = frm.doc.impact;
    let urgency = frm.doc.urgency;

    let impact_value = get_value(impact);
    let urgency_value = get_value(urgency);

    if(impact_value && urgency_value) {
        let priority = impact_value + urgency_value;
        let priority_label = get_priority_label(priority);
        frm.set_value('priority_result', priority_label);
    }
}

function get_value(level) {
    let values = {
        'Low': 1,
        'Medium': 2,
        'High': 3,
        'Critical': 4
    };
    return values[level];
}

function get_priority_label(numeric_priority) {
    let priority_labels = {
        2: 'Priority 5 - Planning',
        3: 'Priority 4 - Low',
        4: 'Priority 3 - Moderate',
        5: 'Priority 2 - High',
        6: 'Priority 1 - Critical',
        7: 'Priority 1 - Critical'
    };
    return priority_labels[numeric_priority];
}