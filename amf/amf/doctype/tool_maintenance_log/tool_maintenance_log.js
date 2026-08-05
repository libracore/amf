// Copyright (c) 2026, libracore AG and contributors
// For license information, please see license.txt

frappe.ui.form.on("Tool Maintenance Log", {
	setup: function(frm) {
		frm.set_query("item_code", function() {
			return {filters: {item_group: "Tool", disabled: 0}};
		});
		frm.set_query("maintenance_plan", function() {
			return {
				filters: {
					item_code: frm.doc.item_code || "",
					status: "Active"
				}
			};
		});
	},

	refresh: function(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Open Maintenance Planner"), function() {
				frappe.route_options = {item_code: frm.doc.item_code};
				frappe.set_route("tool-maintenance");
			}, __("Maintenance"));
		}
	},

	maintenance_plan: function(frm) {
		if (!frm.doc.maintenance_plan) {
			return;
		}
		frappe.db.get_value(
			"Tool Maintenance Plan",
			frm.doc.maintenance_plan,
			["item_code", "maintenance_type", "activity", "responsible"],
			function(values) {
				if (!values) {
					return;
				}
				frm.set_value("item_code", values.item_code);
				frm.set_value("intervention_type", values.maintenance_type);
				frm.set_value("intervention", values.activity);
				if (values.responsible) {
					frm.set_value("responsible", values.responsible);
				}
			}
		);
	}
});
