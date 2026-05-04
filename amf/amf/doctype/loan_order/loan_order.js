// Copyright (c) 2026, libracore AG and contributors
// For license information, please see license.txt

frappe.ui.form.on("Loan Order", {
	refresh: function(frm) {
		set_warehouse_queries(frm);

		if (frm.doc.docstatus !== 1) {
			return;
		}

		frm.add_custom_button(__("Outward Stock Entry"), function() {
			create_loan_order_document(frm, "make_outward_stock_entry");
		}, __("Create"));

		frm.add_custom_button(__("Outward Delivery Note"), function() {
			create_loan_order_document(frm, "make_outward_delivery_note");
		}, __("Create"));

		frm.add_custom_button(__("Return Stock Entry"), function() {
			create_loan_order_document(frm, "make_return_stock_entry");
		}, __("Create"));

		frm.add_custom_button(__("Return Delivery Note"), function() {
			create_loan_order_document(frm, "make_return_delivery_note");
		}, __("Create"));

		frm.add_custom_button(__("Refresh Status"), function() {
			frappe.call({
				method: "amf.amf.doctype.loan_order.loan_order.refresh_loan_order_status",
				args: {
					source_name: frm.doc.name
				},
				callback: function() {
					frm.reload_doc();
				}
			});
		});
	},
	company: function(frm) {
		set_warehouse_queries(frm);
	},
	party_type: function(frm) {
		frm.set_value("party", "");
		frm.set_value("party_name", "");
	},
	party: function(frm) {
		set_party_name(frm);
	}
});

frappe.ui.form.on("Loan Order Item", {
	item_code: function(frm, cdt, cdn) {
		var row = locals[cdt][cdn];
		if (!row.item_code) {
			return;
		}

		frappe.db.get_value("Item", row.item_code, ["item_name", "stock_uom", "description"]).then(function(r) {
			if (!r.message) {
				return;
			}

			frappe.model.set_value(cdt, cdn, "item_name", r.message.item_name || "");
			frappe.model.set_value(cdt, cdn, "stock_uom", r.message.stock_uom || "");
			frappe.model.set_value(cdt, cdn, "uom", row.uom || r.message.stock_uom || "");
			if (!row.description) {
				frappe.model.set_value(cdt, cdn, "description", r.message.description || "");
			}
		});
	},
	qty: function(frm, cdt, cdn) {
		update_declared_amount(cdt, cdn);
	},
	declared_rate: function(frm, cdt, cdn) {
		update_declared_amount(cdt, cdn);
	}
});

function set_warehouse_queries(frm) {
	var warehouse_fields = ["source_warehouse", "loan_warehouse", "return_warehouse"];
	warehouse_fields.forEach(function(fieldname) {
		frm.set_query(fieldname, function() {
			return {
				filters: {
					company: frm.doc.company
				}
			};
		});
	});

	frm.set_query("source_warehouse", "items", function() {
		return { filters: { company: frm.doc.company } };
	});
	frm.set_query("loan_warehouse", "items", function() {
		return { filters: { company: frm.doc.company } };
	});
	frm.set_query("return_warehouse", "items", function() {
		return { filters: { company: frm.doc.company } };
	});
}

function create_loan_order_document(frm, method) {
	frappe.call({
		method: "amf.amf.doctype.loan_order.loan_order." + method,
		args: {
			source_name: frm.doc.name
		},
		callback: function(r) {
			if (!r.message) {
				return;
			}

			frm.reload_doc();
			frappe.set_route("Form", r.message.doctype, r.message.name);
		}
	});
}

function set_party_name(frm) {
	if (!frm.doc.party_type || !frm.doc.party) {
		return;
	}

	var fieldname = frm.doc.party_type === "Customer" ? "customer_name" : "supplier_name";
	frappe.db.get_value(frm.doc.party_type, frm.doc.party, fieldname).then(function(r) {
		var value = r.message ? r.message[fieldname] : "";
		frm.set_value("party_name", value || frm.doc.party);
	});
}

function update_declared_amount(cdt, cdn) {
	var row = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, "declared_amount", flt(row.qty) * flt(row.declared_rate));
}
