/*
Issue Type Client Custom Script
-------------------------------
*/
frappe.ui.form.on('Issue Type', {
    refresh(frm) {
        frm.set_query('process', function() {
            return {
                filters: {
                    enabled: 1
                }
            };
        });
    },

    process(frm) {
        if (!frm.doc.process) {
            frm.set_value('process_owner', null);
            frm.set_value('process_co_owner', null);
            return;
        }

        frappe.db.get_value(
            'AMF Issue Process',
            frm.doc.process,
            ['primary_owner', 'secondary_owner'],
            function(values) {
                if (!values) {
                    return;
                }
                frm.set_value('process_owner', values.primary_owner || null);
                frm.set_value('process_co_owner', values.secondary_owner || null);
            }
        );
    }
});
