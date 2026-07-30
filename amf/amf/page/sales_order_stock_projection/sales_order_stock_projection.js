(function() {
"use strict";

frappe.pages["sales-order-stock-projection"].on_page_load = function(wrapper) {
	wrapper.sales_order_stock_projection = new SalesOrderStockProjection(wrapper);
};


function SalesOrderStockProjection(wrapper) {
	this.wrapper = wrapper;
	this.page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Sales Order Stock Projection"),
		single_column: true
	});
	this.method = "amf.amf.page.sales_order_stock_projection.sales_order_stock_projection.get_dashboard";
	this.data = null;
	this.active_tab = "orders";
	this.metric = "actual_qty";
	this.search_text = "";
	this.make();
}


SalesOrderStockProjection.prototype.make = function() {
	var self = this;
	var default_company = frappe.defaults.get_user_default("Company") ||
		frappe.defaults.get_global_default("Company");

	this.controls = {
		company: this.page.add_field({
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: default_company,
			reqd: 1
		}),
		to_date: this.page.add_field({
			fieldname: "to_date",
			label: __("Delivery through"),
			fieldtype: "Date"
		}),
		customer: this.page.add_field({
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer"
		}),
		include_on_hold: this.page.add_field({
			fieldname: "include_on_hold",
			label: __("Include On Hold"),
			fieldtype: "Check",
			default: 0
		})
	};

	this.page.set_primary_action(__("Refresh projection"), function() {
		self.load();
	}, "octicon octicon-sync");
	this.page.add_inner_button(__("Global Inventory"), function() {
		frappe.set_route("global-inventory-dashboard");
	});
	this.page.add_inner_button(__("Inventory Planning"), function() {
		frappe.set_route("inventory-planning");
	});

	this.$dashboard = $(
		'<div class="sales-order-stock-projection">' +
			'<section class="sosp-hero">' +
				'<div>' +
					'<div class="sosp-eyebrow">' + esc(__("SUBMITTED SALES ORDER DEMAND")) + '</div>' +
					'<h2>' + esc(__("Can we fulfill what we have sold?")) + '</h2>' +
					'<p>' + esc(__("A delivery-priority view of outstanding orders, current stock, expected stock and shortages.")) + '</p>' +
				'</div>' +
				'<div class="sosp-generated"></div>' +
			'</section>' +
			'<div class="sosp-results"></div>' +
		'</div>'
	).appendTo(this.page.main);

	this.$results = this.$dashboard.find(".sosp-results");
	this.bind_events();
	this.render_loading();
	setTimeout(function() { self.load(); }, 0);
};


SalesOrderStockProjection.prototype.bind_events = function() {
	var self = this;

	this.$results.on("click", ".sosp-tab", function() {
		self.active_tab = $(this).attr("data-tab");
		self.update_active_tab();
	});

	this.$results.on("change", ".sosp-metric-select", function() {
		self.metric = $(this).val();
		self.render_results();
	});

	this.$results.on("input", ".sosp-table-search", function() {
		self.search_text = $.trim($(this).val() || "").toLowerCase();
		self.apply_search();
	});

	this.$results.on("click", ".sosp-order-link", function(event) {
		event.preventDefault();
		frappe.set_route("Form", "Sales Order", $(this).attr("data-sales-order"));
	});

	this.$results.on("click", ".sosp-item-link", function(event) {
		event.preventDefault();
		frappe.set_route("Form", "Item", $(this).attr("data-item-code"));
	});

	this.$results.on("click", ".sosp-bom-link", function(event) {
		event.preventDefault();
		frappe.set_route("Form", "BOM", $(this).attr("data-bom-no"));
	});

	this.$results.on("click", ".sosp-customer-link", function(event) {
		event.preventDefault();
		frappe.set_route("Form", "Customer", $(this).attr("data-customer"));
	});
};


SalesOrderStockProjection.prototype.get_filters = function() {
	return {
		company: this.controls.company.get_value(),
		to_date: this.controls.to_date.get_value() || null,
		customer: this.controls.customer.get_value() || null,
		include_on_hold: this.controls.include_on_hold.get_value() ? 1 : 0
	};
};


SalesOrderStockProjection.prototype.load = function() {
	var self = this;
	var filters = this.get_filters();
	if (!filters.company) {
		frappe.msgprint(__("Please select a Company."));
		return;
	}

	this.render_loading();
	this.page.btn_primary.prop("disabled", true);
	frappe.call({
		method: this.method,
		args: filters,
		callback: function(response) {
			self.page.btn_primary.prop("disabled", false);
			if (!response.message) {
				return;
			}
			self.data = response.message;
			self.active_tab = "orders";
			self.search_text = "";
			self.render_results();
		},
		error: function() {
			self.page.btn_primary.prop("disabled", false);
		}
	});
};


SalesOrderStockProjection.prototype.render_loading = function() {
	this.$dashboard.find(".sosp-generated").empty();
	this.$results.html(
		'<div class="sosp-skeleton">' +
			'<div class="sosp-skeleton-row">' +
				'<span></span><span></span><span></span><span></span><span></span>' +
			'</div>' +
			'<div class="sosp-skeleton-table"></div>' +
		'</div>'
	);
};


SalesOrderStockProjection.prototype.render_results = function() {
	if (!this.data) {
		return;
	}

	var summary = this.data.summary || {};
	var orders = this.data.orders || [];
	var items = this.data.items || [];
	var demand_lines = this.data.demand_lines || [];
	var shortages = this.data.shortages || [];
	var component_lines = this.data.component_lines || [];
	var component_shortages = this.data.component_shortages || [];
	var warnings = this.data.warnings || [];
	var self = this;
	var material_gap_roots = {};
	component_lines.forEach(function(row) {
		if (Number(row.shortage_qty || 0) > 0.000001) {
			material_gap_roots[row.demand_item_code] = true;
		}
	});
	var shortage_roots = items.filter(function(row) {
		return Number(row.shortage_qty || 0) > 0.000001 || material_gap_roots[row.item_code];
	});

	this.$dashboard.find(".sosp-generated").html(
		'<span class="octicon octicon-clock"></span> ' +
		esc(__("Calculated {0}", [format_datetime(this.data.generated_at)]))
	);

	if (!orders.length) {
		this.$results.html(
			'<div class="sosp-empty"><span class="octicon octicon-check"></span>' +
			'<h3>' + esc(__("No outstanding submitted Sales Orders")) + '</h3>' +
			'<p>' + esc(__("No open demand matches the selected company and filters.")) + '</p></div>'
		);
		return;
	}

	this.$results.html(
		'<section class="sosp-kpis">' +
			kpi("octicon-list-unordered", summary.sales_orders, __("Open orders"), summary.overdue_orders + " " + __("overdue"), "blue") +
			kpi("octicon-check", summary.ready_orders, __("Ready from stock"), __("All sold lines covered"), "green") +
			kpi("octicon-tools", summary.buildable_orders, __("Buildable"), summary.subassemblies_to_build + " " + __("sub-assemblies to build"), "violet") +
			kpi("octicon-alert", summary.at_risk_orders, __("At risk"), summary.blocked_orders + " " + __("fully blocked"), "red") +
			kpi("octicon-package", summary.component_shortage_items, __("Material gaps"), summary.blocking_component_items + " " + __("blocking components"), "amber") +
			kpi("octicon-credit-card", format_money(summary.outstanding_value, summary.currency), __("Outstanding value"), summary.currency || "", "violet", true) +
		'</section>' +
		(warnings.length ? '<section class="sosp-warning"><span class="octicon octicon-alert"></span><div>' +
			warnings.map(function(message) { return '<span>' + esc(message) + '</span>'; }).join("") + '</div></section>' : '') +
		'<section class="sosp-method">' +
			'<span class="octicon octicon-info"></span>' +
			'<div><strong>' + esc(__("How this projection works")) + '</strong>' +
			'<span>' + esc((this.data.methodology || {}).bom || "") + ' ' +
				esc((this.data.methodology || {}).allocation || "") + ' ' +
				esc((this.data.methodology || {}).warehouse_scope || "") + ' ' +
				esc(__("Actual stock is used for allocation; reserved stock is shown separately to avoid counting Sales Order demand twice.")) + '</span></div>' +
		'</section>' +
		'<section class="sosp-data-card">' +
			'<div class="sosp-data-head">' +
				'<div class="sosp-tabs" role="tablist">' +
					tab("orders", __("Order Readiness"), orders.length) +
					tab("items", __("Sold Items"), items.length) +
					tab("allocation", __("Priority Allocation"), demand_lines.length) +
					tab("shortages", __("Shortages"), shortages.length + component_shortages.length) +
					tab("shortage_groups", __("Shortages by Item Group"), component_shortages.length) +
				'</div>' +
				'<div class="sosp-tools">' +
					'<div class="sosp-search-wrap"><span class="octicon octicon-search"></span>' +
					'<input class="form-control input-sm sosp-table-search" value="' + esc(this.search_text) + '" placeholder="' + esc(__("Search this view")) + '"></div>' +
					'<select class="form-control input-sm sosp-metric-select">' +
						metric_option("actual_qty", __("Warehouse: actual"), this.metric) +
						metric_option("available_qty", __("Warehouse: available"), this.metric) +
						metric_option("projected_qty", __("Warehouse: projected"), this.metric) +
					'</select>' +
				'</div>' +
			'</div>' +
			'<div class="sosp-panel" data-panel="orders">' + this.render_orders(orders) + '</div>' +
			'<div class="sosp-panel" data-panel="items">' + this.render_items(items, false) + '</div>' +
			'<div class="sosp-panel" data-panel="allocation">' + this.render_allocation(demand_lines) + '</div>' +
			'<div class="sosp-panel" data-panel="shortages">' + this.render_items(shortage_roots, true) + '</div>' +
			'<div class="sosp-panel" data-panel="shortage_groups">' + this.render_shortages_by_group(component_shortages) + '</div>' +
		'</section>' +
		'<div class="sosp-footnote">' +
			'<span class="octicon octicon-git-compare"></span> ' +
			esc(__("BOM material demand is net: finished goods and sub-assemblies already in stock suppress demand for their child components. Product Bundles use their packed stock items.")) +
		'</div>'
	);

	this.update_active_tab();
	this.apply_search();
};


SalesOrderStockProjection.prototype.render_orders = function(orders) {
	var demand_lines = this.data.demand_lines || [];
	var component_lines = this.data.component_lines || [];
	var currency = this.data.currency;

	return '<div class="sosp-table-scroll"><table class="table sosp-table sosp-order-table">' +
		'<thead><tr>' +
			'<th>' + esc(__("Readiness")) + '</th>' +
			'<th>' + esc(__("Order / BOM hierarchy")) + '</th>' +
			'<th>' + esc(__("Customer / type")) + '</th>' +
			'<th>' + esc(__("Delivery")) + '</th>' +
			'<th class="text-right">' + esc(__("Lines / demand")) + '</th>' +
			'<th class="text-right">' + esc(__("Covered / stock")) + '</th>' +
			'<th class="text-right">' + esc(__("FG gap / build")) + '</th>' +
			'<th class="text-right">' + esc(__("Material gaps / projected")) + '</th>' +
			'<th class="text-right">' + esc(__("Value")) + '</th>' +
		'</tr></thead><tbody>' +
		orders.map(function(row) {
			var group = "order:" + row.sales_order;
			var search = [row.sales_order, row.customer, row.customer_name, row.status].join(" ").toLowerCase();
			var html = '<tr class="sosp-order-summary-row"' + tree_attributes(group, search) + '>' +
				'<td>' + status_pill(row.status, true) + '</td>' +
				'<td><a href="#" class="sosp-order-link" data-sales-order="' + esc(row.sales_order) + '"><strong>' + esc(row.sales_order) + '</strong></a>' +
					'<small class="sosp-cell-note">' + esc(row.sales_order_status || "") + '</small></td>' +
				'<td><a href="#" class="sosp-customer-link" data-customer="' + esc(row.customer) + '">' + esc(row.customer_name || row.customer) + '</a>' +
					'<small class="sosp-cell-note">' + esc(row.customer || "") + '</small></td>' +
				'<td>' + delivery_date_cell(row.delivery_date, row.days_to_delivery, row.is_overdue) + '</td>' +
				'<td class="text-right">' + format_qty(row.stock_line_count) + '</td>' +
				'<td class="text-right"><div class="sosp-readiness"><span><i style="width:' + clamp(row.readiness_percent, 0, 100) + '%"></i></span><b>' + format_qty(row.readiness_percent) + '%</b></div></td>' +
				'<td class="text-right ' + (row.stock_gap_item_count ? 'sosp-build-color' : '') + '">' + format_qty(row.stock_gap_item_count) + '</td>' +
				'<td class="text-right ' + (row.material_shortage_item_count ? 'sosp-negative' : '') + '">' + format_qty(row.material_shortage_item_count) + '</td>' +
				'<td class="text-right"><strong>' + format_money(row.outstanding_value, currency) + '</strong></td>' +
			'</tr>';

			demand_lines.forEach(function(line) {
				if (line.sales_order !== row.sales_order) { return; }
				var line_search = demand_search(line);
				var packed_note = line.is_packed_item ? __("Bundle {0}", [line.sold_item_code]) : "";
				html += '<tr class="sosp-demand-row"' + tree_attributes(group, line_search) + '>' +
					'<td>' + status_pill(line.status, false) + '</td>' +
					'<td>' + tree_item_identity(line, 1, "sold", packed_note) + '</td>' +
					'<td>' + order_context_detail(line) + '</td>' +
					'<td>' + delivery_date_cell(line.delivery_date, line.days_to_delivery, line.is_overdue) + '</td>' +
					'<td class="text-right sosp-qty"><strong>' + format_qty(line.demand_qty) + '</strong><small>' + esc(line.stock_uom || "") + '</small></td>' +
					'<td class="text-right sosp-positive">' + format_qty(line.allocated_qty) + '</td>' +
					'<td class="text-right ' + gap_class(line) + '"><strong>' + format_qty(line.shortage_qty) + '</strong></td>' +
					'<td class="text-right ' + projected_class(line) + '">' + format_qty(line.total_projected_qty) + '</td>' +
					'<td></td>' +
				'</tr>';

				component_lines.forEach(function(material) {
					if (material.demand_line_id !== line.id) { return; }
					html += render_order_material_row(material, group);
				});
			});
			return html;
		}).join("") +
		'</tbody></table></div>';
};


SalesOrderStockProjection.prototype.render_items = function(items, shortages_only) {
	var self = this;
	var warehouses = this.data.warehouses || [];
	if (!items.length) {
		var empty_title = shortages_only ? __("No shortages") : __("No sold stock items");
		var empty_text = shortages_only ?
			__("Current stock covers the selected finished goods and their net BOM material demand.") :
			__("No stock items match the selected Sales Order demand.");
		return '<div class="sosp-all-clear"><span class="octicon octicon-check"></span><h4>' + esc(empty_title) + '</h4><p>' + esc(empty_text) + '</p></div>';
	}

	return '<div class="sosp-table-scroll"><table class="table sosp-table sosp-item-table">' +
		'<thead><tr>' +
			'<th class="sosp-item-column">' + esc(__("Sold item / BOM hierarchy")) + '</th>' +
			'<th class="text-right">' + esc(__("Net demand")) + '</th>' +
			'<th class="text-right">' + esc(__("From stock")) + '</th>' +
			'<th class="text-right">' + esc(__("Gap / build")) + '</th>' +
			'<th class="text-right">' + esc(__("ERP projected")) + '</th>' +
			'<th>' + esc(__("Next delivery")) + '</th>' +
			'<th>' + esc(__("Status")) + '</th>' +
			warehouse_headers(warehouses) +
		'</tr></thead><tbody>' +
		items.map(function(row) {
			var stock = (self.data.stock_by_item || {})[row.item_code] || {};
			var group = "item:" + row.item_code;
			var search = item_search(row);
			var material_display = self.get_material_display(row.item_code, shortages_only);
			var collapsed_note = shortages_only && material_display.collapsed ?
				__("{0} available BOM rows collapsed", [material_display.collapsed]) : "";
			var html = '<tr class="sosp-root-row"' + tree_attributes(group, search) + '>' +
				'<td class="sosp-item-column">' + tree_item_identity(row, 0, "sold", collapsed_note) + '</td>' +
				'<td class="text-right sosp-qty"><strong>' + format_qty(row.demand_qty) + '</strong><small>' + esc(row.stock_uom || "") + '</small></td>' +
				'<td class="text-right sosp-positive">' + format_qty(row.allocated_qty) + '</td>' +
				'<td class="text-right ' + gap_class(row) + '"><strong>' + format_qty(row.shortage_qty) + '</strong></td>' +
				'<td class="text-right ' + (row.total_projected_qty < 0 ? 'sosp-negative' : 'sosp-positive') + '">' + format_qty(row.total_projected_qty) + '</td>' +
				'<td>' + date_text(row.next_delivery_date) + '</td>' +
				'<td>' + status_pill(row.status, false) + '</td>' +
				warehouse_cells(warehouses, stock, self.metric) +
			'</tr>';

			material_display.rows.forEach(function(material) {
				var material_stock = (self.data.stock_by_item || {})[material.item_code] || {};
				html += '<tr class="sosp-hierarchy-row ' + (material.is_sub_assembly ? 'sosp-subassembly-row' : 'sosp-component-row') + '"' +
					tree_attributes(group, material_search(material)) + '>' +
					'<td class="sosp-item-column">' + tree_item_identity(material, material.display_level, material_type(material)) + '</td>' +
					'<td class="text-right sosp-qty"><strong>' + format_qty(material.demand_qty) + '</strong><small>' + esc(material.stock_uom || "") + '</small></td>' +
					'<td class="text-right sosp-positive">' + format_qty(material.allocated_qty) + '</td>' +
					'<td class="text-right ' + gap_class(material) + '"><strong>' + format_qty(material.shortage_qty) + '</strong></td>' +
					'<td class="text-right ' + projected_class(material) + '">' + format_qty(material.total_projected_qty) + '</td>' +
					'<td>' + date_text(material.next_delivery_date) + '</td>' +
					'<td>' + status_pill(material.status, false) + '</td>' +
					warehouse_cells(warehouses, material_stock, self.metric) +
				'</tr>';
			});
			return html;
		}).join("") +
		'</tbody></table></div>';
};


SalesOrderStockProjection.prototype.render_shortages_by_group = function(parts) {
	if (!parts.length) {
		return '<div class="sosp-all-clear"><span class="octicon octicon-check"></span><h4>' + esc(__("No material shortages")) + '</h4><p>' + esc(__("All net BOM material demand is covered by usable stock.")) + '</p></div>';
	}

	var grouped = {};
	parts.forEach(function(row) {
		var group_name = row.item_group || __("No Item Group");
		var group_key = "group:" + group_name;
		if (!grouped[group_key]) {
			grouped[group_key] = {
				name: group_name,
				parts: [],
				build_count: 0,
				blocking_count: 0
			};
		}
		grouped[group_key].parts.push(row);
		if (row.is_sub_assembly && row.status === "build_required") {
			grouped[group_key].build_count += 1;
		} else {
			grouped[group_key].blocking_count += 1;
		}
	});

	var status_order = { shortage: 0, partial: 1, build_required: 2, non_stock: 3 };
	var groups = Object.keys(grouped).map(function(key) { return grouped[key]; });
	groups.sort(function(a, b) { return a.name.localeCompare(b.name); });
	groups.forEach(function(group, group_index) {
		group.key = "shortage-group-" + group_index;
		group.parts.sort(function(a, b) {
			var a_order = status_order[a.status] === undefined ? 9 : status_order[a.status];
			var b_order = status_order[b.status] === undefined ? 9 : status_order[b.status];
			var status_difference = a_order - b_order;
			if (status_difference) { return status_difference; }
			var shortage_difference = Number(b.shortage_qty || 0) - Number(a.shortage_qty || 0);
			return shortage_difference || String(a.item_code).localeCompare(String(b.item_code));
		});
	});

	return '<div class="sosp-group-summary"><span class="octicon octicon-list-unordered"></span><strong>' +
		esc(__("{0} shortage parts across {1} item groups", [parts.length, groups.length])) +
		'</strong><small>' + esc(__("Each column represents one Item Group. Scrap warehouse quantities are excluded.")) + '</small></div>' +
		'<div class="sosp-group-table-scroll"><table class="sosp-group-table">' +
			'<thead><tr>' + groups.map(function(group) {
				return '<th data-group-key="' + group.key + '"><div><strong>' + esc(group.name) + '</strong>' +
					'<span>' + esc(__("{0} parts", [group.parts.length])) + '</span>' +
					'<small>' + esc(__("{0} need build · {1} blocking", [group.build_count, group.blocking_count])) + '</small></div></th>';
			}).join("") + '</tr></thead>' +
			'<tbody><tr>' + groups.map(function(group) {
				return '<td class="sosp-group-column" data-group-key="' + group.key + '" data-search="' + esc(group.name.toLowerCase()) + '">' +
					'<div class="sosp-group-parts">' + group.parts.map(render_group_shortage_part).join("") + '</div></td>';
			}).join("") + '</tr></tbody>' +
		'</table></div>' +
		'<div class="sosp-group-no-match" style="display:none"><span class="octicon octicon-search"></span> ' + esc(__("No shortage parts match this search.")) + '</div>';
};


SalesOrderStockProjection.prototype.render_allocation = function(lines) {
	var component_lines = this.data.component_lines || [];
	return '<div class="sosp-table-scroll"><table class="table sosp-table sosp-allocation-table">' +
		'<thead><tr>' +
			'<th class="text-right">#</th>' +
			'<th>' + esc(__("Delivery")) + '</th>' +
			'<th>' + esc(__("Sales Order / customer")) + '</th>' +
			'<th>' + esc(__("Demand item")) + '</th>' +
			'<th class="text-right">' + esc(__("Required")) + '</th>' +
			'<th class="text-right">' + esc(__("Allocated")) + '</th>' +
			'<th class="text-right">' + esc(__("Balance after")) + '</th>' +
			'<th>' + esc(__("Status")) + '</th>' +
		'</tr></thead><tbody>' +
		lines.map(function(row, index) {
			var group = "allocation:" + row.id;
			var search = demand_search(row);
			var packed_note = row.is_packed_item ? '<em class="sosp-packed-note">' + esc(__("Bundle {0}", [row.sold_item_code])) + '</em>' : '';
			var html = '<tr class="sosp-root-row"' + tree_attributes(group, search) + '>' +
				'<td class="text-right sosp-priority">' + (index + 1) + '</td>' +
				'<td>' + delivery_date_cell(row.delivery_date, row.days_to_delivery, row.is_overdue) + '</td>' +
				'<td><a href="#" class="sosp-order-link" data-sales-order="' + esc(row.sales_order) + '"><strong>' + esc(row.sales_order) + '</strong></a>' +
					'<small class="sosp-cell-note">' + esc(row.customer_name || row.customer) + '</small></td>' +
				'<td>' + tree_item_identity(row, 0, "sold") + packed_note + '</td>' +
				'<td class="text-right sosp-qty"><strong>' + format_qty(row.demand_qty) + '</strong><small>' + esc(row.stock_uom || "") + '</small></td>' +
				'<td class="text-right sosp-positive">' + format_qty(row.allocated_qty) + '</td>' +
				'<td class="text-right ' + (row.balance_after < 0 ? 'sosp-negative' : '') + '">' + format_qty(row.balance_after) + '</td>' +
				'<td>' + status_pill(row.status, false) + '</td>' +
			'</tr>';

			component_lines.forEach(function(material) {
				if (material.demand_line_id !== row.id) { return; }
				html += '<tr class="sosp-hierarchy-row ' + (material.is_sub_assembly ? 'sosp-subassembly-row' : 'sosp-component-row') + '"' +
					tree_attributes(group, material_search(material)) + '>' +
					'<td class="text-right sosp-tree-sequence">&#8627;</td>' +
					'<td>' + date_text(material.delivery_date) + '</td>' +
					'<td><small class="sosp-cell-note">' + esc(__("Parent: {0}", [material.parent_item_code || row.item_code])) + '</small></td>' +
					'<td>' + tree_item_identity(material, material.level, material_type(material)) + '</td>' +
					'<td class="text-right sosp-qty"><strong>' + format_qty(material.required_qty) + '</strong><small>' + esc(material.stock_uom || "") + '</small></td>' +
					'<td class="text-right sosp-positive">' + format_qty(material.allocated_qty) + '</td>' +
					'<td class="text-right ' + (material.balance_after < 0 ? gap_class(material) : '') + '">' + format_qty(material.balance_after) + '</td>' +
					'<td>' + status_pill(material.status, false) + '</td>' +
				'</tr>';
			});
			return html;
		}).join("") +
		'</tbody></table></div>';
};


SalesOrderStockProjection.prototype.aggregate_materials_for_item = function(item_code) {
	var rows = [];
	var by_path = {};
	(this.data.component_lines || []).forEach(function(line, index) {
		if (line.demand_item_code !== item_code) { return; }
		var path = (line.path || []).join("\u001f");
		var key = path + "\u001e" + (line.parent_bom || "") + "\u001e" + (line.bom_no || "");
		var row = by_path[key];
		if (!row) {
			row = $.extend({}, line, {
				demand_qty: 0,
				allocated_qty: 0,
				shortage_qty: 0,
				build_required_qty: 0,
				orders_map: {},
				first_index: index,
				next_delivery_date: line.delivery_date
			});
			by_path[key] = row;
			rows.push(row);
		}
		row.demand_qty += Number(line.required_qty || 0);
		row.allocated_qty += Number(line.allocated_qty || 0);
		row.shortage_qty += Number(line.shortage_qty || 0);
		row.build_required_qty += Number(line.build_required_qty || 0);
		row.orders_map[line.sales_order] = true;
		row.planning_issue = row.planning_issue || line.planning_issue;
		if (line.delivery_date && (!row.next_delivery_date || line.delivery_date < row.next_delivery_date)) {
			row.next_delivery_date = line.delivery_date;
		}
	});

	rows.forEach(function(row) {
		row.order_count = Object.keys(row.orders_map).length;
		if (!row.is_stock_item) {
			row.status = "non_stock";
		} else if (row.shortage_qty <= 0.000001) {
			row.status = "available";
		} else if (row.is_sub_assembly && !row.planning_issue) {
			row.status = "build_required";
		} else if (row.allocated_qty > 0) {
			row.status = "partial";
		} else {
			row.status = "shortage";
		}
	});
	return rows.sort(function(a, b) { return a.first_index - b.first_index; });
};


SalesOrderStockProjection.prototype.get_material_display = function(item_code, shortages_only) {
	var all_rows = this.aggregate_materials_for_item(item_code);
	if (!shortages_only) {
		all_rows.forEach(function(row) { row.display_level = row.level; });
		return { rows: all_rows, collapsed: 0 };
	}

	var rows = all_rows.filter(function(row) {
		return Number(row.shortage_qty || 0) > 0.000001 ||
			Number(row.build_required_qty || 0) > 0.000001;
	});
	var visible_depths = {};
	rows.forEach(function(row) {
		var path = row.path || [];
		var parent_depth = 0;
		for (var length = path.length - 1; length > 1; length--) {
			var parent_key = path.slice(0, length).join("\u001f");
			if (visible_depths[parent_key]) {
				parent_depth = visible_depths[parent_key];
				break;
			}
		}
		row.display_level = parent_depth + 1;
		visible_depths[path.join("\u001f")] = row.display_level;
	});
	return { rows: rows, collapsed: all_rows.length - rows.length };
};


SalesOrderStockProjection.prototype.update_active_tab = function() {
	var active = this.active_tab;
	this.$results.find(".sosp-tab").each(function() {
		var is_active = $(this).attr("data-tab") === active;
		$(this).toggleClass("active", is_active).attr("aria-selected", is_active ? "true" : "false");
	});
	this.$results.find(".sosp-panel").each(function() {
		$(this).toggle($(this).attr("data-panel") === active);
	});
	this.$results.find(".sosp-metric-select").toggle(
		active === "items" || active === "shortages"
	);
	this.apply_search();
};


SalesOrderStockProjection.prototype.apply_search = function() {
	var query = this.search_text;
	var $active_panel = this.$results.find('.sosp-panel[data-panel="' + this.active_tab + '"]');
	if (this.active_tab === "shortage_groups") {
		this.apply_group_search($active_panel, query);
		return;
	}
	var $rows = $active_panel.find("tbody tr");
	var matching_groups = {};
	$rows.each(function() {
		var $row = $(this);
		if (!query || String($row.attr("data-search") || "").indexOf(query) !== -1) {
			matching_groups[String($row.attr("data-tree-group") || "")] = true;
		}
	});
	$rows.each(function() {
		var group = String($(this).attr("data-tree-group") || "");
		$(this).toggle(!query || Boolean(matching_groups[group]));
	});
};


SalesOrderStockProjection.prototype.apply_group_search = function($panel, query) {
	var visible_groups = 0;
	$panel.find(".sosp-group-column").each(function() {
		var $column = $(this);
		var key = $column.attr("data-group-key");
		var group_matches = Boolean(query) && String($column.attr("data-search") || "").indexOf(query) !== -1;
		var visible_parts = 0;
		$column.find(".sosp-group-part").each(function() {
			var matches = !query || group_matches || String($(this).attr("data-search") || "").indexOf(query) !== -1;
			$(this).toggle(matches);
			if (matches) { visible_parts += 1; }
		});
		var show_group = !query || group_matches || visible_parts > 0;
		$column.toggle(show_group);
		$panel.find('.sosp-group-table th[data-group-key="' + key + '"]').toggle(show_group);
		if (show_group) { visible_groups += 1; }
	});
	$panel.find(".sosp-group-table-scroll").toggle(visible_groups > 0);
	$panel.find(".sosp-group-no-match").toggle(visible_groups === 0);
};


function render_order_material_row(row, group) {
	return '<tr class="sosp-hierarchy-row ' + (row.is_sub_assembly ? 'sosp-subassembly-row' : 'sosp-component-row') + '"' +
		tree_attributes(group, material_search(row)) + '>' +
		'<td>' + status_pill(row.status, false) + '</td>' +
		'<td>' + tree_item_identity(row, Number(row.level || 1) + 1, material_type(row)) + '</td>' +
		'<td>' + order_context_detail(row) + '</td>' +
		'<td>' + date_text(row.delivery_date) + '</td>' +
		'<td class="text-right sosp-qty"><strong>' + format_qty(row.required_qty) + '</strong><small>' + esc(row.stock_uom || "") + '</small></td>' +
		'<td class="text-right sosp-positive">' + format_qty(row.allocated_qty) + '</td>' +
		'<td class="text-right ' + gap_class(row) + '"><strong>' + format_qty(row.shortage_qty) + '</strong></td>' +
		'<td class="text-right ' + projected_class(row) + '">' + format_qty(row.total_projected_qty) + '</td>' +
		'<td></td>' +
	'</tr>';
}


function render_group_shortage_part(row) {
	var type = material_type(row);
	var search = [row.item_code, row.item_name, row.reference_code, row.item_group, row.status,
		type, (row.orders || []).join(" "), (row.sold_items || []).join(" ")].join(" ").toLowerCase();
	return '<article class="sosp-group-part ' + type + '" data-search="' + esc(search) + '">' +
		'<div class="sosp-group-part-head"><span class="sosp-avatar ' + type + '">' + esc(initials(row.item_name || row.item_code)) + '</span><div>' +
			'<a href="#" class="sosp-item-link" data-item-code="' + esc(row.item_code) + '">' + esc(row.item_code) + '</a>' +
			'<small>' + esc(row.item_name || row.item_code) + '</small>' +
			(row.reference_code ? '<em>' + esc(row.reference_code) + '</em>' : '') +
		'</div></div>' +
		'<div class="sosp-group-part-status">' + status_pill(row.status, false) + type_detail(row, type) + '</div>' +
		'<div class="sosp-group-part-metrics">' +
			'<span class="shortage"><small>' + esc(__("Short / build")) + '</small><strong>' + format_qty(row.shortage_qty) + ' ' + esc(row.stock_uom || "") + '</strong></span>' +
			'<span><small>' + esc(__("Net demand")) + '</small><strong>' + format_qty(row.demand_qty) + '</strong></span>' +
			'<span><small>' + esc(__("From stock")) + '</small><strong>' + format_qty(row.allocated_qty) + '</strong></span>' +
			'<span class="' + projected_class(row) + '"><small>' + esc(__("ERP projected")) + '</small><strong>' + format_qty(row.total_projected_qty) + '</strong></span>' +
		'</div>' +
		'<div class="sosp-group-part-foot"><span class="octicon octicon-file-directory"></span> ' +
			esc(__("{0} orders · {1} sold items", [row.order_count || 0, row.sold_item_count || 0])) + '</div>' +
	'</article>';
}


function tree_item_identity(row, level, type, extra_note) {
	level = clamp(level, 0, 12);
	var type_class = type === "assembly" ? "assembly" : (type === "component" ? "component" : "sold");
	var parent_class = level ? " has-parent" : "";
	return '<div class="sosp-item-identity sosp-tree-node' + parent_class + '" style="padding-left:' + (level * 20) + 'px">' +
		'<span class="sosp-avatar ' + type_class + '">' + esc(initials(row.item_name || row.item_code)) + '</span><span>' +
			'<a href="#" class="sosp-item-link" data-item-code="' + esc(row.item_code) + '">' + esc(row.item_code) + '</a>' +
			'<small>' + esc(row.item_name || row.item_code) + '</small>' +
			(row.reference_code ? '<em>' + esc(row.reference_code) + '</em>' : '') +
			(extra_note ? '<em>' + esc(extra_note) + '</em>' : '') +
			'<span class="sosp-tree-meta">' + type_detail(row, type_class) + '</span>' +
		'</span></div>';
}


function type_detail(row, type) {
	var labels = {
		sold: __("Sold item"),
		assembly: __("Sub-assembly"),
		component: __("Component")
	};
	return '<span class="sosp-type ' + type + '">' + esc(labels[type] || labels.component) + '</span>' +
		(row.bom_no ? '<a href="#" class="sosp-bom-link sosp-mini-link" data-bom-no="' + esc(row.bom_no) + '">' + esc(row.bom_no) + '</a>' : '');
}


function order_context_detail(row) {
	if (row.is_sub_assembly || row.parent_item_code) {
		return '<small class="sosp-cell-note">' + esc(__("Parent: {0}", [row.parent_item_code || row.demand_item_code])) + '</small>' +
			(row.parent_bom ? '<a href="#" class="sosp-bom-link sosp-mini-link" data-bom-no="' + esc(row.parent_bom) + '">' + esc(row.parent_bom) + '</a>' : '');
	}
	if (row.is_packed_item) {
		return '<small class="sosp-cell-note">' + esc(__("Product Bundle: {0}", [row.sold_item_code])) + '</small>';
	}
	return '<small class="sosp-cell-note">' + esc(__("Sales Order item")) + '</small>';
}


function material_type(row) {
	return row.is_sub_assembly ? "assembly" : "component";
}


function tree_attributes(group, search) {
	return ' data-tree-group="' + esc(group) + '" data-search="' + esc(search) + '"';
}


function item_search(row) {
	return [row.item_code, row.item_name, row.reference_code, row.item_group, row.status,
		(row.orders || []).join(" "), "sold item"].join(" ").toLowerCase();
}


function demand_search(row) {
	return [row.sales_order, row.customer, row.customer_name, row.item_code, row.item_name,
		row.reference_code, row.sold_item_code, row.sold_item_name, row.status, "sold item"].join(" ").toLowerCase();
}


function material_search(row) {
	return [row.sales_order, row.customer, row.customer_name, row.item_code, row.item_name,
		row.reference_code, row.item_group, row.sold_item_code, row.demand_item_code,
		row.parent_item_code, row.bom_no, row.parent_bom, row.status,
		row.is_sub_assembly ? "sub-assembly" : "component", (row.path || []).join(" ")].join(" ").toLowerCase();
}


function gap_class(row) {
	if (Number(row.shortage_qty || 0) <= 0) { return ""; }
	return row.is_sub_assembly || row.status === "build_required" ? "sosp-build-color" : "sosp-negative";
}


function projected_class(row) {
	return Number(row.total_projected_qty || 0) < 0 ? "sosp-negative" : "sosp-positive";
}


function warehouse_headers(warehouses) {
	if (!warehouses.length) {
		return '<th class="text-right">' + esc(__("No warehouse bins")) + '</th>';
	}
	return warehouses.map(function(warehouse) {
		return '<th class="sosp-warehouse-column text-right" title="' + esc(warehouse.name) + '">' +
			esc(warehouse.warehouse_name || warehouse.name) + '<small>' + esc(warehouse.section || "") + '</small></th>';
	}).join("");
}


function warehouse_cells(warehouses, stock, metric) {
	if (!warehouses.length) {
		return '<td class="text-right text-muted">—</td>';
	}
	return warehouses.map(function(warehouse) {
		var values = stock[warehouse.name] || {};
		var value = Number(values[metric] || 0);
		var klass = value < 0 ? "negative" : (value > 0 ? "positive" : "zero");
		var title = __("Actual: {0} · Reserved: {1} · Available: {2} · Projected: {3}", [
			format_qty(values.actual_qty || 0), format_qty(values.reserved_qty || 0),
			format_qty(values.available_qty || 0), format_qty(values.projected_qty || 0)
		]);
		return '<td class="sosp-stock-cell text-right ' + klass + '" title="' + esc(title) + '">' + format_qty(value) + '</td>';
	}).join("");
}


function status_pill(status, order_context) {
	var labels = order_context ? {
		available: __("Ready"), buildable: __("Buildable"), partial: __("At risk"), shortage: __("Blocked"), non_stock: __("Non-stock")
	} : {
		available: __("Available"), build_required: __("Needs build"), partial: __("Partial"), shortage: __("Shortage"), non_stock: __("Non-stock")
	};
	var icons = {
		available: "octicon-check", buildable: "octicon-tools", build_required: "octicon-tools",
		partial: "octicon-clock", shortage: "octicon-alert", non_stock: "octicon-dash"
	};
	status = status || "non_stock";
	return '<span class="sosp-status ' + esc(status) + '"><span class="octicon ' + icons[status] + '"></span> ' + esc(labels[status]) + '</span>';
}


function delivery_date_cell(value, days, overdue) {
	var label;
	if (overdue) {
		label = __("{0} days overdue", [Math.abs(Number(days || 0))]);
	} else if (Number(days) === 0) {
		label = __("Today");
	} else {
		label = __("in {0} days", [Number(days || 0)]);
	}
	return '<span class="sosp-delivery' + (overdue ? ' overdue' : '') + '"><strong>' + date_text(value) + '</strong><small>' + esc(label) + '</small></span>';
}


function tab(name, label, count) {
	return '<button type="button" class="sosp-tab" data-tab="' + name + '" role="tab" aria-selected="false">' +
		esc(label) + '<span>' + format_qty(count) + '</span></button>';
}


function metric_option(value, label, selected) {
	return '<option value="' + value + '"' + (value === selected ? ' selected' : '') + '>' + esc(label) + '</option>';
}


function kpi(icon, value, label, note, color, preformatted) {
	return '<div class="sosp-kpi ' + color + '"><span class="sosp-kpi-icon octicon ' + icon + '"></span><div>' +
		'<strong>' + (preformatted ? value : format_qty(value)) + '</strong><span>' + esc(label) + '</span><small>' + esc(note) + '</small></div></div>';
}


function format_qty(value) {
	var number = Number(value || 0);
	if (!isFinite(number)) { return "0"; }
	if (Math.abs(number) < 0.0000001) { number = 0; }
	return number.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 3 });
}


function format_money(value, currency) {
	return format_qty(Number(value || 0).toFixed(2)) + (currency ? ' <small class="sosp-currency">' + esc(currency) + '</small>' : '');
}


function date_text(value) {
	if (!value) { return "—"; }
	return esc(frappe.datetime.str_to_user(String(value)));
}


function format_datetime(value) {
	if (!value) { return ""; }
	return frappe.datetime.str_to_user(String(value).split(" ")[0]) + " " + String(value).split(" ").slice(1).join(" ").substring(0, 5);
}


function initials(value) {
	var parts = String(value || "").trim().split(/\s+/).filter(Boolean);
	if (!parts.length) { return "?"; }
	if (parts.length === 1) { return parts[0].substring(0, 2).toUpperCase(); }
	return (parts[0].charAt(0) + parts[parts.length - 1].charAt(0)).toUpperCase();
}


function clamp(value, minimum, maximum) {
	return Math.max(minimum, Math.min(maximum, Number(value || 0)));
}


function esc(value) {
	return frappe.utils.escape_html(String(value === undefined || value === null ? "" : value));
}

})();
