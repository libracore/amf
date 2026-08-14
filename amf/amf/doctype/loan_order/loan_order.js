// Copyright (c) 2026, libracore AG and contributors
// For license information, please see license.txt

frappe.ui.form.on("Loan Order", {
	refresh: function(frm) {
		set_warehouse_queries(frm);
		set_billing_queries(frm);

		if (frm.doc.docstatus !== 1) {
			return;
		}

		if (frm.doc.sales_invoice && frm.doc.billing_status !== "Pending") {
			frm.add_custom_button(__("Open Settlement Invoice"), function() {
				frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice);
			}, __("Billing"));
		} else if (frm.doc.party_type === "Customer") {
			frm.add_custom_button(__("Settlement Sales Invoice"), function() {
				open_settlement_invoice_dialog(frm);
			}, __("Billing"));
		}

		add_settlement_document_buttons(frm);

		if (!has_commercial_settlement(frm)) {
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
		}

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
		set_billing_queries(frm);
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

function set_billing_queries(frm) {
	frm.set_query("selling_price_list", function() {
		return {
			filters: {
				enabled: 1,
				selling: 1,
				currency: frm.doc.currency
			}
		};
	});

	frm.set_query("billing_bom", "items", function(doc, cdt, cdn) {
		var row = locals[cdt][cdn];
		return {
			filters: {
				item: row.item_code,
				docstatus: 1,
				is_active: 1
			}
		};
	});
}

function open_settlement_invoice_dialog(frm) {
	var dialog = new frappe.ui.Dialog({
		title: __("Create Loan Settlement Invoice"),
		fields: [
			{
				fieldname: "billing_decision",
				fieldtype: "Select",
				label: __("Customer Decision"),
				options: "Spare Parts Only\nFull Product Purchase",
				reqd: 1
			},
			{
				fieldname: "selling_price_list",
				fieldtype: "Link",
				label: __("Selling Price List"),
				options: "Price List",
				default: frm.doc.selling_price_list || (
					frm.doc.__onload && frm.doc.__onload.default_selling_price_list
				),
				reqd: 1
			},
			{
				fieldname: "explanation",
				fieldtype: "HTML",
				options: __("<p><b>Spare Parts Only</b>: dismantles each product into its direct BOM rows, invoices the valve heads and syringes, and returns the body and remaining components with the accessories.</p><p><b>Full Product Purchase</b>: invoices the product price less those spares, itemizes the spares, then adds cables and accessories still with the customer.</p>")
			}
		],
		primary_action_label: __("Create Draft Invoice"),
		primary_action: function(values) {
			dialog.disable_primary_action();
			frappe.call({
				method: "amf.amf.doctype.loan_order.loan_order.make_settlement_sales_invoice",
				args: {
					source_name: frm.doc.name,
					billing_decision: values.billing_decision,
					selling_price_list: values.selling_price_list
				},
				callback: function(r) {
					if (!r.message) {
						dialog.enable_primary_action();
						return;
					}
					dialog.hide();
					frm.reload_doc();
					if (r.message.documents && r.message.documents.length) {
						var links = r.message.documents.map(function(document) {
							return frappe.utils.get_form_link(document.doctype, document.name, true);
						});
						frappe.show_alert({
							message: __("Settlement stock documents created: {0}", [links.join(", ")]),
							indicator: "green"
						}, 10);
					}
					frappe.set_route("Form", r.message.doctype, r.message.name);
				},
				error: function() {
					dialog.enable_primary_action();
				}
			});
		}
	});

	dialog.fields_dict.selling_price_list.get_query = function() {
		return {
			filters: {
				enabled: 1,
				selling: 1,
				currency: frm.doc.currency
			}
		};
	};
	dialog.show();
}

function add_settlement_document_buttons(frm) {
	[
		["settlement_delivery_note", __("Open Settlement Delivery Note"), "Delivery Note"],
		["settlement_return_delivery_note", __("Open Settlement Return"), "Delivery Note"],
		["settlement_stock_entry", __("Open Settlement Repack"), "Stock Entry"]
	].forEach(function(definition) {
		var fieldname = definition[0];
		if (!frm.doc[fieldname]) {
			return;
		}
		frm.add_custom_button(definition[1], function() {
			frappe.set_route("Form", definition[2], frm.doc[fieldname]);
		}, __("Billing"));
	});
}

function has_commercial_settlement(frm) {
	return Boolean(
		frm.doc.sales_invoice ||
		frm.doc.settlement_delivery_note ||
		frm.doc.settlement_return_delivery_note ||
		frm.doc.settlement_stock_entry
	);
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
