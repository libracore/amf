// Copyright (c) 2026, libracore AG and contributors
// For license information, please see license.txt

frappe.ui.form.on("Organizational Modification Request", {
	onload: function(frm) {
		if (frm.is_new() && !frm.doc.requester) {
			frm.set_value("requester", frappe.session.user);
		}
	},

	refresh: function(frm) {
		if (frm.is_new()) {
			return;
		}

		frm.add_custom_button(__("Generate OMR PDF"), function() {
			var url = frappe.urllib.get_full_url(
				"/api/method/frappe.utils.print_format.download_pdf?"
				+ "doctype=" + encodeURIComponent("Organizational Modification Request")
				+ "&name=" + encodeURIComponent(frm.doc.name)
				+ "&format=" + encodeURIComponent("AMF.0053 - Organizational Modification Request")
				+ "&no_letterhead=" + encodeURIComponent("1")
			);
			var pdf_window = window.open(url);
			if (!pdf_window) {
				frappe.msgprint(__("Please enable pop-ups to open the OMR PDF."));
			}
		}, __("Print"));
	},

	requester: function(frm) {
		if (!frm.doc.requester || frm.doc.change_responsible_name_function) {
			return;
		}
		frappe.db.get_value("User", frm.doc.requester, "full_name").then(function(r) {
			if (r.message && r.message.full_name && !frm.doc.change_responsible_name_function) {
				frm.set_value("change_responsible_name_function", r.message.full_name);
			}
		});
	},

	change_responsible_signature: function(frm) {
		set_signature_date(frm, "change_responsible_signature", "change_responsible_approval_date");
	},

	quality_signature: function(frm) {
		set_signature_date(frm, "quality_signature", "quality_approval_date");
	},

	management_signature: function(frm) {
		set_signature_date(frm, "management_signature", "management_approval_date");
	},

	closure_quality_signature: function(frm) {
		set_signature_date(frm, "closure_quality_signature", "closure_date");
		if (frm.doc.closure_quality_signature && !frm.doc.closure_quality_reviewer) {
			frm.set_value("closure_quality_reviewer", frappe.session.user);
		}
	}
});

frappe.ui.form.on("Organizational Modification Action", {
	completed: function(frm, cdt, cdn) {
		var row = locals[cdt][cdn];
		frappe.model.set_value(
			cdt,
			cdn,
			"completion_date",
			row.completed ? frappe.datetime.get_today() : ""
		);
	}
});

function set_signature_date(frm, signature_field, date_field) {
	if (frm.doc[signature_field] && !frm.doc[date_field]) {
		frm.set_value(date_field, frappe.datetime.get_today());
	}
}
