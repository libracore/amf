// Copyright (c) 2026, libracore AG and contributors
// For license information, please see license.txt

frappe.ui.form.on("Tool Maintenance Plan", {
	setup: function(frm) {
		frm.set_query("item_code", function() {
			return {filters: {item_group: "Tool", disabled: 0}};
		});
	},

	refresh: function(frm) {
		if (frm.is_new()) {
			return;
		}
		frm.add_custom_button(__("Log Intervention"), function() {
			frappe.new_doc("Tool Maintenance Log", {
				item_code: frm.doc.item_code,
				maintenance_plan: frm.doc.name,
				intervention_type: frm.doc.maintenance_type,
				intervention: frm.doc.activity,
				responsible: frm.doc.responsible
			});
		}, __("Maintenance"));
		frm.add_custom_button(__("Open Maintenance Planner"), function() {
			frappe.route_options = {item_code: frm.doc.item_code};
			frappe.set_route("tool-maintenance");
		}, __("Maintenance"));
	}
});

