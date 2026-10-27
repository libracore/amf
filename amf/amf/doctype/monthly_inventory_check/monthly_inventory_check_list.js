frappe.listview_settings['Monthly Inventory Check'] = {
    add_fields: ['status', 'due_date'],
    get_indicator(doc) {
        if (doc.status === 'Cancelled') return [__('Cancelled'), 'grey', 'status,=,Cancelled'];
        if (doc.status === 'Passed') return [__('Passed'), 'green', 'status,=,Passed'];
        if (doc.due_date < frappe.datetime.get_today()) return [__('Overdue'), 'red', 'due_date,<,Today|status,!=,Passed|status,!=,Cancelled'];
        if (doc.status === 'Awaiting Reconciliation') return [__('Awaiting Reconciliation'), 'orange', 'status,=,Awaiting Reconciliation'];
        return [__('In Progress'), 'blue', 'status,=,In Progress'];
    }
};
