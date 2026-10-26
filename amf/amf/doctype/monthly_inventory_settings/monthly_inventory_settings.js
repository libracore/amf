function refresh_inventory_item_groups(frm) {
    return frappe.call({
        method: 'amf.amf.utils.monthly_inventory.get_item_group_defaults',
        callback(r) {
            const known = new Set((frm.doc.item_groups || []).map(row => row.item_group));
            let added = false;
            (r.message || []).forEach(group => {
                if (!known.has(group.item_group)) {
                    frm.add_child('item_groups', group);
                    known.add(group.item_group);
                    added = true;
                }
            });
            if (added) {
                frm.dirty();
                frm.refresh_field('item_groups');
            }
        }
    });
}

frappe.ui.form.on('Monthly Inventory Settings', {
    setup(frm) {
        frm.set_query('assigned_to', () => ({filters: {enabled: 1, user_type: 'System User'}}));
    },
    refresh(frm) {
        const grid = frm.fields_dict.item_groups.grid;
        grid.cannot_add_rows = true;
        grid.wrapper.find('.grid-remove-rows, .grid-add-row, .grid-add-multiple-rows').hide();
        refresh_inventory_item_groups(frm);
        frm.add_custom_button(__('Refresh Item Groups'), () => refresh_inventory_item_groups(frm));
        frm.add_custom_button(__('Generate Current Month'), () => {
            const generate = () => frappe.call({
                method: 'amf.amf.utils.monthly_inventory.generate_current_month',
                freeze: true,
                freeze_message: __('Selecting references and reading warehouse stock...'),
                callback(r) {
                    if (r.message) frappe.set_route('Form', 'Monthly Inventory Check', r.message);
                }
            });
            const confirm = () => frappe.confirm(
                __('Create this month’s checklist and notify the assignee by email? Existing monthly checks will be opened.'),
                generate
            );
            if (frm.is_dirty()) frm.save().then(confirm);
            else confirm();
        });
    }
});

frappe.ui.form.on('Monthly Inventory Item Group', {
    before_item_groups_remove() {
        frappe.throw(__('Use the Enabled checkbox to disable an item group.'));
    }
});
