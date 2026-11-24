(function () {
	"use strict";

	var api = "amf.amf.page.sales_analytics.sales_analytics.";
	var documentTypes = ["Sales Invoice", "Sales Order", "Delivery Note", "GL Entry", "Item", "Sales Analytics Billing"];
	var palette = ["#126b64", "#436f9f", "#a15b32", "#7d889a"];
	var chf = new Intl.NumberFormat("de-CH", {
		style: "currency", currency: "CHF", minimumFractionDigits: 2, maximumFractionDigits: 2
	});
	var number = new Intl.NumberFormat("de-CH", { maximumFractionDigits: 4 });

	frappe.pages["sales-analytics"].on_page_load = function (wrapper) {
		wrapper.sales_analytics = new SalesAnalytics(wrapper);
	};

	function el(tag, className, text) {
		var node = document.createElement(tag);
		if (className) node.className = className;
		if (text !== undefined && text !== null) node.textContent = text;
		return $(node);
	}

	function button(label, action, className) {
		return el("button", className || "btn btn-default btn-xs", label)
			.attr("type", "button").on("click", action);
	}

	function money(value) {
		return value === null || value === undefined ? "—" : chf.format(value);
	}

	function qty(value) {
		return value === null || value === undefined ? "—" : number.format(value);
	}

	function numericHeading(content) {
		return {content: content, numeric: true};
	}

	function listQty(units) {
		return Object.keys(units).map(function (unit) {
			return qty(units[unit]) + " " + unit;
		}).join(" · ") || "—";
	}

	function route(doctype, name, label) {
		if (!name || documentTypes.indexOf(doctype) === -1) return el("span", "", label || "—");
		return button(label || name, function () { frappe.set_route("Form", doctype, name); }, "sa-link");
	}

	function SalesAnalytics(wrapper) {
		this.page = frappe.ui.make_app_page({ parent: wrapper, title: __("Sales Analytics"), single_column: true });
		this.data = null;
		this.tab = "overview";
		this.refreshSequence = 0;
		this.detailSequence = 0;
		this.searchSequence = 0;
		this.create();
	}

	SalesAnalytics.prototype.create = function () {
		var self = this;
		var today = frappe.datetime.get_today();
		var fields = [
			{fieldname: "from_date", fieldtype: "Date", label: __("From"), default: today.slice(0, 4) + "-01-01"},
			{fieldname: "to_date", fieldtype: "Date", label: __("Through"), default: today},
			{fieldname: "period", fieldtype: "Select", label: __("Group by"), options: "month\nquarter\nyear", default: "month"},
			{fieldname: "customer", fieldtype: "Link", label: __("Customer"), options: "Customer"},
			{fieldname: "item_group", fieldtype: "Link", label: __("Item group"), options: "Item Group"},
			{fieldname: "territory", fieldtype: "Link", label: __("Territory"), options: "Territory"}
		];
		this.controls = {};
		fields.forEach(function (definition) {
			self.controls[definition.fieldname] = self.page.add_field(definition);
		});
		this.page.set_primary_action(__("Refresh"), function () { self.load(); }, "octicon octicon-sync");
		this.root = el("div", "sa").appendTo(this.page.main);
		this.meta = el("div", "sa-meta").attr("aria-live", "polite").appendTo(this.root);
		this.nav = el("nav", "sa-tabs").attr("aria-label", __("Sales analytics views")).appendTo(this.root);
		this.content = el("main", "sa-content").appendTo(this.root);
		this.detail = el("section", "sa-detail").attr("aria-label", __("Source transactions")).hide().appendTo(this.root);
		[
			["overview", __("Overview")], ["sales", __("Sales performance")],
			["orders", __("Orders and shipping")], ["item", __("Item detail")]
		].forEach(function (view) {
			button(view[1], function () {
				self.tab = view[0];
				self.closeDetails();
				self.render();
			}, "sa-tab").attr("data-tab", view[0]).appendTo(self.nav);
		});
		setTimeout(function () { self.load(); }, 0);
	};

	SalesAnalytics.prototype.selectedFilters = function () {
		var filters = {};
		var self = this;
		Object.keys(this.controls).forEach(function (key) { filters[key] = self.controls[key].get_value(); });
		filters.item_code = this.selectedItem || "";
		filters.order_status = this.orderStatus || "";
		filters.shipping_from = this.shippingFrom || "";
		filters.shipping_to = this.shippingTo || "";
		return filters;
	};

	SalesAnalytics.prototype.load = function () {
		var self = this;
		var sequence = ++this.refreshSequence;
		var filters = this.selectedFilters();
		this.meta.text(__("Refreshing sales data…"));
		frappe.call({
			method: api + "get_dashboard", args: { filters: filters },
			callback: function (response) {
				if (sequence !== self.refreshSequence || !response.message) return;
				self.data = response.message;
				self.filters = filters;
				self.closeDetails();
				self.render();
			},
			error: function () {
				if (sequence === self.refreshSequence) self.meta.text(__("Sales data could not be refreshed."));
			}
		});
	};

	SalesAnalytics.prototype.render = function () {
		var self = this;
		this.nav.find("button").each(function () {
			var current = $(this).attr("data-tab") === self.tab;
			$(this).toggleClass("active", current).attr("aria-current", current ? "page" : "false");
		});
		this.content.empty();
		if (this.tab === "item") this.renderItemSearch();
		if (!this.data) return;
		var data = this.data;
		this.meta.text([data.company, "CHF", __("Refreshed") + " " + data.refreshed_at].join(" · "));
		if (this.filters.item_code) {
			var item = el("div", "sa-filter", __("Item filter") + " · " + this.filters.item_code).appendTo(this.content);
			button(__("Clear"), function () { self.selectedItem = ""; self.load(); }).appendTo(item);
		}
		if (this.tab === "orders") this.renderOrders();
		if (this.tab === "sales") this.renderSales();
		if (this.tab === "item" && this.filters.item_code) this.renderItem();
		if (this.tab === "overview") this.renderOverview();
	};

	SalesAnalytics.prototype.panel = function (title) {
		var panel = el("section", "sa-panel").appendTo(this.content);
		el("h3", "", title).appendTo(panel);
		return panel;
	};

	SalesAnalytics.prototype.metric = function (key) {
		return this.data.metrics[key] || [key, "", ""];
	};

	SalesAnalytics.prototype.cardSet = function (panel, cards) {
		var self = this;
		var grid = el("div", "sa-card-grid").appendTo(panel);
		cards.forEach(function (card) {
			var definition = self.metric(card.metric);
			var cardButton = button("", function () {
				var dates = card.from_date && {from_date: card.from_date, to_date: card.to_date};
				self.showDetails(card.metric, { dates: dates });
			}, "sa-card").attr("title", __(definition[1])).appendTo(grid);
			el("span", "sa-card-label", __(card.label)).appendTo(cardButton);
			el("strong", "", money(card.value)).appendTo(cardButton);
			var change = card.change === null || card.change === undefined ? "" :
				" · " + (card.change > 0 ? "+" : "") + qty(card.change) + "% " + __("YoY");
			el("small", "", __(card.period) + change + " · " + __(definition[2])).appendTo(cardButton);
		});
	};

	SalesAnalytics.prototype.renderOverview = function () {
		var data = this.data;
		this.cardSet(this.panel(__("Sales and commitments")), data.cards);
		this.renderTrend();
		this.renderShipping();
		this.renderOutlook();
		this.renderActions();
	};

	SalesAnalytics.prototype.renderSales = function () {
		var self = this;
		if (this.data.charges) {
			var line = el("div", "sa-charges").appendTo(this.panel(__("Invoice breakdown")));
			Object.keys(this.data.charges).forEach(function (key) {
				button(__(self.metric(key)[0]) + " · " + money(self.data.charges[key]),
					function () { self.showDetails(key); }).appendTo(line);
			});
		}
		this.renderTrend();
		this.renderPortfolio(__("Customer contribution"), this.data.portfolio.customers, "customer", this.data.revenue_metric);
		this.renderPortfolio(__("Item performance"), this.data.portfolio.items, "item_code", "item_net");
		this.renderPortfolio(__("Item group contribution"), this.data.portfolio.item_groups, "item_group", "item_net");
		this.renderQuantityLeaders();
		this.renderActions();
	};

	SalesAnalytics.prototype.renderTrend = function () {
		var self = this;
		var trend = this.data.trends;
		var panel = this.panel(__("Sales trends"));
		if (this.data.selected_revenue !== null) {
			button(__(this.metric(this.data.revenue_metric)[0]) + " · " + money(this.data.selected_revenue), function () {
				self.showDetails(self.data.revenue_metric);
			}).appendTo(panel);
		}
		var categories = Object.keys(trend.series).map(function (key) {
			return {key: key, name: __(self.metric(key)[0]), values: trend.series[key]};
		});
		if (trend.prior_revenue) categories.push({key: "prior", name: __("Comparable prior year"), values: trend.prior_revenue});
		this.chart(panel, trend.labels, categories, "line");
		this.periodTable(panel, trend.labels, categories);
		if (trend.cumulative_revenue.length) {
			var cumulative = this.panel(__("Cumulative sales for selected period"));
			this.chart(cumulative, trend.labels, [{
				name: __(this.metric(this.data.revenue_metric)[0]), values: trend.cumulative_revenue
			}], "line");
		}
	};

	SalesAnalytics.prototype.chart = function (panel, labels, datasets, type) {
		if (!labels.length || !datasets.length || typeof frappe.Chart !== "function") return;
		var host = el("div", "sa-chart").appendTo(panel);
		new frappe.Chart(host[0], {
			type: type, height: 245, colors: palette, data: {
				labels: labels, datasets: datasets.map(function (dataset) {
					return {name: dataset.name, values: dataset.values.map(Number)};
				})
			},
			tooltipOptions: { formatTooltipY: money },
			lineOptions: { hideDots: labels.length > 18 ? 1 : 0 },
			axisOptions: { xIsSeries: true }
		});
	};

	SalesAnalytics.prototype.periodTable = function (panel, labels, categories) {
		var self = this;
		if (!categories.length) return;
		var table = this.table(panel, [__("Period")].concat(categories.map(function (row) {
			return numericHeading(row.name);
		})));
		labels.forEach(function (label, index) {
			var row = el("tr").appendTo(table);
			el("td", "", label).appendTo(row);
			categories.forEach(function (series) {
				var cell = el("td", "sa-number").appendTo(row);
				if (series.key === "prior") cell.text(money(series.values[index]));
				else button(money(series.values[index]), function () {
					self.showDetails(series.key, { period: label });
				}, "sa-link").appendTo(cell);
			});
		});
	};

	SalesAnalytics.prototype.renderOrders = function () {
		var self = this;
		var filtering = el("div", "sa-order-filter").appendTo(this.panel(__("Order filters")));
		function filter(label, control) {
			var field = el("label", "sa-inline-field", label).appendTo(filtering);
			control.appendTo(field);
		}
		var status = el("select", "form-control input-sm");
		["", "To Deliver and Bill", "To Bill", "To Deliver", "On Hold", "Closed", "Completed"].forEach(function (value) {
			el("option", "", value ? __(value) : __("All statuses")).val(value).appendTo(status);
		});
		status.val(this.orderStatus || "");
		filter(__("Order status"), status);
		var from = el("input", "form-control input-sm").attr("type", "date").val(this.shippingFrom || "");
		var to = el("input", "form-control input-sm").attr("type", "date").val(this.shippingTo || "");
		filter(__("Shipping from"), from);
		filter(__("Shipping through"), to);
		button(__("Apply order filters"), function () {
			self.orderStatus = status.val();
			self.shippingFrom = from.val();
			self.shippingTo = to.val();
			self.load();
		}).appendTo(filtering);
		this.cardSet(this.panel(__("Order intake and open commitments")), this.data.cards.filter(function (card) {
			return ["order_intake", "undelivered", "overdue", "unbilled", "delivered_unbilled"].indexOf(card.metric) !== -1;
		}));
		if (!this.data.billing_available) el("p", "sa-note", __("Complete unbilled balances require access to orders, deliveries and invoices.")).appendTo(this.content);
		var statistics = this.data.order_statistics;
		el("p", "sa-note", __("Selected-period bookings") + " · " + qty(statistics.orders) + " " +
			__("orders") + " · " + listQty(statistics.quantities)).appendTo(this.content);
		this.renderShipping();
		this.renderPortfolio(__("Open shipping commitments by item"), this.data.portfolio.open_items, "item_code", "undelivered");
		this.renderPortfolio(__("Open shipping commitments by customer"), this.data.portfolio.open_customers, "customer", "undelivered");
		this.renderPortfolio(__("Order intake by customer"), this.data.portfolio.intake_customers, "customer", "order_intake");
		this.renderActions();
	};

	SalesAnalytics.prototype.renderShipping = function () {
		var self = this;
		if (!this.data.readable["Sales Order"]) return;
		var rows = this.data.shipping_schedule;
		var panel = this.panel(__("Confirmed shipping schedule"));
		if (this.data.on_hold) {
			button(__("Shipping value on hold") + " · " + money(this.data.on_hold), function () {
				self.showDetails("held_shipping");
			}).appendTo(panel);
		}
		if (!rows.length) {
			el("p", "sa-note", __("No active shipping commitments in this scope.")).appendTo(panel);
			return;
		}
		this.chart(panel, rows.map(function (row) { return row.period; }), [{
			name: __("Undelivered commitments"), values: rows.map(function (row) { return row.value; })
		}], "bar");
		var table = this.table(panel, [
			__("Reporting period"), numericHeading(__("Orders")), __("Quantity"),
			numericHeading(__("Commitments")), numericHeading(__("Overdue in bucket"))
		]);
		rows.forEach(function (row) {
			var tr = el("tr").appendTo(table);
			button(row.period, function () { self.showDetails("undelivered", { period: row.period }); }, "sa-link").appendTo(el("td").appendTo(tr));
			el("td", "sa-number", qty(row.orders)).appendTo(tr);
			el("td", "", listQty(row.units)).appendTo(tr);
			el("td", "sa-number", money(row.value)).appendTo(tr);
			el("td", "sa-number", money(row.overdue)).appendTo(tr);
		});
	};

	SalesAnalytics.prototype.renderOutlook = function () {
		var self = this;
		var outlook = this.data.outlook;
		if (!outlook) return;
		var panel = this.panel(__("Confirmed invoicing outlook"));
		var values = el("div", "sa-charges").appendTo(panel);
		el("span", "", __("Actual YTD") + " · " + money(outlook.actual)).appendTo(values);
		if (this.data.billing_available) {
			button(__("Dated this year") + " · " + money(outlook.dated), function () { self.showDetails("dated_billing"); }).appendTo(values);
			button(__("Unscheduled for invoicing") + " · " + money(outlook.unscheduled), function () { self.showDetails("unscheduled_billing"); }).appendTo(values);
			el("span", "", __("Year-end outlook") + " · " + money(outlook.year_end)).appendTo(values);
		}
		if (!Object.keys(outlook.monthly).length) {
			if (this.data.billing_available) el("p", "sa-note", __("No approved future invoice dates in this scope.")).appendTo(panel);
		} else {
			var table = this.table(panel, [__("Expected invoice month"), numericHeading(__("Confirmed billing"))]);
			Object.keys(outlook.monthly).forEach(function (month) {
				var row = el("tr").appendTo(table);
				el("td", "", month).appendTo(row);
				button(money(outlook.monthly[month]), function () {
					self.showDetails("dated_billing", {period: month, dates: {period: "month"}});
				}, "sa-link").appendTo(el("td", "sa-number").appendTo(row));
			});
		}
		if (outlook.targets.length) {
			var target = this.table(panel, [__("Target period"), __("Metric")].concat([
				__("Target"), __("Actual"), __("Gap"), __("Attainment"), __("Variance"),
				__("Remaining"), __("Outlook"), __("Outlook gap")
			].map(numericHeading)));
			outlook.targets.forEach(function (entry) {
				var row = el("tr").appendTo(target);
				el("td", "", entry.from_date + " – " + entry.to_date).appendTo(row);
				el("td", "", __(self.metric(entry.metric)[0])).appendTo(row);
				["target", "actual", "gap", "attainment", "variance_pct", "remaining", "outlook", "outlook_gap"].forEach(function (key) {
					var percentage = key === "attainment" || key === "variance_pct";
					el("td", "sa-number", percentage ? qty(entry[key]) + "%" : money(entry[key])).appendTo(row);
				});
			});
		}
	};

	SalesAnalytics.prototype.renderItemSearch = function () {
		var self = this;
		var panel = this.panel(__("Find an item"));
		var input = el("input", "form-control").attr({
			type: "search", placeholder: __("Item code, name, reference or group"),
			"aria-label": __("Find an item")
		}).val(this.selectedItem || "").appendTo(panel);
		var results = el("ul", "sa-search-results").attr("aria-live", "polite").appendTo(panel);
		var timer;
		input.on("input", function () {
			clearTimeout(timer);
			var sequence = ++self.searchSequence;
			var text = input.val().trim();
			results.empty();
			if (text.length < 2) return;
			timer = setTimeout(function () {
				frappe.call({
					method: api + "search_items", args: {text: text},
					callback: function (response) {
						if (sequence !== self.searchSequence) return;
						var items = response.message || [];
						if (!items.length) el("li", "sa-note", __("No matching items.")).appendTo(results);
						items.forEach(function (item) {
							var label = [item.item_code, item.item_name, item.reference_code, item.item_group]
								.filter(Boolean).join(" · ");
							if (item.disabled) label += " · " + __("Disabled");
							button(label, function () {
								self.selectedItem = item.item_code;
								self.load();
							}, "sa-link").appendTo(el("li").appendTo(results));
						});
					}
				});
			}, 220);
		});
	};

	SalesAnalytics.prototype.renderItem = function () {
		var self = this;
		var item = this.data.item;
		if (item) {
			var panel = this.panel(this.filters.item_code);
			route("Item", this.filters.item_code, __("Open item record")).appendTo(panel);
			var info = el("div", "sa-charges").appendTo(panel);
			button(__("Net item sales") + " · " + money(item.net), function () { self.showDetails("item_net"); }).appendTo(info);
			el("span", "", __("Net quantity") + " · " + listQty(item.quantity)).appendTo(info);
			el("span", "", __("Average realized price") + " · " + money(item.average_price)).appendTo(info);
			el("span", "", __("Sales invoices") + " · " + qty(item.invoices)).appendTo(info);
			if (item.periods.length) {
				var history = this.table(panel, [
					__("Period"), __("Net quantity"), numericHeading(__("Net sales")), numericHeading(__("Invoices"))
				]);
				item.periods.forEach(function (entry) {
					var row = el("tr").appendTo(history);
					button(entry.period, function () { self.showDetails("item_net", {period: entry.period}); },
						"sa-link").appendTo(el("td").appendTo(row));
					el("td", "", listQty(entry.quantities)).appendTo(row);
					el("td", "sa-number", money(entry.value)).appendTo(row);
					el("td", "sa-number", qty(entry.invoices)).appendTo(row);
				});
			}
		}
		this.renderTrend();
		this.cardSet(this.panel(__("Item commitments")), this.data.cards.filter(function (card) {
			return ["undelivered", "overdue", "unbilled", "delivered_unbilled"].indexOf(card.metric) !== -1;
		}));
		this.renderShipping();
		this.renderOutlook();
		this.renderPortfolio(__("Customer distribution"), this.data.portfolio.customers, "customer", "item_net");
		this.renderActions();
	};

	SalesAnalytics.prototype.renderPortfolio = function (title, rows, group, metric) {
		var self = this;
		if (!rows.length) return;
		var comparative = rows.some(function (entry) { return entry.previous !== null; });
		var headers = [__("Name")].concat([__("CHF excl. VAT"), __("Share"), __("Documents")].map(numericHeading));
		if (comparative) headers = headers.concat([__("Prior CHF"), __("YoY")].map(numericHeading));
		var table = this.table(this.panel(title), headers);
		rows.forEach(function (entry) {
			var row = el("tr").appendTo(table);
			button(entry.label, function () {
				self.showDetails(metric, {group: group, value: entry.key});
			}, "sa-link").appendTo(el("td").appendTo(row));
			el("td", "sa-number", money(entry.value)).appendTo(row);
			el("td", "sa-number", entry.share === null ? "—" : qty(entry.share) + "%").appendTo(row);
			el("td", "sa-number", qty(entry.records)).appendTo(row);
			if (comparative) {
				el("td", "sa-number", money(entry.previous)).appendTo(row);
				el("td", "sa-number", entry.change === null ? "—" : qty(entry.change) + "%").appendTo(row);
			}
		});
	};

	SalesAnalytics.prototype.renderQuantityLeaders = function () {
		var self = this;
		var groups = this.data.portfolio.quantity_leaders;
		if (!Object.keys(groups).length) return;
		var panel = this.panel(__("Top items by quantity"));
		Object.keys(groups).forEach(function (unit) {
			el("h4", "sa-note", unit).appendTo(panel);
			var table = self.table(panel, [__("Item"), numericHeading(__("Net quantity")), numericHeading(__("Net sales"))]);
			groups[unit].forEach(function (entry) {
				var row = el("tr").appendTo(table);
				button(entry.label, function () { self.showDetails("item_net", {group: "item_code", value: entry.key}); },
					"sa-link").appendTo(el("td").appendTo(row));
				el("td", "sa-number", qty(entry.qty)).appendTo(row);
				el("td", "sa-number", money(entry.value)).appendTo(row);
			});
		});
	};

	SalesAnalytics.prototype.renderActions = function () {
		var self = this;
		var panel = el("div", "sa-actions").appendTo(this.content);
		var actions = [["exceptions", __("Data exceptions") + " · " + qty(this.data.exceptions)]];
		if (this.data.readable["Sales Order"]) {
			actions.push(["order_items", __("Order intake by item")]);
			actions.push(["order_changes", __("Order amendments and cancellations")]);
		}
		if (this.data.readable["Delivery Note"]) actions.push(["movements", __("Operational movements")]);
		if (this.data.reconciliation_available && !this.filters.item_code && !this.filters.item_group) actions.push(["reconciliation", __("Invoice reconciliation")]);
		actions.forEach(function (action) {
			button(action[1], function () { self.showDetails(action[0], {title: action[1]}); }).appendTo(panel);
		});
	};

	SalesAnalytics.prototype.table = function (parent, headers) {
		var scroller = el("div", "sa-scroll").appendTo(parent);
		var table = el("table", "sa-table").appendTo(scroller);
		var head = el("tr").appendTo(el("thead").appendTo(table));
		headers.forEach(function (heading) {
			var numeric = heading.numeric === true;
			var content = numeric ? heading.content : heading;
			var th = el("th", numeric ? "sa-number" : "").attr("scope", "col").appendTo(head);
			if (typeof content === "string") th.text(content);
			else th.append(content);
		});
		return el("tbody").appendTo(table);
	};

	SalesAnalytics.prototype.closeDetails = function () {
		this.detailSequence++;
		this.detail.empty().hide();
	};

	SalesAnalytics.prototype.showDetails = function (metric, options) {
		this.detailOptions = Object.assign({metric: metric, start: 0, limit: 25, direction: "desc"}, options || {});
		this.readDetails(true);
	};

	SalesAnalytics.prototype.detailArgs = function () {
		var selection = this.detailOptions;
		return {
			metric: selection.metric, filters: Object.assign({}, this.filters, selection.dates || {}),
			period: selection.period, group: selection.group, value: selection.value,
			sort: selection.sort, direction: selection.direction
		};
	};

	SalesAnalytics.prototype.readDetails = function (focus) {
		var self = this;
		var version = ++this.detailSequence;
		var selected = this.detailOptions;
		var definition = this.metric(selected.metric);
		this.detail.empty().show();
		var header = el("header", "sa-detail-header").appendTo(this.detail);
		el("h3", "", selected.title || __(definition[0])).attr("tabindex", "-1").appendTo(header);
		button(__("Close"), function () { self.closeDetails(); }).appendTo(header);
		if (definition[1]) el("p", "sa-note", __(definition[1])).appendTo(this.detail);
		var body = el("div", "sa-detail-body", __("Loading source transactions…")).appendTo(this.detail);
		if (focus) {
			header.find("h3")[0].focus();
			this.detail[0].scrollIntoView({block: "nearest", behavior: "smooth"});
		}
		frappe.call({
			method: api + "get_details",
			args: Object.assign(this.detailArgs(), {start: selected.start, limit: selected.limit}),
			callback: function (response) {
				if (version !== self.detailSequence || !response.message) return;
				self.renderDetailRows(body, response.message);
			},
			error: function () {
				if (version === self.detailSequence) body.text(__("Source transactions are unavailable in this scope."));
			}
		});
	};

	SalesAnalytics.prototype.renderDetailRows = function (body, data) {
		var self = this;
		var selected = this.detailOptions;
		body.empty();
		var tools = el("div", "sa-actions").appendTo(body);
		el("span", "sa-note", qty(data.total) + " " + __("records") + " · " + data.refreshed_at).appendTo(tools);
		["xlsx", "csv"].forEach(function (format) {
			button(format === "xlsx" ? __("Excel") : __("CSV"), function () {
				var args = self.detailArgs();
				args.filters = JSON.stringify(args.filters);
				args.file_format = format;
				Object.keys(args).forEach(function (key) { if (args[key] === undefined) delete args[key]; });
				open_url_post("/api/method/" + api + "export_details", args);
			}).appendTo(tools);
		});
		if (data.total === 0) {
			el("p", "sa-note", __("No matching records.")).appendTo(body);
			return;
		}
		var table = this.table(body, data.columns.map(function (column) {
			var arrow = selected.sort === column.key ? (selected.direction === "asc" ? " ↑" : " ↓") : "";
			var heading = button(__(column.label) + arrow, function () {
				selected.direction = selected.sort === column.key && selected.direction === "desc" ? "asc" : "desc";
				selected.sort = column.key;
				selected.start = 0;
				self.readDetails(false);
			}, "sa-sort");
			return column.kind === "text" ? heading : numericHeading(heading);
		}));
		data.rows.forEach(function (record) {
			var row = el("tr").appendTo(table);
			data.columns.forEach(function (column) {
				var value = record[column.key];
				var cell = el("td", column.kind === "text" ? "" : "sa-number").appendTo(row);
				if (column.key === "document") route(record.source, value).appendTo(cell);
				else if (column.key === "original_order") route("Sales Order", value).appendTo(cell);
				else if (column.key === "original_invoice") route("Sales Invoice", value).appendTo(cell);
				else if (column.key === "original_delivery") route("Delivery Note", value).appendTo(cell);
				else if (column.key === "item_code") route("Item", value).appendTo(cell);
				else if (column.key === "billing_plan") route("Sales Analytics Billing", value).appendTo(cell);
				else if (column.kind === "currency") cell.text(money(value));
				else if (column.kind === "number") cell.text(qty(value));
				else if (typeof value === "boolean") cell.text(value ? __("Yes") : __("No"));
				else cell.text(value || "—");
			});
		});
		var pages = el("div", "sa-pages").appendTo(body);
		button(__("Previous"), function () {
			selected.start = Math.max(0, selected.start - data.limit);
			self.readDetails(false);
		}).prop("disabled", !data.start).appendTo(pages);
		el("span", "", (data.start + 1) + "–" + Math.min(data.total, data.start + data.limit)).appendTo(pages);
		button(__("Next"), function () {
			selected.start += data.limit;
			self.readDetails(false);
		}).prop("disabled", data.start + data.limit >= data.total).appendTo(pages);
	};
}());
