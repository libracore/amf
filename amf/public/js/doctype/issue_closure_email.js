(() => {
    function composeClosureEmail(frm) {
        return frappe.call({
            method: 'amf.master_crm.issue_closure.get_closure_email',
            args: {name: frm.doc.name},
            freeze: true
        }).then(({message: draft}) => {
            if (!draft || cur_frm !== frm) return;
            const composer = new frappe.views.CommunicationComposer({
                frm: frm,
                doc: frm.doc,
                title: __('Issue closure email'),
                recipients: draft.recipient || '',
                subject: draft.subject,
                txt: draft.message,
                is_a_reply: false
            });
            // V12 enables the print attachment and guesses a recipient by default.
            composer.dialog.set_value('attach_document_print', 0);
            if (!draft.recipient) composer.dialog.set_value('recipients', '');
        });
    }

    frappe.ui.form.on('Issue', {
        after_save(frm) {
            const onload = frm.doc.__onload;
            const party = onload && onload.closure_email_party;
            if (!party) return;
            delete onload.closure_email_party;
            const prompt = party === 'Supplier'
                ? __('The Issue is closed. Would you like to prepare an email to the supplier?')
                : __('The Issue is closed. Would you like to prepare an email to the customer?');
            frappe.confirm(prompt, () => composeClosureEmail(frm));
        },
        refresh(frm) {
            const selection = frm.doc.input_selection;
            const party = selection === 'Supplier Issue' || selection === 'Supplier'
                ? frm.doc.supplier
                : (!selection || selection === 'Customer Issue' || selection === 'Customer')
                    && (frm.doc.customer_issue || frm.doc.customer);
            if (frm.is_new() || frm.doc.status !== 'Closed' || !party || !frappe.model.can_email('Issue', frm)) return;
            frm.add_custom_button(__('Closure email'), () => composeClosureEmail(frm));
            if (frappe.amf_review_closure_email === frm.doc.name) {
                delete frappe.amf_review_closure_email;
                composeClosureEmail(frm);
            }
        }
    });
})();
