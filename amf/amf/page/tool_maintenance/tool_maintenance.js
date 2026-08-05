(function() {
"use strict";

frappe.pages["tool-maintenance"].on_page_load = function(wrapper) {
	wrapper.tool_maintenance = new ToolMaintenancePage(wrapper);
};


function ToolMaintenancePage(wrapper) {
	this.wrapper = wrapper;
	this.page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Tool Maintenance"),
		single_column: true
	});
	this.method = "amf.amf.page.tool_maintenance.tool_maintenance";
	this.data = null;
	this.request_sequence = 0;
	this.search_timer = null;
	this.route_options = frappe.route_options || {};
	frappe.route_options = null;
	this.make();
}


ToolMaintenancePage.prototype.make = function() {
	var self = this;
	this.controls = {
		search: this.page.add_field({
			fieldname: "search",
			label: __("Search"),
			fieldtype: "Data",
			placeholder: __("Item, serial number, type or location"),
			default: this.route_options.item_code || ""
		}),
		status: this.page.add_field({
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: "\nOverdue\nDue Soon\nPlanned\nNo Plan",
			change: function() { self.load(); }
		}),
		responsible: this.page.add_field({
			fieldname: "responsible",
			label: __("Responsible"),
			fieldtype: "Link",
			options: "Employee",
			change: function() { self.load(); }
		}),
		include_disabled: this.page.add_field({
			fieldname: "include_disabled",
			label: __("Include Disabled"),
			fieldtype: "Check",
			default: 0,
			change: function() { self.load(); }
		})
	};

	this.page.set_primary_action(__("New Maintenance Plan"), function() {
		self.new_plan();
	}, "octicon octicon-plus");
	this.page.add_inner_button(__("Log Intervention"), function() {
		self.new_log();
	});
	this.page.add_inner_button(__("Maintenance Plans"), function() {
		frappe.set_route("List", "Tool Maintenance Plan");
	});
	this.page.add_inner_button(__("Intervention Logs"), function() {
		frappe.set_route("List", "Tool Maintenance Log");
	});

	this.$root = $(
		'<div class="tool-maintenance-page">' +
			'<section class="tm-hero">' +
				'<div><div class="tm-eyebrow"><span class="octicon octicon-tools"></span> ' +
					esc(__("EQUIPMENT RELIABILITY")) + '</div>' +
				'<h2>' + esc(__("Plan the work. Keep the history.")) + '</h2>' +
				'<p>' + esc(__("A live maintenance view for Items in the Tool group, with recurring plans, due dates and traceable intervention records.")) + '</p></div>' +
				'<div class="tm-generated"></div>' +
			'</section>' +
			'<div class="tm-results"></div>' +
		'</div>'
	).appendTo(this.page.main);
	this.$results = this.$root.find(".tm-results");
	this.bind();
	this.render_loading();
	setTimeout(function() { self.load(); }, 0);
};


ToolMaintenancePage.prototype.bind = function() {
	var self = this;
	if (this.controls.search.$input) {
		this.controls.search.$input.on("input", function() {
			clearTimeout(self.search_timer);
			self.search_timer = setTimeout(function() { self.load(); }, 300);
		});
	}
	this.$results.on("click", "[data-action]", function(event) {
		event.preventDefault();
		var $button = $(this);
		var action = $button.attr("data-action");
		var item_code = $button.attr("data-item-code");
		if (action === "open-item") {
			frappe.set_route("Form", "Item", item_code);
		} else if (action === "open-plan") {
			frappe.set_route("Form", "Tool Maintenance Plan", $button.attr("data-plan"));
		} else if (action === "new-plan") {
			self.new_plan(item_code);
		} else if (action === "new-log") {
			self.new_log(item_code, $button.attr("data-plan"));
		} else if (action === "detail") {
			self.open_detail(item_code);
		}
	});
};


ToolMaintenancePage.prototype.get_args = function() {
	return {
		search: this.controls.search.get_value() || "",
		status: this.controls.status.get_value() || "",
		responsible: this.controls.responsible.get_value() || "",
		include_disabled: this.controls.include_disabled.get_value() ? 1 : 0
	};
};


ToolMaintenancePage.prototype.load = function() {
	var self = this;
	var sequence = ++this.request_sequence;
	this.render_loading();
	frappe.call({
		method: this.method + ".get_dashboard",
		args: this.get_args(),
		callback: function(response) {
			if (sequence !== self.request_sequence) {
				return;
			}
			self.data = response.message || {items: [], summary: {}};
			self.render();
		},
		error: function() {
			if (sequence === self.request_sequence) {
				self.$results.html(empty_state(__("The maintenance dashboard could not be loaded.")));
			}
		}
	});
};


ToolMaintenancePage.prototype.render_loading = function() {
	this.$results.html(
		'<div class="tm-loading"><div class="tm-loading-kpis"><i></i><i></i><i></i><i></i><i></i></div>' +
		'<div class="tm-loading-table"></div></div>'
	);
};


ToolMaintenancePage.prototype.render = function() {
	var data = this.data || {};
	var summary = data.summary || {};
	var rows = data.items || [];
	this.$root.find(".tm-generated").html(
		'<span class="octicon octicon-clock"></span> ' +
		esc(__("Updated {0}", [format_datetime(data.generated_at)]))
	);
	this.$results.html(
		'<section class="tm-kpis">' +
			kpi("octicon-tools", summary.tools, __("Tools"), __("Current result"), "blue") +
			kpi("octicon-alert", summary.overdue, __("Overdue"), __("Immediate action"), "red") +
			kpi("octicon-clock", summary.due_soon, __("Due Soon"), __("Within warning window"), "amber") +
			kpi("octicon-calendar", summary.planned, __("Planned"), __("Future activities"), "green") +
			kpi("octicon-circle-slash", summary.no_plan, __("No Plan"), __("Planning gap"), "slate") +
		'</section>' +
		'<section class="tm-data-card">' +
			'<header class="tm-data-head"><div><h3>' + esc(__("Maintenance priorities")) + '</h3>' +
			'<p>' + esc(__("Overdue tools appear first, followed by the nearest due date.")) + '</p></div>' +
			'<span>' + esc(__("{0} matching tools", [rows.length])) + '</span></header>' +
			(rows.length ? render_table(rows) : empty_state(__("No Tool items match these filters."))) +
		'</section>'
	);
};


ToolMaintenancePage.prototype.new_plan = function(item_code) {
	frappe.new_doc("Tool Maintenance Plan", item_code ? {item_code: item_code} : {});
};


ToolMaintenancePage.prototype.new_log = function(item_code, plan_name) {
	var values = {};
	if (item_code) {
		values.item_code = item_code;
	}
	if (plan_name) {
		values.maintenance_plan = plan_name;
	}
	frappe.new_doc("Tool Maintenance Log", values);
};


ToolMaintenancePage.prototype.open_detail = function(item_code) {
	var self = this;
	var dialog = new frappe.ui.Dialog({
		title: __("Maintenance · {0}", [item_code]),
		fields: [{fieldtype: "HTML", fieldname: "body"}]
	});
	dialog.$wrapper.addClass("tm-detail-dialog");
	dialog.fields_dict.body.$wrapper.html(
		'<div class="tm-detail-loading"><i class="fa fa-spinner fa-spin"></i> ' +
		esc(__("Loading plans and intervention history…")) + '</div>'
	);
	dialog.show();
	frappe.call({
		method: this.method + ".get_tool_detail",
		args: {item_code: item_code},
		callback: function(response) {
			if (!response.message) {
				return;
			}
			dialog.fields_dict.body.$wrapper.html(render_detail(response.message));
			dialog.fields_dict.body.$wrapper.on("click", "[data-detail-action]", function(event) {
				event.preventDefault();
				var $target = $(this);
				var action = $target.attr("data-detail-action");
				if (action === "item") {
					frappe.set_route("Form", "Item", item_code);
					dialog.hide();
				} else if (action === "plan") {
					frappe.set_route("Form", "Tool Maintenance Plan", $target.attr("data-name"));
					dialog.hide();
				} else if (action === "log") {
					frappe.set_route("Form", "Tool Maintenance Log", $target.attr("data-name"));
					dialog.hide();
				} else if (action === "new-log") {
					self.new_log(item_code, $target.attr("data-plan"));
					dialog.hide();
				}
			});
		}
	});
};


function render_table(rows) {
	return '<div class="tm-table-wrap"><table class="table tm-table"><thead><tr>' +
		'<th>' + esc(__("Status")) + '</th>' +
		'<th>' + esc(__("Tool")) + '</th>' +
		'<th>' + esc(__("Type / Location")) + '</th>' +
		'<th>' + esc(__("Next Activity")) + '</th>' +
		'<th>' + esc(__("Next Due")) + '</th>' +
		'<th>' + esc(__("Responsible")) + '</th>' +
		'<th>' + esc(__("Last Intervention")) + '</th>' +
		'<th></th></tr></thead><tbody>' +
		rows.map(function(row) {
			return '<tr class="' + (row.disabled ? "tm-disabled-row" : "") + '">' +
				'<td>' + status_badge(row.status, row.overdue_count) + '</td>' +
				'<td class="tm-tool-cell"><a href="#" data-action="open-item" data-item-code="' + esc(row.item_code) + '">' +
					esc(row.item_code) + '</a><strong>' + esc(row.item_name || __("Unnamed Item")) + '</strong>' +
					'<small>' + esc(row.serial_number ? __("S/N {0}", [row.serial_number]) : __("No serial number")) + '</small></td>' +
				'<td><strong class="tm-secondary-strong">' + esc(row.equipment_type || "—") + '</strong>' +
					'<small class="tm-cell-small"><span class="octicon octicon-location"></span> ' + esc(row.location || __("Not set")) + '</small></td>' +
				'<td>' + activity_link(row) + '</td>' +
				'<td class="tm-date-cell">' + format_date(row.next_due_date) + '</td>' +
				'<td>' + esc(row.plan_responsible_name || row.responsible_name || "—") + '</td>' +
				'<td class="tm-date-cell">' + format_date(row.last_intervention_date) +
					(row.last_intervention ? '<small title="' + esc(row.last_intervention) + '">' + esc(shorten(row.last_intervention, 42)) + '</small>' : '') + '</td>' +
				'<td class="tm-actions">' +
					'<button class="btn btn-default btn-xs" data-action="detail" data-item-code="' + esc(row.item_code) + '">' + esc(__("Details")) + '</button>' +
					'<button class="btn btn-default btn-xs" data-action="new-log" data-item-code="' + esc(row.item_code) + '"' +
						(row.next_plan ? ' data-plan="' + esc(row.next_plan) + '"' : '') + '>' + esc(__("Log")) + '</button>' +
					(!row.next_plan ? '<button class="btn btn-default btn-xs" data-action="new-plan" data-item-code="' + esc(row.item_code) + '">' + esc(__("Plan")) + '</button>' : '') +
				'</td></tr>';
		}).join("") +
	'</tbody></table></div>';
}


function activity_link(row) {
	if (!row.next_plan) {
		return '<span class="tm-muted">' + esc(__("No active plan")) + '</span>';
	}
	return '<a href="#" class="tm-activity-link" data-action="open-plan" data-plan="' + esc(row.next_plan) +
		'" data-item-code="' + esc(row.item_code) + '"><strong>' + esc(row.next_activity || __("Maintenance")) +
		'</strong><small>' + esc(row.next_type || "") + '</small></a>';
}


function render_detail(data) {
	var item = data.item || {};
	var plans = data.plans || [];
	var logs = data.logs || [];
	return '<div class="tm-detail">' +
		'<section class="tm-detail-identity"><div><a href="#" data-detail-action="item">' + esc(item.item_code) + '</a>' +
		'<h3>' + esc(item.item_name || "") + '</h3><p>' + esc([item.equipment_type, item.location, item.serial_number ? "S/N " + item.serial_number : ""].filter(Boolean).join(" · ")) +
		'</p></div><span>' + esc(item.responsible_name || __("No responsible employee")) + '</span></section>' +
		'<section class="tm-detail-metadata">' +
			detail_value(__("Ownership"), item.ownership) +
			detail_value(__("Required PPE"), item.required_ppe) +
			detail_value(__("Calibration / Verification"), item.calibration_procedure) +
			detail_value(__("Maintenance Instructions"), item.maintenance_instructions) +
		'</section>' +
		'<section class="tm-detail-section"><header><div><h4>' + esc(__("Maintenance Plans")) + '</h4><p>' + esc(__("Recurring and one-time work still to manage.")) +
		'</p></div></header>' + render_plans(plans) + '</section>' +
		'<section class="tm-detail-section"><header><div><h4>' + esc(__("Intervention History")) + '</h4><p>' + esc(__("Completed work and its supporting references.")) +
		'</p></div></header>' + render_logs(logs) + '</section></div>';
}


function render_plans(plans) {
	if (!plans.length) {
		return '<div class="tm-detail-empty">' + esc(__("No maintenance plan has been created.")) + '</div>';
	}
	return '<div class="tm-detail-list">' + plans.map(function(plan) {
		return '<article><div><a href="#" data-detail-action="plan" data-name="' + esc(plan.name) + '">' + esc(plan.activity) + '</a>' +
			'<span>' + esc(plan.maintenance_type) + ' · ' + esc(plan.status) + '</span></div>' +
			'<div class="tm-detail-due"><strong>' + format_date(plan.next_due_date) + '</strong><span>' +
				esc(plan.responsible_name || __("Unassigned")) + '</span></div>' +
			'<button class="btn btn-default btn-xs" data-detail-action="new-log" data-plan="' + esc(plan.name) + '">' + esc(__("Log")) + '</button></article>';
	}).join("") + '</div>';
}


function render_logs(logs) {
	if (!logs.length) {
		return '<div class="tm-detail-empty">' + esc(__("No intervention has been logged.")) + '</div>';
	}
	return '<div class="tm-history">' + logs.map(function(log) {
		return '<article><time>' + format_date(log.intervention_date) + '</time><div><a href="#" data-detail-action="log" data-name="' + esc(log.name) + '">' +
			esc(log.intervention) + '</a><span>' + esc([log.intervention_type, log.responsible_name || log.performed_by, log.record_reference].filter(Boolean).join(" · ")) +
			'</span>' + (log.remarks ? '<p>' + esc(log.remarks) + '</p>' : '') + '</div></article>';
	}).join("") + '</div>';
}


function detail_value(label, value) {
	return '<div><span>' + esc(label) + '</span><p>' + esc(value || "—") + '</p></div>';
}


function kpi(icon, value, label, note, color) {
	return '<div class="tm-kpi ' + color + '"><span class="tm-kpi-icon octicon ' + icon + '"></span><div><strong>' +
		esc(String(value || 0)) + '</strong><span>' + esc(label) + '</span><small>' + esc(note) + '</small></div></div>';
}


function status_badge(status, count) {
	var css = {"Overdue": "overdue", "Due Soon": "due-soon", "Planned": "planned", "No Plan": "no-plan"}[status] || "no-plan";
	var suffix = status === "Overdue" && count > 1 ? " · " + count : "";
	return '<span class="tm-status ' + css + '">' + esc(__(status || "No Plan") + suffix) + '</span>';
}


function format_date(value) {
	if (!value) {
		return '<span class="tm-muted">—</span>';
	}
	return esc(frappe.datetime.str_to_user(String(value).split(" ")[0]));
}


function format_datetime(value) {
	if (!value) {
		return "—";
	}
	var parts = String(value).split(" ");
	return frappe.datetime.str_to_user(parts[0]) + (parts[1] ? " " + parts[1].slice(0, 5) : "");
}


function shorten(value, limit) {
	value = String(value || "");
	return value.length > limit ? value.slice(0, limit - 1).trim() + "…" : value;
}


function empty_state(message) {
	return '<div class="tm-empty"><span class="octicon octicon-tools"></span><h3>' + esc(__("Nothing to show")) +
		'</h3><p>' + esc(message) + '</p></div>';
}


function esc(value) {
	return frappe.utils.escape_html(String(value === null || value === undefined ? "" : value));
}

}());

