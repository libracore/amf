// Frappe appends this script to ERPNext's Issue list script.
;(() => {
    const settings = frappe.listview_settings.Issue;
    const originalOnload = settings.onload;
    settings.onload = function(listview) {
        originalOnload.call(this, listview);
        const callForSelectedItems = listview.call_for_selected_items;
        listview.call_for_selected_items = function(method, args) {
            if (method !== 'erpnext.support.doctype.issue.issue.set_multiple_status' || !args || args.status !== 'Closed') {
                return callForSelectedItems.call(this, method, args);
            }
            const names = this.get_checked_items(true);
            if (!names.length) return;
            return frappe.call({
                method: 'amf.master_crm.issue_closure.close_from_list',
                args: {names: names},
                freeze: true
            }).then(({message: offers}) => {
                this.refresh();
                if (!offers || !offers.length) return;
                const reviewEmail = (name) => {
                    frappe.amf_review_closure_email = name;
                    frappe.set_route('Form', 'Issue', name);
                };
                if (offers.length === 1) {
                    const offer = offers[0];
                    const prompt = offer.party_type === 'Supplier'
                        ? __('The Issue is closed. Would you like to prepare an email to the supplier?')
                        : __('The Issue is closed. Would you like to prepare an email to the customer?');
                    frappe.confirm(prompt, () => reviewEmail(offer.name));
                    return;
                }
                const dialog = new frappe.ui.Dialog({
                    title: __('Review a closure email?'),
                    fields: [{
                        fieldtype: 'Select', fieldname: 'issue', label: __('Closed Issue'),
                        options: offers.map(offer => offer.name), default: offers[0].name, reqd: 1
                    }],
                    secondary_action_label: __('Skip'),
                    primary_action_label: __('Review email'),
                    primary_action(values) {
                        dialog.hide();
                        reviewEmail(values.issue);
                    }
                });
                dialog.show();
            });
        };
    };
})();
