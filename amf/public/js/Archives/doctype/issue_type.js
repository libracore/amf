frappe.ui.form.on('Issue Type', {
	refresh(frm) {
		// your code here
	},
	
	process: function(frm) {
	    let process_map = {
            'Management Process & Quality': 'remy.rysman@amf.ch',
            'Marketing, Sales & Customer Support': 'christophe.przybyla@amf.ch',
            'Research & Development': 'remy.rysman@amf.ch',
            'Procurement': 'alexandre.ringwald@amf.ch',
            'Manufacturing': 'alexandre.ringwald@amf.ch',
            'Packaging & Shipping': 'alexandre.ringwald@amf.ch',
            'Maintenance': 'alexandre.ringwald@amf.ch',
            'Information System': 'alexandre.ringwald@amf.ch',
        };

        let process_owner = process_map[frm.doc.process];
        if (process_owner) {
            frm.set_value('process_owner', process_owner);
        }
	    
	}
});