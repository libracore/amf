/* global frappe, __, cint, flt */
frappe.ui.form.on('Monthly Inventory Check', {
    refresh(frm) {
        const grid = frm.fields_dict.rows.grid;
        grid.cannot_add_rows = true;
        grid.wrapper.find('.grid-remove-rows, .grid-add-row, .grid-add-multiple-rows').hide();
        if (frm.doc.status === 'Passed') {
            frm.set_read_only();
            frm.dashboard.set_headline_alert(__('Sanity check passed. All counts and submitted corrections were verified.'), 'green');
            return;
        }
        frm.dashboard.set_headline_alert(
            __('{0} of {1} warehouse rows confirmed across {2} references.',
                [frm.doc.checked_rows || 0, frm.doc.total_rows || 0, frm.doc.reference_count || 0]), 'blue');

        function action(method, route) {
            const run = () => frappe.call({
                method: 'amf.amf.utils.monthly_inventory.' + method,
                args: {name: frm.doc.name}, freeze: true,
                callback(r) {
                    if (route && r.message) frappe.set_route('Form', route, r.message);
                    else frm.reload_doc();
                }
            });
            if (frm.is_dirty()) frm.save().then(run);
            else run();
        }
        frm.add_custom_button(__('Refresh Stock'), () => frappe.confirm(
            __('Refresh every warehouse balance and clear all recorded counts? You will need to recount.'),
            () => action('refresh_stock')));
        frm.add_custom_button(__('Confirm Empty Warehouses'), () => frappe.confirm(
            __('Confirm that you physically verified all warehouses showing zero stock for these references and found no stock there?'),
            () => {
                let count = 0;
                (frm.doc.rows || []).forEach(row => {
                    if (!row.counted && flt(row.current_qty) === 0 && flt(row.counted_qty) === 0) {
                        row.counted = 1;
                        count += 1;
                    }
                });
                if (count) {
                    frm.dirty();
                    frm.refresh_field('rows');
                    frm.save();
                }
            }));
        if (frappe.model.can_create('Stock Reconciliation')) {
            frm.add_custom_button(__('Create Draft Reconciliation'), () => action('create_reconciliation', 'Stock Reconciliation'));
        }
        frm.add_custom_button(__('Verify and Complete'), () => action('complete_check'));
        if (frm.doc.reconciliation) {
            frm.add_custom_button(__('Open Reconciliation'), () =>
                frappe.set_route('Form', 'Stock Reconciliation', frm.doc.reconciliation));
        }
        frappe.call({
            method: 'amf.amf.utils.monthly_inventory.get_stale_rows',
            args: {name: frm.doc.name},
            callback(r) {
                if ((r.message || []).length) frm.dashboard.set_headline_alert(
                    __('Stock changed in {0} warehouse rows. Review corrections or Refresh Stock and recount before completing.', [r.message.length]), 'orange');
            }
        });
    }
});

frappe.ui.form.on('Monthly Inventory Check Row', {
    before_rows_remove() {
        frappe.throw(__('Inventory rows cannot be removed. Use Refresh Stock.'));
    }
});
