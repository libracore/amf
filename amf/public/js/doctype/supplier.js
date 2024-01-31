frappe.ui.form.on('Supplier', {
	refresh(frm) {
		// your code here
	},
	
	new_supplier_group(frm) {frm.set_value('supplier_group', frm.doc.new_supplier_group);},
	new_supplier_type(frm) {frm.set_value('supplier_type', frm.doc.new_supplier_type);},
});