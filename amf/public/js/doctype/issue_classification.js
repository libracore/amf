/* Governed Issue classification and process routing. */
frappe.ui.form.on('Issue', {
    setup(frm) {
        setActiveIssueTypeQuery(frm);
    },

    refresh(frm) {
        setActiveIssueTypeQuery(frm);
        bindSubjectSuggestionInput(frm);
        scheduleIssueTypeSuggestions(frm);
    },

    subject(frm) {
        scheduleIssueTypeSuggestions(frm);
    },

    issue_type(frm) {
        markIssueTypeAsUserConfirmed(frm);
        fetchIssueRouting(frm);
        renderIssueTypeSuggestions(frm, frm._amf_issue_type_suggestions || []);
    }
});

// AMF Issue Test keeps its existing lifecycle and routing controller.  This
// shared handler adds the same recommendation and confirmation behavior without
// duplicating the classifier or its UI implementation.
frappe.ui.form.on('AMF Issue Test', {
    refresh(frm) {
        bindSubjectSuggestionInput(frm);
        scheduleIssueTypeSuggestions(frm);
    },

    subject(frm) {
        scheduleIssueTypeSuggestions(frm);
    },

    issue_type(frm) {
        markIssueTypeAsUserConfirmed(frm);
        renderIssueTypeSuggestions(frm, frm._amf_issue_type_suggestions || []);
    }
});

function setActiveIssueTypeQuery(frm) {
    frm.set_query('issue_type', function() {
        return {
            filters: {
                is_active: 1
            }
        };
    });
}

function fetchIssueRouting(frm) {
    if (!frm.doc.issue_type) {
        return;
    }

    frappe.db.get_value(
        'Issue Type',
        frm.doc.issue_type,
        ['process', 'process_owner', 'process_co_owner'],
        function(values) {
            if (!values) {
                return;
            }
            if (frm.fields_dict.process_involved) {
                frm.set_value('process_involved', values.process || null);
            }
            if (frm.fields_dict.process_owner) {
                frm.set_value('process_owner', values.process_owner || null);
            }
            if (frm.fields_dict.process_co_owner) {
                frm.set_value('process_co_owner', values.process_co_owner || null);
            }
        }
    );
}

function markIssueTypeAsUserConfirmed(frm) {
    if (!frm.fields_dict.issue_type_user_confirmed) {
        return;
    }
    frm.set_value('issue_type_user_confirmed', frm.doc.issue_type ? 1 : 0);
}

function bindSubjectSuggestionInput(frm) {
    if (!frm.fields_dict.subject || !frm.fields_dict.subject.$input) {
        return;
    }

    frm.fields_dict.subject.$input
        .off('input.amf_issue_type_suggestions')
        .on('input.amf_issue_type_suggestions', function() {
            scheduleIssueTypeSuggestions(frm, $(this).val());
        });
}

function scheduleIssueTypeSuggestions(frm, subject) {
    subject = subject === undefined ? currentIssueSubject(frm) : subject;
    clearTimeout(frm._amf_issue_type_suggestion_timer);

    if (!subject || $.trim(subject).length < 3) {
        frm._amf_issue_type_suggestions = [];
        renderSuggestionMessage(frm, __('Enter a more specific subject to see Issue Type suggestions.'));
        return;
    }

    frm._amf_issue_type_suggestion_timer = setTimeout(function() {
        loadIssueTypeSuggestions(frm, subject);
    }, 550);
}

function currentIssueSubject(frm) {
    if (frm.fields_dict.subject && frm.fields_dict.subject.$input) {
        return frm.fields_dict.subject.$input.val() || frm.doc.subject || '';
    }
    return frm.doc.subject || '';
}

function loadIssueTypeSuggestions(frm, subject) {
    var requestId = (frm._amf_issue_type_suggestion_request_id || 0) + 1;
    frm._amf_issue_type_suggestion_request_id = requestId;
    renderSuggestionMessage(frm, __('Finding the best active Issue Types…'));

    frappe.call({
        method: 'amf.amf.utils.issue_classification.suggest_issue_types',
        args: {
            subject: subject,
            limit: 3
        },
        callback: function(response) {
            if (requestId !== frm._amf_issue_type_suggestion_request_id) {
                return;
            }
            if ($.trim(currentIssueSubject(frm)) !== $.trim(subject)) {
                return;
            }

            var result = response.message || {};
            frm._amf_issue_type_suggestions = result.suggestions || [];
            renderIssueTypeSuggestions(frm, frm._amf_issue_type_suggestions);
        }
    });
}

function renderIssueTypeSuggestions(frm, suggestions) {
    var $wrapper = issueSuggestionWrapper(frm);
    if (!$wrapper) {
        return;
    }
    if (!suggestions.length) {
        renderSuggestionMessage(
            frm,
            __('No reliable match yet. Add the affected object and what went wrong to the subject.')
        );
        return;
    }

    var rows = suggestions.map(function(suggestion) {
        var selected = frm.doc.issue_type === suggestion.name;
        var signals = (suggestion.signals || []).map(escapeSuggestionValue).join(', ');
        var history = suggestion.history_documents
            ? ' · ' + __('learned from {0} earlier classifications', [suggestion.history_documents])
            : '';
        var detail = signals
            ? __('Signals: {0}', [signals]) + history
            : __('Based on the Issue Type definition') + history;
        var action = selected
            ? '<span class="text-success"><i class="fa fa-check"></i> ' + escapeSuggestionValue(__('Selected')) + '</span>'
            : '<button type="button" class="btn btn-xs btn-default amf-apply-issue-type" data-issue-type="' +
                encodeURIComponent(suggestion.name) + '">' + escapeSuggestionValue(__('Apply')) + '</button>';

        return '<div class="amf-issue-suggestion" style="display:flex;gap:12px;align-items:center;' +
            'justify-content:space-between;padding:9px 10px;border-top:1px solid #d1d8dd;">' +
            '<div style="min-width:0;">' +
                '<div><strong>' + escapeSuggestionValue(suggestion.name) + '</strong> ' +
                    '<span class="text-muted">(' + escapeSuggestionValue(suggestion.classification_code || '') + ')</span></div>' +
                '<div class="small text-muted">' + escapeSuggestionValue(suggestion.process || '') +
                    ' · ' + escapeSuggestionValue(__(suggestion.match_strength + ' match')) + '</div>' +
                '<div class="small text-muted">' + detail + '</div>' +
            '</div>' +
            '<div style="flex:0 0 auto;">' + action + '</div>' +
        '</div>';
    }).join('');

    $wrapper.html(
        '<div style="border:1px solid #d1d8dd;border-radius:4px;overflow:hidden;margin-bottom:10px;">' +
            '<div style="padding:8px 10px;background:#f7fafc;">' +
                '<strong><i class="fa fa-magic"></i> ' + escapeSuggestionValue(__('Suggested Issue Types')) + '</strong>' +
                '<span class="small text-muted"> — ' + escapeSuggestionValue(__('review before applying')) + '</span>' +
            '</div>' + rows +
        '</div>'
    );

    $wrapper.find('.amf-apply-issue-type').on('click', function() {
        frm.set_value('issue_type', decodeURIComponent($(this).attr('data-issue-type')));
    });
}

function renderSuggestionMessage(frm, message) {
    var $wrapper = issueSuggestionWrapper(frm);
    if (!$wrapper) {
        return;
    }
    $wrapper.html(
        '<div class="small text-muted" style="padding:6px 0 10px;">' +
            '<i class="fa fa-magic"></i> ' + escapeSuggestionValue(message) +
        '</div>'
    );
}

function issueSuggestionWrapper(frm) {
    var field = frm.fields_dict.issue_type_suggestions;
    return field && field.$wrapper ? field.$wrapper : null;
}

function escapeSuggestionValue(value) {
    return frappe.utils.escape_html(String(value === undefined || value === null ? '' : value));
}
