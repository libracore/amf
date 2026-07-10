/*
Issue Client Custom Script
--------------------------
*/
frappe.ui.form.on('AMF Issue Test', {
    setup: function(frm) {
        setupIssueContactQueries(frm);
    },

    onload: function(frm) {
        setupIssueContactQueries(frm);
        setIssueCreator(frm);
        updateInternalContactFromPerson(frm);
        fetchIssueItemsIfEmpty(frm);
    },

    status: function(frm) {
        if (frm.doc.status === 'Closed' && hasField(frm, 'resolution_date_issue')) {
            frm.set_value('resolution_date_issue', frappe.datetime.get_today());
        }
        updateLifecycleStage(frm);
    },

    before_save: function(frm) {
        validateInputSelection(frm);
        updateItemGroup(frm);
        updatePriority(frm);
        updateRootCauseAnalysis(frm);
        updateLifecycleStage(frm);
    },

    refresh: function(frm) {
        setupIssueContactQueries(frm);
        setIssueCreator(frm);
        updateInternalContactFromPerson(frm);
        updateCustomerIssue(frm);
        fetchIssueItemsIfEmpty(frm);
        syncRaisedByFromCustomerContact(frm);
        addRepairInvoiceButton(frm);
        addRootCauseButtons(frm);
        updatePriority(frm, false);
    },

    issue_type: function(frm) {
        updateProcessAndOwner(frm);
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

    sales_order: function(frm) {
        fetchIssueItemsFromLinkedDocument(frm);
    },

    delivery_note: function(frm) {
        fetchIssueItemsFromLinkedDocument(frm);
    },

    raised_by_email: function(frm) {
        syncRaisedByFromCustomerContact(frm);
    },

    amf_person: function(frm) {
        updateInternalContactFromPerson(frm);
    },

    impact: updatePriority,
    urgency: updatePriority,
    root_cause_analysis_method: function(frm) {
        if (frm.doc.root_cause_analysis_method === '5 Whys') {
            ensureFiveWhysRows(frm);
        }
    },
    root_cause_whys_on_form_rendered: function(frm) {
        const grid_row = frappe.ui.form.get_open_grid_form();
        if (
            grid_row &&
            grid_row.doc &&
            grid_row.doc.parentfield === 'root_cause_whys'
        ) {
            updateWhyQuestionDescription(frm, grid_row.doc.doctype, grid_row.doc.name);
        }
    },
    effectiveness_result: function(frm) {
        updateRootCauseAnalysis(frm);
    },
});

frappe.ui.form.on('AMF Issue Test Root Cause Why', {
    form_render: function(frm, cdt, cdn) {
        updateWhyQuestionDescription(frm, cdt, cdn);
    },
    root_cause_whys_add: function(frm, cdt, cdn) {
        normalizeWhyRow(frm, cdt, cdn);
        updateWhyQuestionDescription(frm, cdt, cdn);
        updateRootCauseAnalysis(frm);
    },
    why_question: function(frm, cdt, cdn) {
        updateWhyQuestionDescription(frm, cdt, cdn);
    },
    cause_statement: function(frm) {
        updateRootCauseAnalysis(frm);
    },
    evidence: function(frm) {
        updateRootCauseAnalysis(frm);
    },
    validated: function(frm) {
        updateRootCauseAnalysis(frm);
    },
    is_root_cause: function(frm, cdt, cdn) {
        keepSingleRootCause(frm, cdt, cdn);
        syncRootCauseStatementFromSelectedRow(frm, true);
        updateRootCauseAnalysis(frm);
    },
    cause_type: function(frm) {
        updateRootCauseAnalysis(frm);
    },
});

function validateInputSelection(frm) {
    if (hasField(frm, 'input_selection') && frm.doc.input_selection === "-") {
        frappe.msgprint(__("Please select an 'Input Selection' first (Customer, Supplier or Internal Issue)."));
        frappe.throw(__("Input Selection not chosen.")); // This will prevent the document from saving
    }
}

function updateItemGroup(frm) {
    if (!hasField(frm, 'item') || !hasField(frm, 'item_group')) {
        return;
    }

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

function fetchIssueItemsIfEmpty(frm) {
    if (!hasField(frm, 'issue_items') || (frm.doc.issue_items || []).length) {
        return;
    }

    if (!getIssueItemsSource(frm)) {
        return;
    }

    fetchIssueItemsFromLinkedDocument(frm);
}

function fetchIssueItemsFromLinkedDocument(frm) {
    if (!hasField(frm, 'issue_items')) {
        return;
    }

    const source = getIssueItemsSource(frm);
    if (!source) {
        clearIssueItems(frm);
        return;
    }

    frappe.call({
        method: 'frappe.client.get',
        args: {
            doctype: source.doctype,
            name: source.name
        },
        callback: function(r) {
            const current_source = getIssueItemsSource(frm);
            if (
                !current_source ||
                current_source.doctype !== source.doctype ||
                current_source.name !== source.name
            ) {
                return;
            }

            fillIssueItemsFromSource(frm, r.message);
        }
    });
}

function getIssueItemsSource(frm) {
    if (frm.doc.delivery_note) {
        return {
            doctype: 'Delivery Note',
            name: frm.doc.delivery_note
        };
    }

    if (frm.doc.sales_order) {
        return {
            doctype: 'Sales Order',
            name: frm.doc.sales_order
        };
    }

    return null;
}

function fillIssueItemsFromSource(frm, source_doc) {
    clearIssueItems(frm);

    (source_doc && source_doc.items || []).forEach((source_row) => {
        const row = frm.add_child('issue_items');
        row.item_code = source_row.item_code || '';
        row.item_name = source_row.item_name || '';
        row.quantity = source_row.qty || 0;
        row.serial_no = source_row.serial_no || '';
        row.batch_no = source_row.batch_no || '';
    });

    frm.refresh_field('issue_items');
}

function clearIssueItems(frm) {
    if (!hasField(frm, 'issue_items')) {
        return;
    }

    frm.clear_table('issue_items');
    frm.refresh_field('issue_items');
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

function clearCustomerLinkedContactIfNotLinked(frm, fieldname, after_clear) {
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
            if (after_clear) {
                after_clear();
            }
        }
    });
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
    const primary = emails.filter((row) => row.is_primary && row.email_id);
    if (primary.length) {
        return primary[0].email_id;
    }

    const first = emails.filter((row) => row.email_id);
    return first.length ? first[0].email_id : null;
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
                if (hasField(frm, 'process_involved')) {
                    frm.set_value('process_involved', r.process || null);
                }
                if (hasField(frm, 'process_owner')) {
                    frm.set_value('process_owner', r.process_owner || null);
                }
            }
        });
    }
}

const PRIORITY_LEVELS = ['Low', 'Medium', 'High'];

const PRIORITY_MATRIX = {
    Low: {
        Low: 'P3 - Routine Follow-Up',
        Medium: 'P3 - Routine Follow-Up',
        High: 'P2 - Controlled Action'
    },
    Medium: {
        Low: 'P3 - Routine Follow-Up',
        Medium: 'P2 - Controlled Action',
        High: 'P1 - Immediate Containment'
    },
    High: {
        Low: 'P2 - Controlled Action',
        Medium: 'P1 - Immediate Containment',
        High: 'P1 - Immediate Containment'
    }
};

const PRIORITY_DEFINITIONS = {
    'P1 - Immediate Containment': {
        short_label: 'P1',
        color: '#b42318',
        background: '#fee4e2',
        border: '#fda29b',
        explanation: 'Immediate containment or decision is required. Assign clear ownership, protect the customer or next process, and treat RCA as normally required.',
        action: 'Act today. Escalate when ownership, containment, or customer communication is unclear.'
    },
    'P2 - Controlled Action': {
        short_label: 'P2',
        color: '#b54708',
        background: '#fef0c7',
        border: '#fdb022',
        explanation: 'The issue is significant enough to plan and control actively, but it is not necessarily a same-day crisis.',
        action: 'Assign an owner and due date. Use RCA when the issue is recurrent, customer-facing, or process-related.'
    },
    'P3 - Routine Follow-Up': {
        short_label: 'P3',
        color: '#027a48',
        background: '#dcfae6',
        border: '#75e0a7',
        explanation: 'The issue can be handled through normal follow-up if facts remain low-risk and isolated.',
        action: 'Document the correction and close cleanly. Escalate if repetition or hidden customer risk appears.'
    }
};

const IMPACT_EXPLANATIONS = {
    Low: 'Limited consequence: local inconvenience, easy correction, no confirmed customer or product-conformity risk.',
    Medium: 'Meaningful consequence: rework, delay, supplier/customer touch point, cost, or limited conformity risk.',
    High: 'Serious consequence: customer dissatisfaction, product conformity, delivery promise, safety/regulatory exposure, significant cost, or recurrence risk.'
};

const URGENCY_EXPLANATIONS = {
    Low: 'Can wait for normal planning without creating additional risk.',
    Medium: 'Needs planned action soon because delay may create rework, disruption, or dissatisfaction.',
    High: 'Needs immediate containment, decision, or escalation to prevent additional nonconforming output or customer impact.'
};

function updatePriority(frm, updateField) {
    const priority = getPriorityDefinition(frm.doc.impact, frm.doc.urgency);
    const priority_label = priority ? priority.label : '';

    if (updateField !== false && hasField(frm, 'priority_result') && frm.doc.priority_result !== priority_label) {
        frm.set_value('priority_result', priority_label);
    }

    renderPriorityHeatmap(frm, priority);
}

function getPriorityDefinition(impact, urgency) {
    const normalized_impact = normalizePriorityLevel(impact);
    const normalized_urgency = normalizePriorityLevel(urgency);
    if (!normalized_impact || !normalized_urgency) {
        return null;
    }

    const label = PRIORITY_MATRIX[normalized_urgency] &&
        PRIORITY_MATRIX[normalized_urgency][normalized_impact];
    if (!label) {
        return null;
    }

    const definition = PRIORITY_DEFINITIONS[label];
    return {
        label: label,
        impact: normalized_impact,
        urgency: normalized_urgency,
        short_label: definition.short_label,
        color: definition.color,
        background: definition.background,
        border: definition.border,
        explanation: definition.explanation,
        action: definition.action
    };
}

function normalizePriorityLevel(value) {
    if (value === 'Critical') {
        return 'High';
    }

    return PRIORITY_LEVELS.indexOf(value) !== -1 ? value : null;
}

function renderPriorityHeatmap(frm, priority) {
    if (!hasField(frm, 'priority_heatmap')) {
        return;
    }

    const selected_impact = normalizePriorityLevel(frm.doc.impact);
    const selected_urgency = normalizePriorityLevel(frm.doc.urgency);
    frm.fields_dict.priority_heatmap.$wrapper.html(
        buildPriorityHeatmapHtml(selected_impact, selected_urgency, priority)
    );
}

function buildPriorityHeatmapHtml(selected_impact, selected_urgency, priority) {
    const urgency_rows = ['High', 'Medium', 'Low'];
    const impact_columns = ['Low', 'Medium', 'High'];
    const status_text = priority ?
        `${priority.label}: ${priority.explanation}` :
        'Select Impact and Urgency to position this Issue on the matrix.';
    const action_text = priority ? priority.action : 'Impact measures consequence. Urgency measures time pressure.';
    const impact_help = selected_impact ? IMPACT_EXPLANATIONS[selected_impact] : 'Select the consequence level.';
    const urgency_help = selected_urgency ? URGENCY_EXPLANATIONS[selected_urgency] : 'Select the required reaction speed.';

    let cells = '<div class="amf-priority-axis"></div>';
    impact_columns.forEach((impact) => {
        cells += `<div class="amf-priority-axis amf-priority-axis-top">Impact ${escapeHtml(impact)}</div>`;
    });

    urgency_rows.forEach((urgency) => {
        cells += `<div class="amf-priority-axis amf-priority-axis-left">Urgency ${escapeHtml(urgency)}</div>`;
        impact_columns.forEach((impact) => {
            const label = PRIORITY_MATRIX[urgency][impact];
            const definition = PRIORITY_DEFINITIONS[label];
            const selected = urgency === selected_urgency && impact === selected_impact;
            const cell_text = label.replace(`${definition.short_label} - `, '');
            cells += [
                `<div class="amf-priority-cell${selected ? ' selected' : ''}"`,
                ` style="background:${definition.background};border-color:${definition.border};color:${definition.color};">`,
                `<div class="amf-priority-cell-label">${escapeHtml(definition.short_label)}</div>`,
                `<div class="amf-priority-cell-text">${escapeHtml(cell_text)}</div>`,
                selected ? '<div class="amf-priority-marker">This issue</div>' : '',
                '</div>'
            ].join('');
        });
    });

    return `
        <style>
            .amf-priority-heatmap {
                margin: 8px 0 16px;
                max-width: 760px;
                font-size: 12px;
                line-height: 1.35;
            }
            .amf-priority-summary {
                margin-bottom: 10px;
                padding: 10px 12px;
                border: 1px solid #d0d5dd;
                border-radius: 6px;
                background: #f9fafb;
            }
            .amf-priority-summary strong {
                display: block;
                margin-bottom: 4px;
                color: #1f2937;
            }
            .amf-priority-grid {
                display: grid;
                grid-template-columns: 96px repeat(3, minmax(120px, 1fr));
                gap: 4px;
            }
            .amf-priority-axis {
                min-height: 28px;
                display: flex;
                align-items: center;
                justify-content: center;
                color: #475467;
                font-weight: 600;
                text-align: center;
            }
            .amf-priority-axis-left {
                justify-content: flex-end;
                padding-right: 8px;
            }
            .amf-priority-axis-top {
                border-bottom: 1px solid #eaecf0;
            }
            .amf-priority-cell {
                min-height: 86px;
                border: 1px solid;
                border-radius: 6px;
                padding: 8px;
                position: relative;
                text-align: center;
            }
            .amf-priority-cell.selected {
                outline: 3px solid #2563eb;
                outline-offset: 1px;
                box-shadow: 0 0 0 2px #ffffff inset;
            }
            .amf-priority-cell-label {
                font-size: 17px;
                font-weight: 700;
                margin-bottom: 3px;
            }
            .amf-priority-cell-text {
                font-weight: 600;
            }
            .amf-priority-marker {
                margin-top: 5px;
                display: inline-block;
                padding: 2px 6px;
                border-radius: 999px;
                background: #ffffff;
                color: #1d4ed8;
                font-weight: 700;
            }
            .amf-priority-help {
                margin-top: 10px;
                color: #475467;
            }
            @media (max-width: 767px) {
                .amf-priority-grid {
                    grid-template-columns: 80px repeat(3, minmax(82px, 1fr));
                }
                .amf-priority-cell {
                    min-height: 96px;
                    padding: 6px;
                }
            }
        </style>
        <div class="amf-priority-heatmap">
            <div class="amf-priority-summary">
                <strong>${escapeHtml(status_text)}</strong>
                <span>${escapeHtml(action_text)}</span>
            </div>
            <div class="amf-priority-grid">${cells}</div>
            <div class="amf-priority-help">
                <div><strong>Impact:</strong> ${escapeHtml(impact_help)}</div>
                <div><strong>Urgency:</strong> ${escapeHtml(urgency_help)}</div>
            </div>
        </div>
    `;
}

const DEFAULT_WHY_ROWS = [
    {
        question: 'Why did the issue occur?',
        cause_type: 'Symptom',
        description: 'Captures the visible problem or failure mode. Describe what was observed before jumping to a cause.'
    },
    {
        question: 'Why was that condition possible?',
        cause_type: 'Direct Cause',
        description: 'Identifies the immediate technical or operational cause that allowed the symptom to happen.'
    },
    {
        question: 'Why did the process or control not prevent it?',
        cause_type: 'Process Cause',
        description: 'Checks the prevention control: why the process, ERP control, review, training, or instruction did not prevent the event.'
    },
    {
        question: 'Why was the weakness not detected earlier?',
        cause_type: 'Escape Cause',
        description: 'Checks the escape cause: why inspection, review, ERP control, or communication did not detect the weakness earlier.'
    },
    {
        question: 'Why does the management system allow this recurrence risk?',
        cause_type: 'System Cause',
        description: 'Identifies the system cause: procedure, ownership, competence, tooling, KPI, supplier control, document control, or resource gap that allows recurrence.'
    }
];

function addRootCauseButtons(frm) {
    if (!hasField(frm, 'root_cause_whys')) {
        return;
    }

    frm.add_custom_button(__('Start 5 Whys'), function() {
        ensureFiveWhysRows(frm);
    }, __('Root Cause'));

    frm.add_custom_button(__('Use Selected Root Cause'), function() {
        syncRootCauseStatementFromSelectedRow(frm, true);
        updateRootCauseAnalysis(frm);
    }, __('Root Cause'));
}

function ensureFiveWhysRows(frm) {
    if (!hasField(frm, 'root_cause_whys')) {
        return;
    }

    if (hasField(frm, 'root_cause_analysis_method') && !frm.doc.root_cause_analysis_method) {
        frm.set_value('root_cause_analysis_method', '5 Whys');
    }

    const rows = frm.doc.root_cause_whys || [];
    for (let i = rows.length; i < DEFAULT_WHY_ROWS.length; i++) {
        const definition = DEFAULT_WHY_ROWS[i];
        const row = frm.add_child('root_cause_whys');
        row.cause_type = definition.cause_type;
        row.why_question = definition.question;
    }

    normalizeWhyRows(frm);
    frm.refresh_field('root_cause_whys');
    updateRootCauseAnalysis(frm);
}

function normalizeWhyRow(frm, cdt, cdn) {
    const row = locals[cdt] && locals[cdt][cdn];
    if (!row) {
        return;
    }

    const rows = frm.doc.root_cause_whys || [];
    const idx = rows.findIndex((candidate) => candidate.name === cdn) + 1;
    const definition = getDefaultWhyDefinition(idx);
    if (!definition) {
        return;
    }
    if (!row.cause_type || isOldGeneratedCauseType(row, idx)) {
        frappe.model.set_value(cdt, cdn, 'cause_type', definition.cause_type);
    }
    if (!row.why_question) {
        frappe.model.set_value(cdt, cdn, 'why_question', definition.question);
    }
}

function normalizeWhyRows(frm) {
    (frm.doc.root_cause_whys || []).forEach((row, index) => {
        const definition = getDefaultWhyDefinition(index + 1);
        if (!definition) {
            return;
        }
        if (!row.cause_type || isOldGeneratedCauseType(row, index + 1)) {
            row.cause_type = definition.cause_type;
        }
        if (!row.why_question) {
            row.why_question = definition.question;
        }
    });
}

function getDefaultWhyDefinition(whyNumber) {
    if (whyNumber <= 0 || whyNumber > DEFAULT_WHY_ROWS.length) {
        return null;
    }

    return DEFAULT_WHY_ROWS[whyNumber - 1];
}

function updateWhyQuestionDescription(frm, cdt, cdn) {
    const row = locals[cdt] && locals[cdt][cdn];
    if (!row || !hasField(frm, 'root_cause_whys')) {
        return;
    }

    const grid = frm.fields_dict.root_cause_whys.grid;
    const grid_row = grid && grid.grid_rows_by_docname && grid.grid_rows_by_docname[row.name];
    const field = grid_row && grid_row.grid_form && grid_row.grid_form.fields_dict.why_question;
    if (!field || !field.set_description) {
        return;
    }

    field.set_description(getWhyQuestionDescription(row));
}

function getWhyQuestionDescription(row) {
    const question = normalizeQuestion(row.why_question);
    const definition = DEFAULT_WHY_ROWS.find((candidate) => {
        return normalizeQuestion(candidate.question) === question;
    });

    return definition ? definition.description : '';
}

function normalizeQuestion(value) {
    return (value || '').replace(/\s+/g, ' ').trim();
}

function isOldGeneratedCauseType(row, whyNumber) {
    const definition = getDefaultWhyDefinition(whyNumber);
    return Boolean(
        definition &&
        whyNumber === 4 &&
        row.why_question === definition.question &&
        row.cause_type === 'System Cause'
    );
}

function keepSingleRootCause(frm, cdt, cdn) {
    const selected = locals[cdt] && locals[cdt][cdn];
    if (!selected || !selected.is_root_cause) {
        return;
    }

    (frm.doc.root_cause_whys || []).forEach((row) => {
        if (row.name !== cdn && row.is_root_cause) {
            frappe.model.set_value(row.doctype, row.name, 'is_root_cause', 0);
        }
    });
}

function syncRootCauseStatementFromSelectedRow(frm, force) {
    if (!hasField(frm, 'root_cause_statement')) {
        return;
    }

    const selected = getSelectedRootCauseRow(frm);
    if (!selected || !selected.cause_statement) {
        return;
    }

    if (force || !frm.doc.root_cause_statement) {
        frm.set_value('root_cause_statement', selected.cause_statement);
    }
}

function getSelectedRootCauseRow(frm) {
    const selected = (frm.doc.root_cause_whys || []).filter((row) => {
        return row.is_root_cause && row.cause_statement;
    });

    return selected.length ? selected[selected.length - 1] : null;
}

function updateRootCauseAnalysis(frm) {
    if (!hasField(frm, 'root_cause_analysis_status')) {
        return;
    }

    normalizeWhyRows(frm);
    syncRootCauseStatementFromSelectedRow(frm, false);

    const status = calculateRootCauseStatus(frm);
    if (frm.doc.root_cause_analysis_status !== status) {
        frm.set_value('root_cause_analysis_status', status);
    }
}

function calculateRootCauseStatus(frm) {
    if (frm.doc.effectiveness_result === 'Effective') {
        return 'Verified';
    }

    if (frm.doc.root_cause_statement || getSelectedRootCauseRow(frm)) {
        return 'Root Cause Identified';
    }

    const has_analysis = Boolean(frm.doc.root_cause_description) ||
        (frm.doc.root_cause_whys || []).some((row) => {
            return Boolean(row.cause_statement || row.evidence);
        });

    return has_analysis ? 'In Progress' : 'Not Started';
}

function updateLifecycleStage(frm) {
    if (!hasField(frm, 'issue_lifecycle_stage')) {
        return;
    }

    if (frm.doc.status === 'Closed') {
        frm.set_value('issue_lifecycle_stage', 'Closed');
    } else if (frm.doc.effectiveness_result === 'Effective') {
        frm.set_value('issue_lifecycle_stage', 'Effectiveness Check');
    } else if (frm.doc.corrective_action || frm.doc.preventive_action) {
        frm.set_value('issue_lifecycle_stage', 'Correction');
    } else if (frm.doc.root_cause_statement || frm.doc.root_cause_description) {
        frm.set_value('issue_lifecycle_stage', 'Root Cause Analysis');
    } else if (frm.doc.immediate_containment_action) {
        frm.set_value('issue_lifecycle_stage', 'Containment');
    }
}

function hasField(frm, fieldname) {
    return Boolean(frm.fields_dict && frm.fields_dict[fieldname]);
}

function isNewDoc(frm) {
    if (frm.is_new) {
        return frm.is_new();
    }

    return Boolean(frm.doc && frm.doc.__islocal);
}

function escapeHtml(value) {
    return String(value || '').replace(/[&<>"']/g, function(character) {
        return {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;'
        }[character];
    });
}
