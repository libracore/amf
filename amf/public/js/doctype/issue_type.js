/*
Issue Type Client Custom Script
-------------------------------
*/
frappe.ui.form.on('Issue Type', {
    refresh(frm) {
        // your code here
    },
    
    process(frm) {
        const processMap = {
            'Management Process & Quality': 'remy.rysman@amf.ch',
            'Marketing, Sales & Customer Support': 'christophe.przybyla@amf.ch',
            'Research & Development': 'remy.rysman@amf.ch',
            'Procurement': 'alexandre.ringwald@amf.ch',
            'Manufacturing': 'alexandre.ringwald@amf.ch',
            'Packaging & Shipping': 'alexandre.ringwald@amf.ch',
            'Maintenance': 'alexandre.ringwald@amf.ch',
            'Information System': 'alexandre.ringwald@amf.ch',
        };

        if (frm.doc.process) {
            let processOwner = processMap[frm.doc.process];
            if (processOwner) {
                frm.set_value('process_owner', processOwner);
            } else {
                console.log(`No process owner found for the process: ${frm.doc.process}`);
            }
        } else {
            console.log('The process field is not set.');
        }
    }
});
