/*
Issue Client Custom Script
--------------------------
*/
frappe.ui.form.on('Issue', {
    setup: function(frm) {
        setupIssueContactQueries(frm);
    },

    onload: function(frm) {
        setupIssueContactQueries(frm);
        setIssueCreator(frm);
        updateInternalContactFromPerson(frm);
    },

    status: function(frm) {
        if (frm.doc.status === 'Closed' && hasField(frm, 'resolution_date_issue')) {
            frm.set_value('resolution_date_issue', frappe.datetime.get_today());
        }
    },

    before_save: function(frm) {
        validateInputSelection(frm);
        updateItemGroup(frm);
        calculatePriority(frm);
    },

    refresh: function(frm) {
        setupIssueContactQueries(frm);
        setIssueCreator(frm);
        updateInternalContactFromPerson(frm);
        updateCustomerIssue(frm);
        updateRaisedByEmail(frm);
        syncRaisedByFromCustomerContact(frm);
        addRepairInvoiceButton(frm);
    },

    customer_issue: function(frm) {
        setupIssueContactQueries(frm);
        clearRaisedByContactIfNotLinked(frm);
        clearContactNewIfNotLinked(frm);
    },

    customer: function(frm) {
        updateCustomerIssue(frm);
        setupIssueContactQueries(frm);
        clearRaisedByContactIfNotLinked(frm);
        clearContactNewIfNotLinked(frm);
    },

    raised_by_email: function(frm) {
        syncRaisedByFromCustomerContact(frm);
    },

    amf_person: function(frm) {
        updateInternalContactFromPerson(frm);
    },

    issue_type: function(frm) {
        updateProcessAndOwner(frm);
    },

    impact: calculatePriority,
    urgency: calculatePriority,
});

function hasField(frm, fieldname) {
    return Boolean(frm.fields_dict && frm.fields_dict[fieldname]);
}

function isNewDoc(frm) {
    return frm.is_new ? frm.is_new() : frm.doc.__islocal;
}

function validateInputSelection(frm) {
    if (hasField(frm, 'input_selection') && frm.doc.input_selection === '-') {
        frappe.msgprint(__("Please select an 'Input Selection' first (Customer, Supplier or Internal Issue)."));
        frappe.throw(__("Input Selection not chosen."));
    }
}

function updateItemGroup(frm) {
    if (!hasField(frm, 'item') || !hasField(frm, 'item_group') || !frm.doc.item) {
        return;
    }

    frappe.call({
        method: 'frappe.client.get',
        args: {
            doctype: 'Item',
            name: frm.doc.item
        },
        callback: function(r) {
            if (r.message) {
                frm.set_value('item_group', r.message.item_group);
            }
        }
    });
}

function updateCustomerIssue(frm) {
    if (hasField(frm, 'customer_issue') && !frm.doc.customer_issue && frm.doc.customer) {
        frm.set_value('customer_issue', frm.doc.customer);
    }
}

function setupIssueContactQueries(frm) {
    setupCustomerLinkedContactQuery(frm, 'raised_by_email');
    setupCustomerLinkedContactQuery(frm, 'contact_new');
}

function setupCustomerLinkedContactQuery(frm, fieldname) {
    if (!hasField(frm, fieldname)) {
        return;
    }

    frm.set_query(fieldname, function() {
        const customer = getIssueCustomer(frm);
        if (!customer) {
            return {
                filters: {
                    name: ['=', '']
                }
            };
        }

        return {
            query: 'frappe.contacts.doctype.contact.contact.contact_query',
            filters: {
                link_doctype: 'Customer',
                link_name: customer
            }
        };
    });
}

function setIssueCreator(frm) {
    if (!hasField(frm, 'amf_person') || frm.doc.amf_person || !isNewDoc(frm)) {
        return;
    }

    const user = frappe.session && frappe.session.user;
    if (user && user !== 'Guest') {
        frm.set_value('amf_person', user);
    }
}

function updateInternalContactFromPerson(frm) {
    if (!hasField(frm, 'amf_contact') || !frm.doc.amf_person) {
        return;
    }

    frappe.db.get_value('User', frm.doc.amf_person, 'full_name', function(r) {
        if (r && r.full_name) {
            frm.set_value('amf_contact', r.full_name);
        }
    });
}

function getIssueCustomer(frm) {
    return frm.doc.customer_issue || frm.doc.customer || null;
}

function clearRaisedByContactIfNotLinked(frm) {
    clearCustomerLinkedContactIfNotLinked(frm, 'raised_by_email');
}

function clearContactNewIfNotLinked(frm) {
    clearCustomerLinkedContactIfNotLinked(frm, 'contact_new');
}

function clearCustomerLinkedContactIfNotLinked(frm, fieldname) {
    const customer = getIssueCustomer(frm);
    if (!hasField(frm, fieldname) || !frm.doc[fieldname] || !customer) {
        return;
    }

    frappe.db.get_value('Dynamic Link', {
        parenttype: 'Contact',
        parent: frm.doc[fieldname],
        link_doctype: 'Customer',
        link_name: customer
    }, 'name', function(r) {
        if (!r || !r.name) {
            frm.set_value(fieldname, null);
        }
    });
}

function updateRaisedByEmail(frm) {
    if (!hasField(frm, 'raised_by_email') || frm.doc.raised_by_email || !frm.doc.raised_by) {
        return;
    }

    if (frm.fields_dict.raised_by_email.df.fieldtype === 'Link') {
        return;
    }

    frm.set_value('raised_by_email', frm.doc.raised_by);
}

function syncRaisedByFromCustomerContact(frm) {
    if (!hasField(frm, 'raised_by_email') || !frm.doc.raised_by_email || !hasField(frm, 'raised_by')) {
        return;
    }

    frappe.call({
        method: 'frappe.client.get',
        args: {
            doctype: 'Contact',
            name: frm.doc.raised_by_email
        },
        callback: function(r) {
            const email = getContactEmail(r.message);
            if (email) {
                frm.set_value('raised_by', email);
            }
        }
    });
}

function getContactEmail(contact) {
    if (!contact) {
        return null;
    }

    if (contact.email_id) {
        return contact.email_id;
    }

    const emails = contact.email_ids || [];
    const primary = emails.filter(function(row) {
        return row.is_primary && row.email_id;
    });
    if (primary.length) {
        return primary[0].email_id;
    }

    const first = emails.filter(function(row) {
        return row.email_id;
    });
    return first.length ? first[0].email_id : null;
}

function addRepairInvoiceButton(frm) {
    frm.add_custom_button(__('Repair Invoice'), function() {
        frm.set_value('status', 'Closed');
        frappe.route_options = {
            customer: frm.doc.customer,
            project: 'Test'
        };
        frappe.set_route('Form', 'Sales Invoice', 'New Sales Invoice 1');
    }, __('Make'));
}

function updateProcessAndOwner(frm) {
    if (!frm.doc.issue_type) {
        return;
    }

    frappe.db.get_value('Issue Type', frm.doc.issue_type, ['process', 'process_owner'], function(r) {
        if (!r) {
            return;
        }
        if (hasField(frm, 'process_involved')) {
            frm.set_value('process_involved', r.process || null);
        }
        if (hasField(frm, 'process_owner')) {
            frm.set_value('process_owner', r.process_owner || null);
        }
    });
}

function calculatePriority(frm) {
    if (!hasField(frm, 'priority_result')) {
        return;
    }

    const impactValue = getPriorityValue(frm.doc.impact);
    const urgencyValue = getPriorityValue(frm.doc.urgency);
    if (!impactValue || !urgencyValue) {
        return;
    }

    frm.set_value('priority_result', getPriorityLabel(impactValue + urgencyValue));
}

function getPriorityValue(level) {
    const values = {
        Low: 1,
        Medium: 2,
        High: 3,
        Critical: 4
    };
    return values[level];
}

function getPriorityLabel(numericPriority) {
    const priorityLabels = {
        2: 'Priority 5 - Planning',
        3: 'Priority 4 - Low',
        4: 'Priority 3 - Moderate',
        5: 'Priority 2 - High',
        6: 'Priority 1 - Critical',
        7: 'Priority 1 - Critical',
        8: 'Priority 1 - Critical'
    };
    return priorityLabels[numericPriority] || '';
}
