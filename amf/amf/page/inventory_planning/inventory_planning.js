(function() {
"use strict";

frappe.pages["inventory-planning"].on_page_load = function(wrapper) {
	wrapper.inventory_planning = new InventoryPlanningPage(wrapper);
};


function InventoryPlanningPage(wrapper) {
	this.wrapper = wrapper;
	this.page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Inventory Planning"),
		single_column: true
	});
	this.method = "amf.amf.page.inventory_planning.inventory_planning";
	this.data = null;
	this.loading = false;
	this.page_start = 0;
	this.page_length = 100;
	this.setup();
}


InventoryPlanningPage.prototype.setup = function() {
	var self = this;
	var default_company = frappe.defaults.get_user_default("Company") || "";

	this.filters = {
		company: this.page.add_field({
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			fieldname: "company",
			default: default_company,
			reqd: 1,
			change: function() { self.refresh_from_start(); }
		}),
		item_group: this.page.add_field({
			label: __("Item Group"),
			fieldtype: "Link",
			options: "Item Group",
			fieldname: "item_group",
			change: function() { self.refresh_from_start(); }
		}),
		procurement_type: this.page.add_field({
			label: __("Supply mode"),
			fieldtype: "Select",
			fieldname: "procurement_type",
			options: [
				{label: __("All items"), value: "all"},
				{label: __("Purchase"), value: "purchase"},
				{label: __("Manufacture"), value: "manufacture"}
			],
			default: "all",
			change: function() { self.refresh_from_start(); }
		}),
		risk: this.page.add_field({
			label: __("Risk"),
			fieldtype: "Select",
			fieldname: "risk",
			options: [
				{label: __("All risks"), value: "all"},
				{label: __("Critical"), value: "critical"},
				{label: __("Action"), value: "action"},
				{label: __("Watch"), value: "watch"},
				{label: __("Healthy"), value: "healthy"}
			],
			default: "all",
			change: function() { self.refresh_from_start(); }
		}),
		service_level: this.page.add_field({
			label: __("Service level"),
			fieldtype: "Select",
			fieldname: "service_level",
			options: "90\n95\n97.5\n99",
			default: "95",
			change: function() { self.refresh_from_start(); }
		}),
		horizon_days: this.page.add_field({
			label: __("Horizon"),
			fieldtype: "Select",
			fieldname: "horizon_days",
			options: [
				{label: __("60 days"), value: "60"},
				{label: __("90 days"), value: "90"},
				{label: __("180 days"), value: "180"},
				{label: __("365 days"), value: "365"}
			],
			default: "90",
			change: function() { self.refresh_from_start(); }
		}),
		search: this.page.add_field({
			label: __("Item search"),
			fieldtype: "Data",
			fieldname: "search",
			placeholder: __("Code, name or reference"),
			change: function() { self.refresh_from_start(); }
		})
	};

	this.page.set_primary_action(__("Recalculate"), function() {
		self.load();
	}, "octicon octicon-sync");
	this.page.add_inner_button(__("Export current rows"), function() {
		self.export_csv();
	});
	this.page.add_inner_button(__("Sales Order Projection"), function() {
		frappe.set_route("sales-order-stock-projection");
	});
	this.page.add_inner_button(__("Global Inventory"), function() {
		frappe.set_route("global-inventory-dashboard");
	});

	this.$dashboard = $(
		'<div class="inventory-planning-page">' +
			'<section class="ip-hero">' +
				'<div class="ip-hero-copy">' +
					'<div class="ip-eyebrow"><span class="octicon octicon-pulse"></span> ' +
						esc(__("Inventory intelligence")) + '</div>' +
					'<h2>' + esc(__("See the shortage before it happens.")) + '</h2>' +
					'<p>' + esc(__("Physical consumption, actual lead times and dated ERP commitments become one auditable replenishment plan.")) + '</p>' +
				'</div>' +
				'<div class="ip-readonly-badge">' +
					'<span class="octicon octicon-eye"></span>' +
					'<div><strong>' + esc(__("Analysis only")) + '</strong><small>' +
						esc(__("No Item or order is changed")) + '</small></div>' +
				'</div>' +
			'</section>' +
			'<div class="ip-results"></div>' +
		'</div>'
	).appendTo(this.page.main);

	this.$results = this.$dashboard.find(".ip-results");
	this.bind();
	setTimeout(function() { self.load(); }, 0);
};


InventoryPlanningPage.prototype.bind = function() {
	var self = this;
	this.$dashboard.on("click", ".ip-item-row", function(event) {
		if ($(event.target).closest("a, button").length) {
			return;
		}
		self.open_item_detail($(this).attr("data-item-code"));
	});
	this.$dashboard.on("click", ".ip-open-detail", function(event) {
		event.preventDefault();
		self.open_item_detail($(this).attr("data-item-code"));
	});
	this.$dashboard.on("click", ".ip-item-link", function(event) {
		event.preventDefault();
		frappe.set_route("Form", "Item", $(this).attr("data-item-code"));
	});
	this.$dashboard.on("click", ".ip-page-prev", function() {
		self.page_start = Math.max(self.page_start - self.page_length, 0);
		self.load();
	});
	this.$dashboard.on("click", ".ip-page-next", function() {
		if (self.data && self.page_start + self.page_length < self.data.total_rows) {
			self.page_start += self.page_length;
			self.load();
		}
	});
};


InventoryPlanningPage.prototype.refresh_from_start = function() {
	if (this.loading) {
		return;
	}
	this.page_start = 0;
	this.load();
};


InventoryPlanningPage.prototype.get_args = function() {
	return {
		company: this.filters.company.get_value(),
		item_group: this.filters.item_group.get_value(),
		procurement_type: this.filters.procurement_type.get_value() || "all",
		risk: this.filters.risk.get_value() || "all",
		service_level: this.filters.service_level.get_value() || 95,
		horizon_days: this.filters.horizon_days.get_value() || 90,
		lookback_days: 365,
		review_period_days: 30,
		search: this.filters.search.get_value(),
		page_start: this.page_start,
		page_length: this.page_length
	};
};


InventoryPlanningPage.prototype.load = function() {
	var self = this;
	var args = this.get_args();
	if (!args.company) {
		this.$results.html(empty_state(__("Select a company to begin.")));
		return;
	}

	this.loading = true;
	this.set_loading();
	frappe.call({
		method: this.method + ".get_dashboard",
		args: args,
		freeze: false,
		callback: function(response) {
			self.loading = false;
			if (!response.message) {
				return;
			}
			self.data = response.message;
			self.render();
		},
		error: function() {
			self.loading = false;
			self.$results.html(empty_state(__("The inventory analysis could not be loaded.")));
		}
	});
};


InventoryPlanningPage.prototype.set_loading = function() {
	this.$results.html(
		'<div class="ip-loading">' +
			'<div class="ip-loading-head"></div>' +
			'<div class="ip-loading-kpis"><i></i><i></i><i></i><i></i><i></i></div>' +
			'<div class="ip-loading-table"></div>' +
		'</div>'
	);
};


InventoryPlanningPage.prototype.render = function() {
	var data = this.data || {};
	var summary = data.summary || {};
	var rows = data.items || [];
	var filters = data.filters || {};

	this.$results.html(
		'<section class="ip-context">' +
			'<div><span class="octicon octicon-calendar"></span><strong>' +
				esc(__("{0}-day projection", [filters.horizon_days])) + '</strong><span>' +
				esc(__("{0} days of physical history · {1}% service level · Z {2}", [
					filters.lookback_days,
					filters.service_level,
					format_qty(filters.z_score)
				])) + '</span></div>' +
			'<button type="button" class="btn btn-default btn-xs ip-method-button">' +
				'<span class="octicon octicon-info"></span> ' + esc(__("How it works")) +
			'</button>' +
		'</section>' +
		render_kpis(summary) +
		render_risk_strip(summary) +
		'<section class="ip-table-card">' +
			'<div class="ip-table-head">' +
				'<div><h3>' + esc(__("Replenishment priorities")) + '</h3><p>' +
					esc(__("Sorted by first stockout, safety breach and recommended quantity.")) +
				'</p></div>' +
				'<div class="ip-row-count">' +
					esc(__("{0} matching items", [data.total_rows || 0])) +
				'</div>' +
			'</div>' +
			(rows.length ? render_item_table(rows) : empty_state(__("No items match these filters."))) +
			render_pagination(data) +
		'</section>' +
		'<section class="ip-methodology">' +
			'<div class="ip-method-title"><span class="octicon octicon-shield"></span><div><strong>' +
				esc(__("A firm projection, with soft plans kept visible")) + '</strong><span>' +
				esc(__("Material Requests and unlinked Plannings never mask a shortage.")) +
			'</span></div></div>' +
			render_methodology(data.methodology || {}) +
		'</section>'
	);

	this.$results.find(".ip-method-button").on("click", function() {
		var $method = $(".ip-methodology");
		if ($method.length) {
			$("html, body").animate({scrollTop: $method.offset().top - 120}, 250);
		}
	});
};


InventoryPlanningPage.prototype.open_item_detail = function(item_code) {
	var self = this;
	var args = this.get_args();
	args.item_code = item_code;
	delete args.search;
	delete args.item_group;
	delete args.procurement_type;
	delete args.risk;
	delete args.page_start;
	delete args.page_length;

	var dialog = new frappe.ui.Dialog({
		title: __("Inventory plan · {0}", [item_code]),
		fields: [{fieldtype: "HTML", fieldname: "body"}]
	});
	dialog.$wrapper.addClass("ip-detail-dialog");
	dialog.fields_dict.body.$wrapper.html(
		'<div class="ip-detail-loading"><i class="fa fa-spinner fa-spin"></i> ' +
		esc(__("Tracing stock, commitments and lead-time samples…")) + '</div>'
	);
	dialog.show();

	frappe.call({
		method: this.method + ".get_item_detail",
		args: args,
		callback: function(response) {
			if (!response.message) {
				return;
			}
			dialog.set_title(__("Inventory plan · {0}", [item_code]));
			dialog.fields_dict.body.$wrapper.html(render_item_detail(response.message));
			bind_detail_links(dialog);
		},
		error: function() {
			dialog.fields_dict.body.$wrapper.html(empty_state(__("Item detail could not be loaded.")));
		}
	});
};


InventoryPlanningPage.prototype.export_csv = function() {
	var rows = (this.data && this.data.items) || [];
	if (!rows.length) {
		frappe.msgprint(__("There are no displayed rows to export."));
		return;
	}
	var headers = [
		"Risk", "Item", "Item Name", "Supply Mode", "Actual", "Free",
		"Firm Supply", "Firm Demand", "Daily Forecast", "Lead Time",
		"Safety Stock", "Reorder Level", "Minimum Projected",
		"Shortage Date", "Potential Replenish Date", "Recommended Qty", "Action", "Confidence"
	];
	var body = rows.map(function(row) {
		return [
			row.risk, row.item_code, row.item_name, row.procurement_type,
			row.actual_qty, row.free_qty, row.firm_supply_qty, row.firm_demand_qty,
			row.forecast_daily, row.lead_time_days, row.safety_stock,
			row.reorder_level, row.minimum_projected_qty, row.shortage_date || "",
			row.potential_replenish_date || "",
			row.recommended_qty, row.action, row.confidence
		];
	});
	var csv = [headers].concat(body).map(function(row) {
		return row.map(csv_cell).join(",");
	}).join("\n");
	var blob = new Blob([csv], {type: "text/csv;charset=utf-8"});
	var link = document.createElement("a");
	link.href = URL.createObjectURL(blob);
	link.download = "inventory-planning-" + frappe.datetime.get_today() + ".csv";
	document.body.appendChild(link);
	link.click();
	document.body.removeChild(link);
	URL.revokeObjectURL(link.href);
};


function render_kpis(summary) {
	return '<section class="ip-kpis">' +
		kpi("octicon-database", summary.analysed_items, __("Analysed"), __("stock items"), "blue") +
		kpi("octicon-flame", summary.critical_items, __("Critical"), __("stockout forecast"), "red") +
		kpi("octicon-bell", summary.action_items, __("Act now"), __("replenishment due"), "amber") +
		kpi("octicon-eye", summary.watch_items, __("Watch"), __("safety exposure"), "violet") +
		kpi("octicon-check", summary.high_confidence_items, __("High confidence"), __("demand + lead time"), "green") +
	'</section>';
}


function kpi(icon, value, label, note, color) {
	return '<div class="ip-kpi ' + color + '">' +
		'<span class="ip-kpi-icon octicon ' + icon + '"></span>' +
		'<div><strong>' + format_qty(value || 0) + '</strong><span>' +
			esc(label) + '</span><small>' + esc(note) + '</small></div>' +
	'</div>';
}


function render_risk_strip(summary) {
	var total = Math.max(Number(summary.analysed_items || 0), 1);
	var segments = [
		{key: "critical_items", label: __("Critical"), css: "critical"},
		{key: "action_items", label: __("Action"), css: "action"},
		{key: "watch_items", label: __("Watch"), css: "watch"},
		{key: "healthy_items", label: __("Healthy"), css: "healthy"}
	];
	return '<section class="ip-risk-strip">' +
		'<div class="ip-risk-labels">' + segments.map(function(segment) {
			return '<span><i class="' + segment.css + '"></i>' + esc(segment.label) +
				' <b>' + format_qty(summary[segment.key] || 0) + '</b></span>';
		}).join("") + '</div>' +
		'<div class="ip-risk-bar">' + segments.map(function(segment) {
			var count = Number(summary[segment.key] || 0);
			var width = count ? Math.max((count / total) * 100, 1.2) : 0;
			return '<i class="' + segment.css + '" style="width:' + width + '%"></i>';
		}).join("") + '</div>' +
	'</section>';
}


function render_item_table(rows) {
	return '<div class="ip-table-scroll"><table class="table ip-priority-table">' +
		'<thead><tr>' +
			'<th>' + esc(__("Priority / item")) + '</th>' +
			'<th>' + esc(__("Mode")) + '</th>' +
			'<th class="text-right">' + esc(__("Actual / free")) + '</th>' +
			'<th class="text-right">' + esc(__("Firm in / out")) + '</th>' +
			'<th class="text-right">' + esc(__("Demand")) + '</th>' +
			'<th class="text-right">' + esc(__("Lead time")) + '</th>' +
			'<th class="text-right">' + esc(__("SS / reorder")) + '</th>' +
			'<th class="text-right">' + esc(__("Projection low")) + '</th>' +
			'<th>' + esc(__("First risk")) + '</th>' +
			'<th>' + esc(__("Potential replenish")) + '</th>' +
			'<th>' + esc(__("Recommendation")) + '</th>' +
		'</tr></thead><tbody>' +
		rows.map(render_item_row).join("") +
		'</tbody></table></div>';
}


function render_item_row(row) {
	var first_risk = row.shortage_date || row.safety_breach_date;
	var demand_note = [
		format_qty(row.demand_days) + " " + __("active days"),
		pattern_label(row.demand_pattern)
	].join(" · ");
	var lead_note = format_qty(row.lead_time_samples) + " " + __("samples") +
		" · " + confidence_label(row.lead_time_confidence);
	var min_class = Number(row.minimum_projected_qty || 0) < 0 ? "negative" :
		(Number(row.minimum_projected_qty || 0) < Number(row.safety_stock || 0) ? "warning" : "positive");

	return '<tr class="ip-item-row" data-item-code="' + esc(row.item_code) + '">' +
		'<td><div class="ip-priority-item">' +
			risk_pill(row.risk) +
			'<div><a href="#" class="ip-item-link" data-item-code="' + esc(row.item_code) + '">' +
				esc(row.item_code) + '</a><strong>' + esc(row.item_name || row.item_code) + '</strong>' +
				'<small>' + esc([row.reference_code, row.item_group].filter(Boolean).join(" · ")) + '</small></div>' +
		'</div></td>' +
		'<td><span class="ip-mode ' + (row.procurement_type === "Purchase" ? "buy" : "make") + '">' +
			'<span class="octicon ' + (row.procurement_type === "Purchase" ? "octicon-package" : "octicon-gear") + '"></span> ' +
			esc(row.procurement_type) + '</span><small class="ip-cell-note">' +
			esc(confidence_label(row.confidence)) + '</small></td>' +
		'<td class="text-right ip-number"><strong>' + format_qty(row.actual_qty) + '</strong><span>' +
			format_qty(row.free_qty) + ' ' + esc(row.stock_uom || "") + '</span></td>' +
		'<td class="text-right ip-number"><strong class="positive">+' + format_qty(row.firm_supply_qty) +
			'</strong><span class="negative">−' + format_qty(row.firm_demand_qty) + '</span></td>' +
		'<td class="text-right ip-number"><strong>' + format_qty(row.forecast_daily) + '/d</strong><span>' +
			esc(demand_note) + '</span></td>' +
		'<td class="text-right ip-number"><strong>' + format_qty(row.lead_time_days) + ' d</strong><span>± ' +
			format_qty(row.lead_time_std_days) + ' · ' + esc(lead_note) + '</span></td>' +
		'<td class="text-right ip-number"><strong>' + format_qty(row.safety_stock) + '</strong><span>' +
			format_qty(row.reorder_level) + ' ' + esc(row.stock_uom || "") + '</span></td>' +
		'<td class="text-right ip-projection-low ' + min_class + '"><strong>' +
			format_qty(row.minimum_projected_qty) + '</strong><span>' +
			esc(row.stock_uom || "") + '</span></td>' +
		'<td>' + (first_risk ? '<strong class="ip-date">' + format_date(first_risk) + '</strong><small class="ip-cell-note">' +
			esc(row.shortage_date ? __("Stockout") : __("Safety breach")) + '</small>' :
			'<span class="ip-no-risk"><span class="octicon octicon-check"></span> ' + esc(__("Covered")) + '</span>') + '</td>' +
		'<td>' + (row.potential_replenish_date ? '<strong class="ip-date">' +
			format_date(row.potential_replenish_date) + '</strong><small class="ip-cell-note">' +
			esc(row.potential_replenish_overdue ? __("Overdue open PO") : __("Earliest open PO")) +
			'</small>' : '<span class="text-muted">—</span>') + '</td>' +
		'<td><div class="ip-action-cell"><strong>' + esc(row.action) + '</strong><span>' +
			(row.recommended_qty ? format_qty(row.recommended_qty) + ' ' + esc(row.stock_uom || "") : esc(__("No quantity"))) +
			'</span><button class="btn btn-default btn-xs ip-open-detail" data-item-code="' + esc(row.item_code) + '">' +
			esc(__("Audit")) + '</button></div></td>' +
	'</tr>';
}


function render_pagination(data) {
	var total = Number(data.total_rows || 0);
	if (!total) {
		return "";
	}
	var start = Number(data.page_start || 0);
	var length = Number(data.page_length || 100);
	var end = Math.min(start + length, total);
	return '<div class="ip-pagination"><span>' +
		esc(__("Showing {0}–{1} of {2}", [start + 1, end, total])) + '</span><div>' +
		'<button class="btn btn-default btn-sm ip-page-prev"' + (start <= 0 ? ' disabled' : '') + '>' +
			'<span class="octicon octicon-chevron-left"></span> ' + esc(__("Previous")) + '</button>' +
		'<button class="btn btn-default btn-sm ip-page-next"' + (end >= total ? ' disabled' : '') + '>' +
			esc(__("Next")) + ' <span class="octicon octicon-chevron-right"></span></button>' +
		'</div></div>';
}


function render_methodology(methodology) {
	var entries = [
		["octicon-arrow-down", __("Physical demand"), methodology.physical_history],
		["octicon-clock", __("Lead time"), methodology.lead_time],
		["octicon-shield", __("Safety policy"), methodology.safety_stock],
		["octicon-calendar", __("Firm horizon"), methodology.future_demand],
		["octicon-git-merge", __("Forecast netting"), methodology.forecast_netting],
		["octicon-home", __("Warehouse scope"), methodology.warehouse_scope]
	];
	return '<div class="ip-method-grid">' + entries.map(function(entry) {
		return '<div><span class="octicon ' + entry[0] + '"></span><strong>' +
			esc(entry[1]) + '</strong><p>' + esc(entry[2] || "") + '</p></div>';
	}).join("") + '</div>';
}


function render_item_detail(detail) {
	var item = detail.item || {};
	var policy = detail.policy || {};
	var demand = detail.demand_profile || {};
	var lead = detail.lead_time || {};
	var projection = detail.projection || {};

	return '<div class="ip-detail">' +
		'<section class="ip-detail-identity">' +
			'<div><span class="ip-detail-risk">' + risk_pill(item.risk) + '</span><h3>' +
				'<a href="#" class="ip-detail-doc-link" data-doctype="Item" data-name="' + esc(item.item_code) + '">' +
				esc(item.item_code) + '</a></h3><p>' + esc(item.item_name || item.item_code) + '</p></div>' +
			'<div class="ip-detail-action"><small>' + esc(__("Recommended action")) + '</small><strong>' +
				esc(item.action) + '</strong><span>' + format_qty(item.recommended_qty) + ' ' +
				esc(item.stock_uom || "") + '</span></div>' +
		'</section>' +
		'<section class="ip-detail-metrics">' +
			detail_metric(__("Daily forecast"), format_qty(demand.forecast_daily), pattern_label(demand.pattern)) +
			detail_metric(__("Lead time"), format_qty(lead.average_days) + " d", "± " + format_qty(lead.std_days) + " · " + lead.sample_count + " " + __("samples")) +
			detail_metric(__("Safety stock"), format_qty(policy.safety_stock), __("Current") + " " + format_qty(item.current_safety_stock)) +
			detail_metric(__("Reorder level"), format_qty(policy.reorder_level), __("Current") + " " + format_qty(item.current_reorder_level)) +
			detail_metric(__("Potential replenish"), item.potential_replenish_date ? format_date(item.potential_replenish_date) : "—", item.potential_replenish_date ? (item.potential_replenish_overdue ? __("Overdue open PO schedule date") : __("Earliest open PO schedule date")) : __("No open Purchase Order")) +
			detail_metric(__("Projection low"), format_qty(projection.minimum_projected_qty), projection.shortage_date ? __("Stockout") + " " + format_date(projection.shortage_date) : __("No stockout")) +
		'</section>' +
		'<section class="ip-equation-card">' +
			'<div><span class="octicon octicon-beaker"></span><strong>' + esc(__("Policy calculation")) + '</strong></div>' +
			'<code>SS = ' + format_qty(policy.z_score) + ' × √(' +
				format_qty(lead.average_days) + ' × ' + format_qty(policy.daily_std) + '² + ' +
				format_qty(policy.daily_mean) + '² × ' + format_qty(lead.std_days) + '²) = ' +
				format_qty(policy.safety_stock) + '</code>' +
			'<p>' + esc(__("Reorder level = lead-time demand {0} + safety stock {1} = {2}", [
				format_qty(policy.lead_time_demand),
				format_qty(policy.safety_stock),
				format_qty(policy.reorder_level)
			])) + '</p>' +
		'</section>' +
		'<section class="ip-detail-section"><div class="ip-detail-title"><div><h4>' +
			esc(__("Time-phased projection")) + '</h4><p>' +
			esc(__("Solid line excludes soft supply; the dashed scenario includes it.")) +
			'</p></div></div>' + render_projection_chart(detail.weekly_projection || [], policy.safety_stock) +
			render_weekly_table(detail.weekly_projection || [], item.stock_uom) + '</section>' +
		'<div class="ip-detail-split">' +
			'<section class="ip-detail-section"><div class="ip-detail-title"><div><h4>' +
				esc(__("Historical outputs")) + '</h4><p>' +
				esc(__("Physical consumption used by the demand model.")) + '</p></div></div>' +
				render_history_sources(detail.historical_demand_sources || [], item.stock_uom, "demand") + '</section>' +
			'<section class="ip-detail-section"><div class="ip-detail-title"><div><h4>' +
				esc(__("Historical inputs")) + '</h4><p>' +
				esc(__("Physical receipts and completed production.")) + '</p></div></div>' +
				render_history_sources(detail.historical_supply_sources || [], item.stock_uom, "supply") + '</section>' +
		'</div>' +
		'<section class="ip-detail-section"><div class="ip-detail-title"><div><h4>' +
			esc(__("Lead-time evidence")) + '</h4><p>' +
			esc(lead.source || "") + '</p></div></div>' +
			render_lead_samples(detail.lead_samples || []) + '</section>' +
		'<section class="ip-detail-section"><div class="ip-detail-title"><div><h4>' +
			esc(__("Future commitment ledger")) + '</h4><p>' +
			esc(__("Firm events drive the main projection; soft events are scenario-only.")) +
			'</p></div></div>' + render_future_events(detail.future_events || [], item.stock_uom) + '</section>' +
		'<section class="ip-detail-section"><div class="ip-detail-title"><div><h4>' +
			esc(__("ERPNext Bin reconciliation")) + '</h4><p>' +
			esc(__("Warehouse values are shown for audit, not used as a substitute for dated events.")) +
			'</p></div></div>' + render_warehouse_stock(detail.warehouse_stock || [], item.stock_uom) + '</section>' +
		'<section class="ip-detail-section"><div class="ip-detail-title"><div><h4>' +
			esc(__("Recent physical movements")) + '</h4><p>' +
			esc(__("Transfers are visible here but excluded from consumption.")) +
			'</p></div></div>' + render_recent_movements(detail.recent_movements || [], item.stock_uom) + '</section>' +
	'</div>';
}


function detail_metric(label, value, note) {
	return '<div><small>' + esc(label) + '</small><strong>' + esc(value) +
		'</strong><span>' + esc(note || "") + '</span></div>';
}


function render_projection_chart(weeks, safety_stock) {
	if (!weeks.length) {
		return empty_state(__("No projection points."));
	}
	var width = 900;
	var height = 230;
	var padding = 34;
	var values = [];
	weeks.forEach(function(week) {
		values.push(Number(week.closing_qty || 0));
		values.push(Number(week.closing_with_soft_qty || 0));
	});
	values.push(Number(safety_stock || 0));
	values.push(0);
	var min = Math.min.apply(Math, values);
	var max = Math.max.apply(Math, values);
	if (max === min) { max += 1; min -= 1; }
	var x = function(index) {
		return padding + (weeks.length === 1 ? 0 : index * (width - padding * 2) / (weeks.length - 1));
	};
	var y = function(value) {
		return padding + (max - value) * (height - padding * 2) / (max - min);
	};
	var firm = weeks.map(function(week, index) {
		return x(index) + "," + y(Number(week.closing_qty || 0));
	}).join(" ");
	var soft = weeks.map(function(week, index) {
		return x(index) + "," + y(Number(week.closing_with_soft_qty || 0));
	}).join(" ");
	var safety_y = y(Number(safety_stock || 0));
	var zero_y = y(0);

	return '<div class="ip-projection-chart">' +
		'<svg viewBox="0 0 ' + width + ' ' + height + '" role="img" aria-label="' + esc(__("Projected inventory chart")) + '">' +
			'<line x1="' + padding + '" y1="' + zero_y + '" x2="' + (width - padding) + '" y2="' + zero_y + '" class="zero"></line>' +
			'<line x1="' + padding + '" y1="' + safety_y + '" x2="' + (width - padding) + '" y2="' + safety_y + '" class="safety"></line>' +
			'<text x="' + (padding + 4) + '" y="' + (safety_y - 7) + '">' + esc(__("Safety")) + ' ' + format_qty(safety_stock) + '</text>' +
			'<polyline points="' + soft + '" class="soft-line"></polyline>' +
			'<polyline points="' + firm + '" class="firm-line"></polyline>' +
			weeks.map(function(week, index) {
				return '<circle cx="' + x(index) + '" cy="' + y(Number(week.closing_qty || 0)) + '" r="4" class="firm-point"><title>' +
					esc(format_date(week.to_date) + ": " + format_qty(week.closing_qty)) + '</title></circle>';
			}).join("") +
		'</svg>' +
		'<div class="ip-chart-legend"><span><i class="firm"></i>' + esc(__("Firm projection")) +
			'</span><span><i class="soft"></i>' + esc(__("With soft supply")) +
			'</span><span><i class="safety"></i>' + esc(__("Safety stock")) + '</span></div>' +
	'</div>';
}


function render_weekly_table(rows, uom) {
	if (!rows.length) { return ""; }
	return '<div class="ip-mini-table-scroll"><table class="table ip-mini-table"><thead><tr>' +
		'<th>' + esc(__("Week")) + '</th><th class="text-right">' + esc(__("Opening")) +
		'</th><th class="text-right">' + esc(__("Firm in")) + '</th><th class="text-right">' +
		esc(__("Firm out")) + '</th><th class="text-right">' + esc(__("Forecast")) +
		'</th><th class="text-right">' + esc(__("Closing")) + '</th><th class="text-right">' +
		esc(__("With soft")) + '</th></tr></thead><tbody>' +
		rows.map(function(row) {
			return '<tr><td><strong>' + format_date(row.from_date) + '</strong><span> → ' +
				format_date(row.to_date) + '</span></td><td class="text-right">' +
				format_qty(row.opening_qty) + '</td><td class="text-right positive">+' +
				format_qty(row.firm_supply_qty) + '</td><td class="text-right negative">−' +
				format_qty(row.firm_demand_qty) + '</td><td class="text-right">−' +
				format_qty(row.forecast_residual_qty) + '</td><td class="text-right"><strong>' +
				format_qty(row.closing_qty) + '</strong></td><td class="text-right">' +
				format_qty(row.closing_with_soft_qty) + ' ' + esc(uom || "") + '</td></tr>';
		}).join("") + '</tbody></table></div>';
}


function render_history_sources(rows, uom, flow) {
	if (!rows.length) {
		return empty_state(
			flow === "supply" ?
				__("No qualifying physical input in the lookback window.") :
				__("No qualifying physical demand in the lookback window.")
		);
	}
	return '<div class="ip-source-list ' + esc(flow || "demand") + '">' + rows.map(function(row) {
		return '<div><span class="octicon ' + (flow === "supply" ? "octicon-arrow-up" : "octicon-arrow-down") + '"></span><strong>' +
			esc(row.source) + '</strong><b>' + format_qty(row.qty) + ' ' + esc(uom || "") +
			'</b><small>' + format_qty(row.active_days) + ' ' + esc(__("active days")) + '</small></div>';
	}).join("") + '</div>';
}


function render_lead_samples(rows) {
	if (!rows.length) { return empty_state(__("No linked historical samples; Item lead time is used.")); }
	return '<div class="ip-sample-list">' + rows.slice(0, 12).map(function(row) {
		return '<div><strong>' + format_qty(row.days) + ' d</strong><span>' +
			document_link(row.start_document, row.source.indexOf("PO") === 0 ? "Purchase Order" : "Work Order") +
			' → ' + document_link(row.finish_document, row.source.indexOf("PO") === 0 ? "Purchase Receipt" : "Stock Entry") +
			'</span><small>' + esc(format_date(row.start_date) + " → " + format_date(row.finish_date)) + '</small></div>';
	}).join("") + '</div>';
}


function render_future_events(rows, uom) {
	if (!rows.length) { return empty_state(__("No firm or soft events inside the horizon.")); }
	return '<div class="ip-mini-table-scroll"><table class="table ip-mini-table"><thead><tr>' +
		'<th>' + esc(__("Date")) + '</th><th>' + esc(__("Signal")) + '</th><th>' +
		esc(__("Document")) + '</th><th>' + esc(__("Party / warehouse")) +
		'</th><th class="text-right">' + esc(__("Quantity")) + '</th></tr></thead><tbody>' +
		rows.map(function(row) {
			var is_supply = row.direction === "supply";
			return '<tr><td>' + format_date(row.date) + '</td><td><span class="ip-event ' +
				(is_supply ? "supply" : "demand") + '">' + esc(row.source) + '</span> ' +
				(row.confidence === "soft" ? '<span class="ip-soft-tag">' + esc(__("Soft")) + '</span>' : '') +
				'</td><td>' + document_link(row.document_name, row.document_type) + '</td><td>' +
				esc([row.party, row.warehouse].filter(Boolean).join(" · ") || "—") +
				'</td><td class="text-right ' + (is_supply ? "positive" : "negative") + '"><strong>' +
				(is_supply ? "+" : "−") + format_qty(row.qty) + '</strong> ' + esc(uom || "") + '</td></tr>';
		}).join("") + '</tbody></table></div>';
}


function render_warehouse_stock(rows, uom) {
	if (!rows.length) { return empty_state(__("No usable warehouse bins.")); }
	return '<div class="ip-mini-table-scroll"><table class="table ip-mini-table"><thead><tr>' +
		'<th>' + esc(__("Warehouse")) + '</th><th class="text-right">' + esc(__("Actual")) +
		'</th><th class="text-right">' + esc(__("Reserved sales")) + '</th><th class="text-right">' +
		esc(__("Reserved WO")) + '</th><th class="text-right">' + esc(__("Ordered")) +
		'</th><th class="text-right">' + esc(__("Planned")) + '</th><th class="text-right">' +
		esc(__("ERP projected")) + '</th></tr></thead><tbody>' +
		rows.map(function(row) {
			return '<tr><td><strong>' + esc(row.warehouse_name || row.warehouse) +
				'</strong><span>' + esc(row.warehouse) + '</span></td><td class="text-right">' +
				format_qty(row.actual_qty) + '</td><td class="text-right">' +
				format_qty(row.reserved_sales_qty) + '</td><td class="text-right">' +
				format_qty(row.reserved_production_qty) + '</td><td class="text-right">' +
				format_qty(row.ordered_qty) + '</td><td class="text-right">' +
				format_qty(row.planned_qty) + '</td><td class="text-right"><strong>' +
				format_qty(row.erp_projected_qty) + '</strong> ' + esc(uom || "") + '</td></tr>';
		}).join("") + '</tbody></table></div>';
}


function render_recent_movements(rows, uom) {
	if (!rows.length) { return empty_state(__("No stock-ledger movements.")); }
	return '<div class="ip-mini-table-scroll"><table class="table ip-mini-table"><thead><tr>' +
		'<th>' + esc(__("Date")) + '</th><th>' + esc(__("Class")) + '</th><th>' +
		esc(__("Document")) + '</th><th>' + esc(__("Warehouse")) +
		'</th><th class="text-right">' + esc(__("Movement")) + '</th></tr></thead><tbody>' +
		rows.slice(0, 30).map(function(row) {
			return '<tr><td>' + format_date(row.posting_date) + '</td><td><span class="ip-flow-class ' +
				esc(row.flow_class) + '">' + esc(flow_label(row.flow_class)) + '</span>' +
				(row.purpose ? '<small>' + esc(row.purpose) + '</small>' : '') + '</td><td>' +
				document_link(row.voucher_no, row.voucher_type) + '</td><td>' +
				esc(row.warehouse) + '</td><td class="text-right ' + (Number(row.qty) >= 0 ? "positive" : "negative") +
				'"><strong>' + (Number(row.qty) > 0 ? "+" : "") + format_qty(row.qty) +
				'</strong> ' + esc(uom || "") + '</td></tr>';
		}).join("") + '</tbody></table></div>';
}


function bind_detail_links(dialog) {
	dialog.$wrapper.find(".ip-detail-doc-link").on("click", function(event) {
		event.preventDefault();
		frappe.set_route("Form", $(this).attr("data-doctype"), $(this).attr("data-name"));
		dialog.hide();
	});
}


function document_link(name, doctype) {
	if (!name || !doctype) { return '<span class="text-muted">—</span>'; }
	return '<a href="#" class="ip-detail-doc-link" data-doctype="' + esc(doctype) +
		'" data-name="' + esc(name) + '">' + esc(name) + '</a>';
}


function risk_pill(risk) {
	var labels = {
		critical: __("Critical"),
		action: __("Action"),
		watch: __("Watch"),
		healthy: __("Healthy")
	};
	var icons = {
		critical: "octicon-flame",
		action: "octicon-bell",
		watch: "octicon-eye",
		healthy: "octicon-check"
	};
	risk = labels[risk] ? risk : "watch";
	return '<span class="ip-risk ' + risk + '"><span class="octicon ' +
		icons[risk] + '"></span> ' + esc(labels[risk]) + '</span>';
}


function pattern_label(pattern) {
	return {
		no_history: __("No history"),
		new: __("New"),
		intermittent: __("Intermittent"),
		variable: __("Variable"),
		stable: __("Stable")
	}[pattern] || __("Unknown");
}


function confidence_label(confidence) {
	return {
		low: __("Low confidence"),
		medium: __("Medium confidence"),
		high: __("High confidence")
	}[confidence] || __("Low confidence");
}


function flow_label(flow) {
	return {
		consumption: __("Consumption"),
		supply: __("Supply"),
		transfer: __("Transfer"),
		adjustment: __("Adjustment"),
		other: __("Other")
	}[flow] || __("Other");
}


function format_date(value) {
	if (!value) { return "—"; }
	try {
		return frappe.datetime.str_to_user(value);
	} catch (error) {
		return String(value);
	}
}


function format_qty(value) {
	var number = Number(value || 0);
	if (!isFinite(number)) { return "0"; }
	number = Math.abs(number) < 0.0000001 ? 0 : number;
	return number.toLocaleString(undefined, {minimumFractionDigits: 0, maximumFractionDigits: 2});
}


function empty_state(message) {
	return '<div class="ip-empty"><span class="octicon octicon-package"></span><p>' +
		esc(message) + '</p></div>';
}


function csv_cell(value) {
	var text = String(value === undefined || value === null ? "" : value);
	return '"' + text.replace(/"/g, '""') + '"';
}


function esc(value) {
	return frappe.utils.escape_html(String(value === undefined || value === null ? "" : value));
}

})();
