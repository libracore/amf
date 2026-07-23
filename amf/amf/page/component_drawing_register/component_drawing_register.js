(function() {
"use strict";

frappe.pages["component-drawing-register"].on_page_load = function(wrapper) {
	wrapper.component_drawing_register = new ComponentDrawingRegister(wrapper);
};


function ComponentDrawingRegister(wrapper) {
	this.wrapper = wrapper;
	this.page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Component Drawing Register"),
		single_column: true
	});
	this.method = "amf.amf.page.component_drawing_register.component_drawing_register.get_components";
	this.data = null;
	this.active_tab = "register";
	this.request_sequence = 0;
	this.search_timer = null;
	this.make();
}


ComponentDrawingRegister.prototype.make = function() {
	var self = this;

	this.controls = {
		search: this.page.add_field({
			fieldname: "search",
			label: __("Search"),
			fieldtype: "Data",
			placeholder: __("Code, name, reference or drawing")
		}),
		series: this.page.add_field({
			fieldname: "series",
			label: __("Series"),
			fieldtype: "Select",
			options: "All\nPlug\nValve Seat",
			default: "All",
			change: function() {
				self.load();
			}
		}),
		drawing_status: this.page.add_field({
			fieldname: "drawing_status",
			label: __("Drawing"),
			fieldtype: "Select",
			options: "All\nWith default\nMissing default",
			default: "All",
			change: function() {
				self.load();
			}
		}),
		include_disabled: this.page.add_field({
			fieldname: "include_disabled",
			label: __("Include Disabled"),
			fieldtype: "Check",
			default: 0,
			change: function() {
				self.load();
			}
		})
	};

	this.page.set_primary_action(__("Refresh"), function() {
		self.load();
	}, "octicon octicon-sync");

	this.$register = $(
		'<div class="component-drawing-register">' +
			'<section class="cdr-hero">' +
				'<div>' +
					'<div class="cdr-eyebrow">' + esc(__("CONTROLLED TECHNICAL DOCUMENTS")) + '</div>' +
					'<h2>' + esc(__("Components and their current drawings")) + '</h2>' +
					'<p>' + esc(__("Six-digit component codes beginning with 10 or 20. Only the drawing marked as default is shown.")) + '</p>' +
				'</div>' +
				'<div class="cdr-generated"></div>' +
			'</section>' +
			'<div class="cdr-results"></div>' +
		'</div>'
	).appendTo(this.page.main);

	this.$results = this.$register.find(".cdr-results");
	this.bind_events();
	this.render_loading();
	setTimeout(function() {
		self.load();
	}, 0);
};


ComponentDrawingRegister.prototype.bind_events = function() {
	var self = this;

	if (this.controls.search.$input) {
		this.controls.search.$input.on("input", function() {
			clearTimeout(self.search_timer);
			self.search_timer = setTimeout(function() {
				self.load();
			}, 300);
		});
	}

	this.$results.on("click", ".cdr-item-link", function(event) {
		event.preventDefault();
		frappe.set_route("Form", "Item", $(this).attr("data-item-code"));
	});

	this.$results.on("click", ".cdr-tab", function() {
		self.active_tab = $(this).attr("data-tab");
		self.update_active_tab();
	});
};


ComponentDrawingRegister.prototype.get_filters = function() {
	var series = this.controls.series.get_value();
	var drawing_status = this.controls.drawing_status.get_value();
	return {
		search: this.controls.search.get_value() || "",
		series: series === "Plug" ? "10" : (series === "Valve Seat" ? "20" : ""),
		drawing_status: drawing_status === "With default" ? "with" :
			(drawing_status === "Missing default" ? "missing" : ""),
		include_disabled: this.controls.include_disabled.get_value() ? 1 : 0
	};
};


ComponentDrawingRegister.prototype.load = function() {
	var self = this;
	var sequence = ++this.request_sequence;

	this.render_loading();
	if (this.page.btn_primary) {
		this.page.btn_primary.prop("disabled", true);
	}

	frappe.call({
		method: this.method,
		args: this.get_filters(),
		callback: function(response) {
			if (sequence !== self.request_sequence) {
				return;
			}
			if (self.page.btn_primary) {
				self.page.btn_primary.prop("disabled", false);
			}
			self.data = response.message || { rows: [], summary: {} };
			self.render();
		},
		error: function() {
			if (sequence === self.request_sequence && self.page.btn_primary) {
				self.page.btn_primary.prop("disabled", false);
			}
		}
	});
};


ComponentDrawingRegister.prototype.render_loading = function() {
	this.$results.html(
		'<div class="cdr-skeleton">' +
			'<div class="cdr-skeleton-row"><span></span><span></span><span></span><span></span><span></span></div>' +
			'<div class="cdr-skeleton-table"></div>' +
		'</div>'
	);
};


ComponentDrawingRegister.prototype.render = function() {
	var data = this.data || {};
	var rows = data.rows || [];
	var missing_drawings = data.missing_drawings || [];
	var summary = data.summary || {};

	this.$register.find(".cdr-generated").html(
		'<span class="octicon octicon-clock"></span> ' +
		esc(__("Updated {0}", [format_datetime(data.generated_at)]))
	);

	this.$results.html(
		'<section class="cdr-kpis">' +
			kpi("octicon-package", summary.components, __("Components"), __("Current result"), "blue") +
			kpi("octicon-file-pdf", summary.with_drawing, __("Default drawings"), __("Ready to open"), "green") +
			kpi("octicon-alert", summary.missing_drawing, __("Missing defaults"), __("Requires attention"), "amber") +
			kpi("octicon-versions", summary.series_10, __("Plugs"), __("10-series components"), "violet") +
			kpi("octicon-versions", summary.series_20, __("Valve Seats"), __("20-series components"), "slate") +
		'</section>' +
		'<section class="cdr-data-card">' +
			'<header class="cdr-data-head">' +
				'<div class="cdr-tabs" role="tablist">' +
					tab_button("register", __("Drawing Register"), summary.components || 0) +
					tab_button("missing", __("Missing Drawing References"), missing_drawings.length) +
				'</div>' +
				'<div class="cdr-rule"><span class="octicon octicon-checklist"></span> ' +
					esc(__("Item code rule: ^(10|20)[0-9]{4}$")) + '</div>' +
			'</header>' +
			'<div class="cdr-tab-panel" data-panel="register">' + this.render_table(rows) + '</div>' +
			'<div class="cdr-tab-panel" data-panel="missing">' + this.render_missing_references(missing_drawings) + '</div>' +
		'</section>'
	);
	this.update_active_tab();
};


ComponentDrawingRegister.prototype.render_table = function(rows) {
	if (!rows.length) {
		return '<div class="cdr-empty">' +
			'<span class="octicon octicon-search"></span>' +
			'<h3>' + esc(__("No components found")) + '</h3>' +
			'<p>' + esc(__("No six-digit 10/20 component matches the selected filters.")) + '</p>' +
		'</div>';
	}

	return '<div class="cdr-table-wrap"><table class="table cdr-table">' +
		'<thead><tr>' +
			'<th>' + esc(__("Component")) + '</th>' +
			'<th>' + esc(__("Item Group")) + '</th>' +
			'<th>' + esc(__("Default Drawing")) + '</th>' +
			'<th>' + esc(__("Version")) + '</th>' +
			'<th>' + esc(__("Revision")) + '</th>' +
			'<th>' + esc(__("Status")) + '</th>' +
		'</tr></thead>' +
		'<tbody>' +
		rows.map(function(row) {
			return '<tr class="' + (row.disabled ? "cdr-disabled-row" : "") + '">' +
				'<td class="cdr-component-cell">' +
					'<a href="#" class="cdr-item-link" data-item-code="' + esc(row.item_code) + '">' +
						esc(row.item_code) + '</a>' +
					'<strong title="' + esc(row.description || row.item_name || "") + '">' +
						esc(row.item_name || __("Unnamed Item")) + '</strong>' +
					'<small>' + esc(row.reference_code || __("No reference code")) +
						(row.stock_uom ? " · " + esc(row.stock_uom) : "") + '</small>' +
				'</td>' +
				'<td>' + esc(row.item_group || "—") + '</td>' +
				'<td class="cdr-drawing-cell">' + drawing_link(row) + '</td>' +
				'<td class="cdr-version-cell">' + revision_value(row.version) + '</td>' +
				'<td class="cdr-version-cell">' + revision_value(row.revision) + '</td>' +
				'<td>' + status_badges(row) + '</td>' +
			'</tr>';
		}).join("") +
		'</tbody></table></div>';
};


ComponentDrawingRegister.prototype.render_missing_references = function(rows) {
	if (!rows.length) {
		return '<div class="cdr-empty">' +
			'<span class="octicon octicon-check"></span>' +
			'<h3>' + esc(__("No missing drawings")) + '</h3>' +
			'<p>' + esc(__("Every matching component has a default drawing.")) + '</p>' +
		'</div>';
	}

	return '<div class="cdr-table-wrap"><table class="table cdr-table cdr-missing-ref-table">' +
		'<thead><tr><th>' + esc(__("Reference")) + '</th></tr></thead>' +
		'<tbody>' +
		rows.map(function(row) {
			return '<tr class="' + (row.disabled ? "cdr-disabled-row" : "") + '">' +
				'<td class="cdr-reference-cell">' +
					'<a href="#" class="cdr-item-link" data-item-code="' + esc(row.item_code) + '">' +
						esc(row.reference_code || __("No reference code")) + '</a>' +
					'<small>' + esc(row.item_code) + ' · ' + esc(row.item_name || __("Unnamed Item")) + '</small>' +
				'</td>' +
			'</tr>';
		}).join("") +
		'</tbody></table></div>';
};


ComponentDrawingRegister.prototype.update_active_tab = function() {
	var active_tab = this.active_tab;
	this.$results.find(".cdr-tab").each(function() {
		var is_active = $(this).attr("data-tab") === active_tab;
		$(this).toggleClass("active", is_active)
			.attr("aria-selected", is_active ? "true" : "false");
	});
	this.$results.find(".cdr-tab-panel").each(function() {
		$(this).toggle($(this).attr("data-panel") === active_tab);
	});
};


function drawing_link(row) {
	if (!row.has_default_drawing) {
		return '<span class="cdr-missing"><span class="octicon octicon-alert"></span> ' +
			esc(__("No default drawing")) + '</span>';
	}

	if (!row.drawing) {
		return '<span class="cdr-missing"><span class="octicon octicon-alert"></span> ' +
			esc(__("Default has no file")) + '</span>';
	}

	return '<a class="cdr-drawing-link" href="' + esc(row.drawing) + '" target="_blank" rel="noopener noreferrer">' +
			'<span class="cdr-pdf-icon"><span class="octicon octicon-file-pdf"></span></span>' +
			'<span><strong>' + esc(row.drawing_reference_code || row.reference_code || __("Drawing")) + '</strong>' +
			'<small title="' + esc(row.drawing_file_name) + '">' + esc(row.drawing_file_name) + '</small></span>' +
			'<span class="octicon octicon-link-external cdr-open-icon"></span>' +
		'</a>';
}


function revision_value(value) {
	if (!value) {
		return '<span class="cdr-not-set">—</span>';
	}
	return '<span class="cdr-revision">' + esc(value) + '</span>';
}


function status_badges(row) {
	var drawing_status = row.has_default_drawing ?
		'<span class="cdr-status default"><span class="octicon octicon-check"></span> ' + esc(__("Default")) + '</span>' :
		'<span class="cdr-status missing"><span class="octicon octicon-alert"></span> ' + esc(__("Missing")) + '</span>';
	var item_status = row.disabled ?
		'<span class="cdr-status disabled">' + esc(__("Disabled")) + '</span>' : "";
	return drawing_status + item_status;
}


function tab_button(name, label, count) {
	return '<button type="button" class="cdr-tab" data-tab="' + esc(name) +
		'" role="tab" aria-selected="false">' + esc(label) +
		'<span>' + esc(count || 0) + '</span></button>';
}


function kpi(icon, value, label, note, color) {
	return '<div class="cdr-kpi ' + color + '">' +
		'<span class="cdr-kpi-icon octicon ' + icon + '"></span>' +
		'<div><strong>' + esc(value || 0) + '</strong><span>' + esc(label) + '</span><small>' + esc(note) + '</small></div>' +
	'</div>';
}


function format_datetime(value) {
	if (!value) {
		return "";
	}
	return frappe.datetime.str_to_user(value);
}


function esc(value) {
	return frappe.utils.escape_html(String(value === undefined || value === null ? "" : value));
}

})();
