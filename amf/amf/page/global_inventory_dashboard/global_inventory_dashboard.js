(function() {
"use strict";

frappe.pages["global-inventory-dashboard"].on_page_load = function(wrapper) {
	wrapper.global_inventory_dashboard = new GlobalInventoryDashboard(wrapper);
};


function GlobalInventoryDashboard(wrapper) {
	this.wrapper = wrapper;
	this.page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Global Inventory Dashboard"),
		single_column: true
	});
	this.method = "amf.amf.page.global_inventory_dashboard.global_inventory_dashboard";
	this.data = null;
	this.selected_item = null;
	this.suggestions = [];
	this.active_suggestion = -1;
	this.active_tab = "structure";
	this.metric = "available_qty";
	this.collapsed = {};
	this.search_timer = null;
	this.search_sequence = 0;

	this.make();
}


GlobalInventoryDashboard.prototype.make = function() {
	var self = this;

	this.page.set_primary_action(__("Explore inventory"), function() {
		self.resolve_and_load();
	}, "octicon octicon-search");

	this.page.add_inner_button(__("Refresh"), function() {
		if (self.selected_item) {
			self.load_dashboard();
		}
	});
	this.page.add_inner_button(__("Sales Order Projection"), function() {
		frappe.set_route("sales-order-stock-projection");
	});

	this.$dashboard = $(
		'<div class="global-inventory-dashboard">' +
			'<section class="gid-search-panel">' +
				'<div class="gid-search-copy">' +
					'<div class="gid-eyebrow">' + esc(__("SMART STOCK EXPLORER")) + '</div>' +
					'<h2>' + esc(__("See every part. Know what is available.")) + '</h2>' +
					'<p>' + esc(__("Find a product or component, then explore its complete BOM and live warehouse stock.")) + '</p>' +
				'</div>' +
				'<div class="gid-search-controls">' +
					'<div class="gid-search-field">' +
						'<label for="gid-item-search">' + esc(__("Item")) + '</label>' +
						'<div class="gid-input-wrap">' +
							'<span class="octicon octicon-search gid-input-icon"></span>' +
							'<input id="gid-item-search" class="form-control" type="text" autocomplete="off" ' +
								'placeholder="' + esc(__("Item code, name, reference, barcode…")) + '" ' +
								'role="combobox" aria-autocomplete="list" aria-expanded="false">' +
							'<span class="gid-search-spinner"><i class="fa fa-spinner fa-spin"></i></span>' +
						'</div>' +
						'<div class="gid-suggestions" role="listbox"></div>' +
					'</div>' +
					'<div class="gid-quantity-field">' +
						'<label for="gid-quantity">' + esc(__("Build quantity")) + '</label>' +
						'<input id="gid-quantity" class="form-control" type="number" min="0.001" step="any" value="1">' +
					'</div>' +
					'<button type="button" class="btn btn-primary gid-explore-button">' +
						'<span class="octicon octicon-search"></span> ' + esc(__("Explore")) +
					'</button>' +
				'</div>' +
				'<div class="gid-search-hint">' +
					esc(__("Searches item codes, names, groups, descriptions, references, barcodes and supplier/manufacturer part numbers.")) +
				'</div>' +
			'</section>' +
			'<div class="gid-results"></div>' +
		'</div>'
	).appendTo(this.page.main);

	this.$search = this.$dashboard.find("#gid-item-search");
	this.$quantity = this.$dashboard.find("#gid-quantity");
	this.$suggestions = this.$dashboard.find(".gid-suggestions");
	this.$spinner = this.$dashboard.find(".gid-search-spinner");
	this.$results = this.$dashboard.find(".gid-results");
	this.$explore = this.$dashboard.find(".gid-explore-button");

	this.bind_events();
	this.render_empty_state();
};


GlobalInventoryDashboard.prototype.bind_events = function() {
	var self = this;

	this.$search.on("input", function() {
		self.selected_item = null;
		self.queue_search($(this).val());
	});

	this.$search.on("keydown", function(event) {
		if (event.which === 40) {
			event.preventDefault();
			self.move_suggestion(1);
		} else if (event.which === 38) {
			event.preventDefault();
			self.move_suggestion(-1);
		} else if (event.which === 13) {
			event.preventDefault();
			if (self.active_suggestion >= 0 && self.suggestions[self.active_suggestion]) {
				self.select_suggestion(self.active_suggestion);
				self.load_dashboard();
			} else {
				self.resolve_and_load();
			}
		} else if (event.which === 27) {
			self.close_suggestions();
		}
	});

	this.$search.on("blur", function() {
		setTimeout(function() {
			self.close_suggestions();
		}, 180);
	});

	this.$search.on("focus", function() {
		if (self.suggestions.length) {
			self.$suggestions.show();
			self.$search.attr("aria-expanded", "true");
		}
	});

	this.$suggestions.on("mousedown", ".gid-suggestion", function(event) {
		event.preventDefault();
		self.select_suggestion(parseInt($(this).attr("data-index"), 10));
	});

	this.$explore.on("click", function() {
		self.resolve_and_load();
	});

	this.$quantity.on("keydown", function(event) {
		if (event.which === 13) {
			event.preventDefault();
			self.resolve_and_load();
		}
	});

	this.$results.on("click", ".gid-tab", function() {
		self.active_tab = $(this).attr("data-tab");
		self.update_active_tab();
	});

	this.$results.on("change", ".gid-metric-select", function() {
		self.metric = $(this).val();
		self.render_results();
	});

	this.$results.on("click", ".gid-tree-toggle", function() {
		var node_id = $(this).closest("tr").attr("data-node-id");
		self.collapsed[node_id] = !self.collapsed[node_id];
		self.update_tree_visibility();
	});

	this.$results.on("click", ".gid-expand-all", function() {
		self.collapsed = {};
		self.update_tree_visibility();
	});

	this.$results.on("click", ".gid-collapse-all", function() {
		(self.data.nodes || []).forEach(function(node) {
			if (node.has_children) {
				self.collapsed[node.id] = true;
			}
		});
		self.update_tree_visibility();
	});

	this.$results.on("click", ".gid-item-link", function(event) {
		event.preventDefault();
		frappe.set_route("Form", "Item", $(this).attr("data-item-code"));
	});

	this.$results.on("click", ".gid-bom-link", function(event) {
		event.preventDefault();
		frappe.set_route("Form", "BOM", $(this).attr("data-bom-no"));
	});
};


GlobalInventoryDashboard.prototype.queue_search = function(query) {
	var self = this;
	clearTimeout(this.search_timer);
	query = $.trim(query || "");

	if (query.length < 2) {
		this.suggestions = [];
		this.close_suggestions();
		this.$spinner.hide();
		return;
	}

	this.search_timer = setTimeout(function() {
		self.search_items(query);
	}, 260);
};


GlobalInventoryDashboard.prototype.search_items = function(query, callback) {
	var self = this;
	var sequence = ++this.search_sequence;
	this.$spinner.show();

	frappe.call({
		method: this.method + ".search_items",
		args: { query: query, limit: 12 },
		callback: function(response) {
			if (sequence !== self.search_sequence) {
				return;
			}
			self.$spinner.hide();
			self.suggestions = response.message || [];
			self.active_suggestion = self.suggestions.length ? 0 : -1;
			self.render_suggestions(query);
			if (callback) {
				callback(self.suggestions);
			}
		},
		error: function() {
			if (sequence === self.search_sequence) {
				self.$spinner.hide();
			}
		}
	});
};


GlobalInventoryDashboard.prototype.render_suggestions = function(query) {
	var self = this;
	if (!this.suggestions.length) {
		this.$suggestions.html(
			'<div class="gid-no-suggestions">' +
				esc(__("No active item found for “{0}”.", [query])) +
			'</div>'
		).show();
		this.$search.attr("aria-expanded", "true");
		return;
	}

	var html = this.suggestions.map(function(item, index) {
		var meta = [item.reference_code, item.item_group, item.stock_uom].filter(Boolean);
		return '<button type="button" class="gid-suggestion' + (index === self.active_suggestion ? ' active' : '') + '" ' +
			'data-index="' + index + '" role="option" aria-selected="' + (index === self.active_suggestion ? 'true' : 'false') + '">' +
			'<span class="gid-suggestion-mark">' + esc(initials(item.item_name || item.item_code)) + '</span>' +
			'<span class="gid-suggestion-body">' +
				'<span class="gid-suggestion-title">' + esc(item.item_code) + '</span>' +
				'<span class="gid-suggestion-name">' + esc(item.item_name || item.item_code) + '</span>' +
				(meta.length ? '<span class="gid-suggestion-meta">' + esc(meta.join(" · ")) + '</span>' : '') +
			'</span>' +
			(item.default_bom ? '<span class="gid-has-bom"><span class="octicon octicon-git-branch"></span> BOM</span>' : '') +
		'</button>';
	}).join("");

	this.$suggestions.html(html).show();
	this.$search.attr("aria-expanded", "true");
};


GlobalInventoryDashboard.prototype.move_suggestion = function(direction) {
	if (!this.suggestions.length) {
		return;
	}
	this.active_suggestion = (this.active_suggestion + direction + this.suggestions.length) % this.suggestions.length;
	this.render_suggestions(this.$search.val());
	var $active = this.$suggestions.find(".gid-suggestion.active");
	if ($active.length) {
		this.$suggestions.scrollTop($active.position().top + this.$suggestions.scrollTop() - 60);
	}
};


GlobalInventoryDashboard.prototype.select_suggestion = function(index) {
	var item = this.suggestions[index];
	if (!item) {
		return;
	}
	this.selected_item = item;
	this.$search.val(item.item_code);
	this.close_suggestions();
};


GlobalInventoryDashboard.prototype.close_suggestions = function() {
	this.$suggestions.hide();
	this.$search.attr("aria-expanded", "false");
};


GlobalInventoryDashboard.prototype.resolve_and_load = function() {
	var self = this;
	var query = $.trim(this.$search.val() || "");
	var quantity = parseFloat(this.$quantity.val());

	if (!query) {
		frappe.msgprint(__("Enter an item code, name or reference first."));
		this.$search.focus();
		return;
	}
	if (!quantity || quantity <= 0) {
		frappe.msgprint(__("Build quantity must be greater than zero."));
		this.$quantity.focus();
		return;
	}

	if (this.selected_item && this.selected_item.item_code === query) {
		this.load_dashboard();
		return;
	}

	this.search_items(query, function(items) {
		if (!items.length) {
			return;
		}
		var normalized = query.toLowerCase();
		var exact = items.filter(function(item) {
			return String(item.item_code || "").toLowerCase() === normalized ||
				String(item.reference_code || "").toLowerCase() === normalized ||
				String(item.item_name || "").toLowerCase() === normalized;
		})[0];
		self.selected_item = exact || items[0];
		self.$search.val(self.selected_item.item_code);
		self.close_suggestions();
		self.load_dashboard();
	});
};


GlobalInventoryDashboard.prototype.load_dashboard = function() {
	var self = this;
	var quantity = parseFloat(this.$quantity.val());
	if (!this.selected_item || !quantity || quantity <= 0) {
		return;
	}

	this.close_suggestions();
	this.set_loading(true);
	frappe.call({
		method: this.method + ".get_dashboard",
		args: {
			item_code: this.selected_item.item_code,
			quantity: quantity
		},
		callback: function(response) {
			self.set_loading(false);
			if (!response.message) {
				return;
			}
			self.data = response.message;
			self.active_tab = "structure";
			self.collapsed = {};
			(self.data.nodes || []).forEach(function(node) {
				if (node.has_children && node.level >= 2) {
					self.collapsed[node.id] = true;
				}
			});
			self.render_results();
		},
		error: function() {
			self.set_loading(false);
		}
	});
};


GlobalInventoryDashboard.prototype.set_loading = function(loading) {
	this.$explore.prop("disabled", loading);
	if (loading) {
		this.$explore.html('<i class="fa fa-spinner fa-spin"></i> ' + esc(__("Loading structure…")));
		this.$results.html(render_skeleton());
	} else {
		this.$explore.html('<span class="octicon octicon-search"></span> ' + esc(__("Explore")));
	}
};


GlobalInventoryDashboard.prototype.render_empty_state = function() {
	this.$results.html(
		'<div class="gid-empty-state">' +
			'<div class="gid-empty-visual">' +
				'<span class="gid-box gid-box-one"></span>' +
				'<span class="gid-box gid-box-two"></span>' +
				'<span class="gid-box gid-box-three"></span>' +
			'</div>' +
			'<h3>' + esc(__("Your inventory map starts here")) + '</h3>' +
			'<p>' + esc(__("Choose any item above to reveal its assemblies, components, shortages and stock by warehouse.")) + '</p>' +
		'</div>'
	);
};


GlobalInventoryDashboard.prototype.render_results = function() {
	if (!this.data) {
		this.render_empty_state();
		return;
	}

	var root = this.data.root_item || {};
	var summary = this.data.summary || {};
	var warnings = this.data.warnings || [];
	var metric_options = [
		{ value: "available_qty", label: __("Available (actual − reserved)") },
		{ value: "actual_qty", label: __("Actual stock") },
		{ value: "projected_qty", label: __("Projected stock") }
	];
	var self = this;

	var warning_html = warnings.length ?
		'<div class="gid-warning"><span class="octicon octicon-alert"></span><div>' +
			warnings.map(function(message) { return '<div>' + esc(message) + '</div>'; }).join("") +
		'</div></div>' : '';

	this.$results.html(
		'<section class="gid-root-card">' +
			'<div class="gid-root-icon">' + esc(initials(root.item_name || root.item_code)) + '</div>' +
			'<div class="gid-root-main">' +
				'<div class="gid-root-kicker">' + esc(root.item_group || __("Selected item")) + '</div>' +
				'<h3><a href="#" class="gid-item-link" data-item-code="' + esc(root.item_code) + '">' + esc(root.item_code) + '</a></h3>' +
				'<div class="gid-root-name">' + esc(root.item_name || root.item_code) + '</div>' +
				'<div class="gid-root-meta">' +
					(root.reference_code ? '<span><b>' + esc(__("Reference")) + ':</b> ' + esc(root.reference_code) + '</span>' : '') +
					(root.stock_uom ? '<span><b>' + esc(__("UOM")) + ':</b> ' + esc(root.stock_uom) + '</span>' : '') +
					(root.bom_no ? '<span><b>' + esc(__("BOM")) + ':</b> <a href="#" class="gid-bom-link" data-bom-no="' + esc(root.bom_no) + '">' + esc(root.bom_no) + '</a></span>' : '<span class="text-warning">' + esc(__("No active BOM")) + '</span>') +
				'</div>' +
			'</div>' +
			'<div class="gid-build-qty">' +
				'<span>' + esc(__("PLANNED QUANTITY")) + '</span>' +
				'<strong>' + format_qty(root.requested_qty) + ' ' + esc(root.stock_uom || "") + '</strong>' +
			'</div>' +
		'</section>' +
		warning_html +
		'<section class="gid-kpis">' +
			kpi_card("octicon-git-branch", summary.component_rows, __("BOM rows"), __("Recursive structure"), "blue") +
			kpi_card("octicon-package", summary.unique_components, __("Unique parts"), __("Consolidated demand"), "violet") +
			kpi_card("octicon-alert", summary.shortage_items, __("Shortages"), __("Using available stock"), summary.shortage_items ? "red" : "green") +
			kpi_card("octicon-home", summary.warehouse_count, __("Warehouses"), __("With matching bins"), "teal") +
			kpi_card("octicon-layers", summary.bom_levels, __("BOM levels"), __("Deepest branch"), "amber") +
		'</section>' +
		'<section class="gid-data-card">' +
			'<div class="gid-data-head">' +
				'<div class="gid-tabs" role="tablist">' +
					tab_button("structure", __("BOM Structure"), (this.data.nodes || []).length) +
					tab_button("consolidated", __("Consolidated"), (this.data.requirements || []).length) +
					tab_button("shortages", __("Shortages"), (this.data.shortages || []).length) +
				'</div>' +
				'<div class="gid-table-tools">' +
					'<button type="button" class="btn btn-default btn-xs gid-expand-all">' + esc(__("Expand all")) + '</button>' +
					'<button type="button" class="btn btn-default btn-xs gid-collapse-all">' + esc(__("Collapse all")) + '</button>' +
					'<label>' + esc(__("Warehouse values")) +
						'<select class="form-control input-sm gid-metric-select">' +
							metric_options.map(function(option) {
								return '<option value="' + option.value + '"' + (option.value === self.metric ? ' selected' : '') + '>' + esc(option.label) + '</option>';
							}).join("") +
						'</select>' +
					'</label>' +
				'</div>' +
			'</div>' +
			'<div class="gid-tab-panel" data-panel="structure">' + this.render_structure_table() + '</div>' +
			'<div class="gid-tab-panel" data-panel="consolidated">' + this.render_requirements_table(this.data.requirements || [], false) + '</div>' +
			'<div class="gid-tab-panel" data-panel="shortages">' + this.render_requirements_table(this.data.shortages || [], true) + '</div>' +
		'</section>' +
		'<div class="gid-stock-note"><span class="octicon octicon-info"></span> ' +
			esc(__("Available stock is actual stock minus reserved stock. Consolidated demand is gross BOM demand and does not consume on-hand sub-assemblies before evaluating their children.")) +
		'</div>'
	);

	this.update_active_tab();
	this.update_tree_visibility();
};


GlobalInventoryDashboard.prototype.render_structure_table = function() {
	var self = this;
	var warehouses = this.data.warehouses || [];
	var nodes = this.data.nodes || [];

	if (!nodes.length) {
		return empty_table_message(__("No BOM rows found."));
	}

	return '<div class="gid-table-scroll"><table class="table gid-inventory-table gid-structure-table">' +
		'<thead><tr>' +
			'<th class="gid-item-column">' + esc(__("Item / assembly")) + '</th>' +
			'<th>' + esc(__("Type")) + '</th>' +
			'<th>' + esc(__("BOM")) + '</th>' +
			'<th class="text-right">' + esc(__("Required")) + '</th>' +
			'<th class="text-right">' + esc(__("Total actual")) + '</th>' +
			'<th class="text-right">' + esc(__("Total available")) + '</th>' +
			'<th>' + esc(__("Status")) + '</th>' +
			warehouse_headers(warehouses) +
		'</tr></thead>' +
		'<tbody>' + nodes.map(function(node) {
			return self.structure_row(node, warehouses);
		}).join("") + '</tbody>' +
	'</table></div>';
};


GlobalInventoryDashboard.prototype.structure_row = function(node, warehouses) {
	var stock = (this.data.stock_by_item || {})[node.item_code] || {};
	var indent = Math.min(node.level, 12) * 22 + 10;
	var toggle = node.has_children ?
		'<button type="button" class="gid-tree-toggle" aria-label="' + esc(__("Expand or collapse")) + '"><span class="octicon octicon-chevron-down"></span></button>' :
		'<span class="gid-tree-spacer"></span>';
	var type = node.is_root ? "root" : (node.is_sub_assembly ? "assembly" : "component");
	var type_label = node.is_root ? __("Root") : (node.is_sub_assembly ? __("Sub-assembly") : __("Component"));
	var flags = "";
	if (node.cycle) {
		flags += '<span class="gid-row-flag warning" title="' + esc(__("Circular BOM stopped")) + '"><span class="octicon octicon-alert"></span></span>';
	}
	if (node.truncated) {
		flags += '<span class="gid-row-flag warning" title="' + esc(__("Branch was truncated")) + '">…</span>';
	}

	return '<tr data-node-id="' + esc(node.id) + '" data-parent-id="' + esc(node.parent_id || "") + '" data-level="' + node.level + '">' +
		'<td class="gid-item-column">' +
			'<div class="gid-tree-item" style="padding-left:' + indent + 'px">' + toggle +
				'<span class="gid-item-avatar ' + type + '">' + esc(initials(node.item_name || node.item_code)) + '</span>' +
				'<span class="gid-item-identity">' +
					'<a href="#" class="gid-item-link" data-item-code="' + esc(node.item_code) + '">' + esc(node.item_code) + '</a>' +
					'<span title="' + esc(node.description || node.item_name || "") + '">' + esc(node.item_name || node.item_code) + '</span>' +
					(node.reference_code ? '<small>' + esc(node.reference_code) + '</small>' : '') +
				'</span>' + flags +
			'</div>' +
		'</td>' +
		'<td><span class="gid-type-badge ' + type + '">' + esc(type_label) + '</span></td>' +
		'<td>' + (node.bom_no ? '<a href="#" class="gid-bom-link" data-bom-no="' + esc(node.bom_no) + '">' + esc(node.bom_no) + '</a>' : '<span class="text-muted">—</span>') + '</td>' +
		'<td class="text-right gid-qty"><strong>' + format_qty(node.required_qty) + '</strong><small>' + esc(node.stock_uom || "") + '</small></td>' +
		'<td class="text-right">' + format_qty(node.total_actual_qty) + '</td>' +
		'<td class="text-right">' + format_qty(node.total_available_qty) + '</td>' +
		'<td>' + status_pill(node.status) + '</td>' +
		warehouse_cells(warehouses, stock, this.metric) +
	'</tr>';
};


GlobalInventoryDashboard.prototype.render_requirements_table = function(rows, show_shortage) {
	var warehouses = this.data.warehouses || [];
	var self = this;

	if (!rows.length) {
		return show_shortage ?
			'<div class="gid-all-clear"><span class="octicon octicon-check"></span><h4>' + esc(__("No stock shortages")) + '</h4><p>' + esc(__("Available stock covers the consolidated BOM demand.")) + '</p></div>' :
			empty_table_message(__("No component requirements found."));
	}

	return '<div class="gid-table-scroll"><table class="table gid-inventory-table gid-requirements-table">' +
		'<thead><tr>' +
			'<th class="gid-item-column">' + esc(__("Item")) + '</th>' +
			'<th>' + esc(__("Type")) + '</th>' +
			'<th class="text-right">' + esc(__("Occurrences")) + '</th>' +
			'<th class="text-right">' + esc(__("Required")) + '</th>' +
			'<th class="text-right">' + esc(__("Available")) + '</th>' +
			(show_shortage ? '<th class="text-right">' + esc(__("Short by")) + '</th>' : '') +
			'<th>' + esc(__("Status")) + '</th>' +
			warehouse_headers(warehouses) +
		'</tr></thead><tbody>' +
		rows.map(function(row) {
			var stock = (self.data.stock_by_item || {})[row.item_code] || {};
			var type = row.is_sub_assembly ? "assembly" : "component";
			return '<tr>' +
				'<td class="gid-item-column"><div class="gid-flat-item">' +
					'<span class="gid-item-avatar ' + type + '">' + esc(initials(row.item_name || row.item_code)) + '</span>' +
					'<span class="gid-item-identity"><a href="#" class="gid-item-link" data-item-code="' + esc(row.item_code) + '">' + esc(row.item_code) + '</a>' +
					'<span>' + esc(row.item_name || row.item_code) + '</span>' +
					(row.reference_code ? '<small>' + esc(row.reference_code) + '</small>' : '') + '</span>' +
				'</div></td>' +
				'<td><span class="gid-type-badge ' + type + '">' + esc(row.is_sub_assembly ? __("Sub-assembly") : __("Component")) + '</span></td>' +
				'<td class="text-right">' + format_qty(row.occurrences) + '</td>' +
				'<td class="text-right gid-qty"><strong>' + format_qty(row.required_qty) + '</strong><small>' + esc(row.stock_uom || "") + '</small></td>' +
				'<td class="text-right">' + format_qty(row.total_available_qty) + '</td>' +
				(show_shortage ? '<td class="text-right gid-shortage-qty">' + format_qty(row.shortage_qty) + '</td>' : '') +
				'<td>' + status_pill(row.status) + '</td>' +
				warehouse_cells(warehouses, stock, self.metric) +
			'</tr>';
		}).join("") +
		'</tbody></table></div>';
};


GlobalInventoryDashboard.prototype.update_active_tab = function() {
	var active = this.active_tab;
	this.$results.find(".gid-tab").each(function() {
		var is_active = $(this).attr("data-tab") === active;
		$(this).toggleClass("active", is_active).attr("aria-selected", is_active ? "true" : "false");
	});
	this.$results.find(".gid-tab-panel").each(function() {
		$(this).toggle($(this).attr("data-panel") === active);
	});
	this.$results.find(".gid-expand-all, .gid-collapse-all").toggle(active === "structure");
};


GlobalInventoryDashboard.prototype.update_tree_visibility = function() {
	if (!this.data) {
		return;
	}
	var self = this;
	var node_map = {};
	(this.data.nodes || []).forEach(function(node) {
		node_map[node.id] = node;
	});

	this.$results.find(".gid-structure-table tbody tr").each(function() {
		var $row = $(this);
		var node = node_map[$row.attr("data-node-id")];
		var parent_id = node ? node.parent_id : null;
		var visible = true;
		while (parent_id) {
			if (self.collapsed[parent_id]) {
				visible = false;
				break;
			}
			parent_id = node_map[parent_id] ? node_map[parent_id].parent_id : null;
		}
		$row.toggle(visible);
		$row.find(".gid-tree-toggle span")
			.toggleClass("octicon-chevron-right", !!self.collapsed[$row.attr("data-node-id")])
			.toggleClass("octicon-chevron-down", !self.collapsed[$row.attr("data-node-id")]);
	});
};


function warehouse_headers(warehouses) {
	if (!warehouses.length) {
		return '<th class="gid-warehouse-column text-right">' + esc(__("No warehouse bins")) + '</th>';
	}
	return warehouses.map(function(warehouse) {
		var label = warehouse.warehouse_name || warehouse.name;
		return '<th class="gid-warehouse-column text-right" title="' + esc(warehouse.name + (warehouse.company ? " · " + warehouse.company : "")) + '">' +
			esc(label) + '<small>' + esc(warehouse.section || warehouse.company || "") + '</small></th>';
	}).join("");
}


function warehouse_cells(warehouses, stock, metric) {
	if (!warehouses.length) {
		return '<td class="text-right text-muted">—</td>';
	}
	return warehouses.map(function(warehouse) {
		var values = stock[warehouse.name] || {};
		var value = Number(values[metric] || 0);
		var cell_class = value < 0 ? "negative" : (value > 0 ? "positive" : "zero");
		var title = __("Actual: {0} · Reserved: {1} · Available: {2} · Projected: {3}", [
			format_qty(values.actual_qty || 0),
			format_qty(values.reserved_qty || 0),
			format_qty(values.available_qty || 0),
			format_qty(values.projected_qty || 0)
		]);
		return '<td class="gid-stock-cell text-right ' + cell_class + '" title="' + esc(title) + '">' + format_qty(value) + '</td>';
	}).join("");
}


function status_pill(status) {
	var labels = {
		available: __("Available"),
		partial: __("Partial"),
		shortage: __("Shortage"),
		non_stock: __("Non-stock")
	};
	var icons = {
		available: "octicon-check",
		partial: "octicon-clock",
		shortage: "octicon-alert",
		non_stock: "octicon-dash"
	};
	return '<span class="gid-status ' + esc(status || "non_stock") + '"><span class="octicon ' + icons[status || "non_stock"] + '"></span> ' +
		esc(labels[status] || labels.non_stock) + '</span>';
}


function tab_button(name, label, count) {
	return '<button type="button" class="gid-tab" data-tab="' + name + '" role="tab" aria-selected="false">' +
		esc(label) + '<span>' + format_qty(count || 0) + '</span></button>';
}


function kpi_card(icon, value, label, note, color) {
	return '<div class="gid-kpi ' + color + '">' +
		'<span class="gid-kpi-icon octicon ' + icon + '"></span>' +
		'<div><strong>' + format_qty(value || 0) + '</strong><span>' + esc(label) + '</span><small>' + esc(note) + '</small></div>' +
	'</div>';
}


function empty_table_message(message) {
	return '<div class="gid-table-empty"><span class="octicon octicon-package"></span> ' + esc(message) + '</div>';
}


function render_skeleton() {
	return '<div class="gid-skeleton">' +
		'<div class="gid-skeleton-card large"></div>' +
		'<div class="gid-skeleton-row">' +
			'<div class="gid-skeleton-card"></div><div class="gid-skeleton-card"></div><div class="gid-skeleton-card"></div><div class="gid-skeleton-card"></div>' +
		'</div>' +
		'<div class="gid-skeleton-card table"></div>' +
	'</div>';
}


function format_qty(value) {
	var number = Number(value || 0);
	if (!isFinite(number)) {
		return "0";
	}
	var rounded = Math.abs(number) < 0.0000001 ? 0 : number;
	return rounded.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 3 });
}


function initials(value) {
	var parts = String(value || "").trim().split(/\s+/).filter(Boolean);
	if (!parts.length) {
		return "?";
	}
	if (parts.length === 1) {
		return parts[0].substring(0, 2).toUpperCase();
	}
	return (parts[0].charAt(0) + parts[parts.length - 1].charAt(0)).toUpperCase();
}


function esc(value) {
	return frappe.utils.escape_html(String(value === undefined || value === null ? "" : value));
}

})();
