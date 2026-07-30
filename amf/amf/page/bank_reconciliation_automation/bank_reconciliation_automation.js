(function() {
"use strict";

frappe.pages["bank-reconciliation-automation"].on_page_load = function(wrapper) {
	wrapper.bank_reconciliation_automation = new BankReconciliationPage(wrapper);
};


function BankReconciliationPage(wrapper) {
	this.wrapper = wrapper;
	this.page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Bank Reconciliation Automation"),
		single_column: true
	});
	this.method = "amf.amf.page.bank_reconciliation_automation.bank_reconciliation_automation";
	this.file = null;
	this.content = null;
	this.analysis = null;
	this.setup_data = null;
	this.status_filter = "all";
	this.busy = false;
	this.make();
}


BankReconciliationPage.prototype.make = function() {
	var self = this;
	var default_company = frappe.defaults.get_user_default("Company");
	if (default_company !== "Advanced Microfluidics SA") {
		default_company = "Advanced Microfluidics SA";
	}

	this.fields = {
		company: this.page.add_field({
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			fieldname: "company",
			default: default_company,
			reqd: 1,
			change: function() {
				self.analysis = null;
				self.load_setup();
				self.render_results();
			}
		}),
		tolerance: this.page.add_field({
			label: __("Amount tolerance"),
			fieldtype: "Currency",
			fieldname: "tolerance",
			default: 0.05,
			description: __("Maximum difference accepted for a full invoice payment")
		})
	};

	this.page.set_primary_action(__("Analyze CSV"), function() {
		self.analyze();
	}, "octicon octicon-search");
	this.page.add_inner_button(__("Configure 3 bank accounts"), function() {
		self.configure_accounts();
	});

	this.$root = $(
		'<div class="bra-page">' +
			'<section class="bra-hero">' +
				'<div class="bra-hero-copy">' +
					'<div class="bra-eyebrow"><span class="octicon octicon-checklist"></span> ' +
						esc(__("PostFinance to ERPNext")) + '</div>' +
					'<h2>' + esc(__("Turn bank movements into auditable payments.")) + '</h2>' +
					'<p>' + esc(__("The importer finds SINV and PINV references, validates every accounting dimension, and only enables rows that are safe to post.")) + '</p>' +
				'</div>' +
				'<div class="bra-safety">' +
					'<span class="octicon octicon-shield"></span>' +
					'<div><strong>' + esc(__("Review first")) + '</strong>' +
					'<small>' + esc(__("Duplicate and partial-payment protection")) + '</small></div>' +
				'</div>' +
			'</section>' +
			'<section class="bra-panel bra-setup-panel">' +
				'<div class="bra-panel-heading">' +
					'<div><span class="bra-step">1</span><div><h3>' + esc(__("Bank account mapping")) + '</h3>' +
					'<p>' + esc(__("Each statement IBAN must resolve to one company Bank Account and one currency ledger.")) + '</p></div></div>' +
					'<button class="btn btn-default btn-sm bra-configure"><span class="octicon octicon-gear"></span> ' +
						esc(__("Configure accounts")) + '</button>' +
				'</div>' +
				'<div class="bra-account-grid"><div class="bra-loading">' + esc(__("Loading bank setup…")) + '</div></div>' +
			'</section>' +
			'<section class="bra-panel bra-upload-panel">' +
				'<div class="bra-panel-heading">' +
					'<div><span class="bra-step">2</span><div><h3>' + esc(__("Upload and validate")) + '</h3>' +
					'<p>' + esc(__("Use the original UTF-8, semicolon-separated PostFinance mouvements export.")) + '</p></div></div>' +
				'</div>' +
				'<div class="bra-dropzone" tabindex="0">' +
					'<input class="bra-file-input" type="file" accept=".csv,text/csv" hidden>' +
					'<span class="octicon octicon-cloud-upload bra-upload-icon"></span>' +
					'<strong>' + esc(__("Drop export_mouvements CSV here")) + '</strong>' +
					'<span>' + esc(__("or click to select a file · maximum 2 MB")) + '</span>' +
				'</div>' +
				'<div class="bra-file-row" style="display:none">' +
					'<div><span class="octicon octicon-file-text"></span><div><strong class="bra-file-name"></strong>' +
					'<small class="bra-file-meta"></small></div></div>' +
					'<button class="btn btn-primary btn-sm bra-analyze">' + esc(__("Analyze transactions")) + '</button>' +
				'</div>' +
			'</section>' +
			'<section class="bra-results"></section>' +
		'</div>'
	).appendTo(this.page.main);

	this.$accounts = this.$root.find(".bra-account-grid");
	this.$results = this.$root.find(".bra-results");
	this.bind();
	this.load_setup();
};


BankReconciliationPage.prototype.bind = function() {
	var self = this;
	var $dropzone = this.$root.find(".bra-dropzone");
	var $input = this.$root.find(".bra-file-input");

	$dropzone.on("click keydown", function(event) {
		if (event.type === "click" || event.keyCode === 13 || event.keyCode === 32) {
			event.preventDefault();
			$input.trigger("click");
		}
	});
	$input.on("change", function() {
		self.set_file(this.files && this.files[0]);
	});
	$dropzone.on("dragenter dragover", function(event) {
		event.preventDefault();
		event.stopPropagation();
		$dropzone.addClass("is-dragging");
	});
	$dropzone.on("dragleave drop", function(event) {
		event.preventDefault();
		event.stopPropagation();
		$dropzone.removeClass("is-dragging");
	});
	$dropzone.on("drop", function(event) {
		var files = event.originalEvent.dataTransfer.files;
		self.set_file(files && files[0]);
	});

	this.$root.on("click", ".bra-analyze", function() {
		self.analyze();
	});
	this.$root.on("click", ".bra-configure", function() {
		self.configure_accounts();
	});
	this.$root.on("click", ".bra-status-filter", function() {
		self.status_filter = $(this).attr("data-status");
		self.render_table();
	});
	this.$root.on("change", ".bra-select-all", function() {
		self.$results.find(".bra-row-select:not(:disabled)").prop("checked", this.checked);
		self.update_selection();
	});
	this.$root.on("change", ".bra-row-select", function() {
		self.update_selection();
	});
	this.$root.on("click", ".bra-create-drafts", function() {
		self.create_payments(false);
	});
	this.$root.on("click", ".bra-create-submit", function() {
		self.create_payments(true);
	});
	this.$root.on("click", ".bra-doc-link", function(event) {
		event.preventDefault();
		frappe.set_route("Form", $(this).attr("data-doctype"), $(this).attr("data-name"));
	});
};


BankReconciliationPage.prototype.set_file = function(file) {
	if (!file) {
		return;
	}
	if (file.size > 2 * 1024 * 1024) {
		frappe.msgprint(__("The CSV file must be 2 MB or smaller."));
		return;
	}
	if (!/\.csv$/i.test(file.name)) {
		frappe.msgprint(__("Please select a CSV file."));
		return;
	}
	this.file = file;
	this.content = null;
	this.analysis = null;
	this.$root.find(".bra-file-name").text(file.name);
	this.$root.find(".bra-file-meta").text(format_bytes(file.size));
	this.$root.find(".bra-file-row").css("display", "flex");
	this.$root.find(".bra-dropzone").addClass("has-file");
	this.render_results();
};


BankReconciliationPage.prototype.read_file = function(callback) {
	var self = this;
	if (this.content !== null) {
		callback(this.content);
		return;
	}
	if (!this.file) {
		frappe.msgprint(__("Select a PostFinance CSV file first."));
		return;
	}
	var reader = new FileReader();
	reader.onload = function(event) {
		self.content = event.target.result;
		callback(self.content);
	};
	reader.onerror = function() {
		frappe.msgprint(__("The selected file could not be read."));
	};
	reader.readAsText(this.file, "UTF-8");
};


BankReconciliationPage.prototype.load_setup = function() {
	var self = this;
	var company = this.fields.company.get_value();
	if (!company) {
		return;
	}
	this.$accounts.html('<div class="bra-loading">' + esc(__("Loading bank setup…")) + '</div>');
	frappe.call({
		method: this.method + ".get_setup",
		args: {company: company},
		callback: function(response) {
			if (!response.message) {
				return;
			}
			self.setup_data = response.message;
			self.fields.tolerance.set_value(response.message.default_tolerance || 0.05);
			self.render_accounts();
		},
		error: function() {
			self.$accounts.html('<div class="bra-empty">' + esc(__("Bank setup could not be loaded.")) + '</div>');
		}
	});
};


BankReconciliationPage.prototype.render_accounts = function() {
	var accounts = (this.setup_data && this.setup_data.accounts) || [];
	if (!accounts.length) {
		this.$accounts.html('<div class="bra-empty">' + esc(__("No supported bank accounts found.")) + '</div>');
		return;
	}
	this.$accounts.html(accounts.map(function(account) {
		var configured = account.status === "configured";
		var issues = (account.issues || []).map(function(issue) {
			return '<li>' + esc(issue) + '</li>';
		}).join("");
		return '<article class="bra-account-card ' + (configured ? "is-ready" : "is-missing") + '">' +
			'<div class="bra-account-top"><span class="bra-currency">' + esc(account.currency) + '</span>' +
			'<span class="bra-account-state"><span class="octicon ' +
				(configured ? "octicon-check" : "octicon-alert") + '"></span> ' +
				esc(configured ? __("Configured") : __("Setup required")) + '</span></div>' +
			'<div class="bra-iban">' + esc(account.iban) + '</div>' +
			'<dl><dt>' + esc(__("GL Account")) + '</dt><dd>' + esc(account.gl_account || "—") + '</dd>' +
			'<dt>' + esc(__("Bank Account")) + '</dt><dd>' + esc(account.bank_account || "—") + '</dd></dl>' +
			(issues ? '<ul class="bra-account-issues">' + issues + '</ul>' : '') +
		'</article>';
	}).join(""));
};


BankReconciliationPage.prototype.configure_accounts = function() {
	var self = this;
	if (this.busy) {
		return;
	}
	frappe.confirm(
		__("Create or repair the CHF, EUR and USD PostFinance company Bank Account mappings?"),
		function() {
			self.busy = true;
			frappe.call({
				method: self.method + ".setup_bank_accounts",
				args: {company: self.fields.company.get_value()},
				freeze: true,
				freeze_message: __("Configuring bank accounts…"),
				callback: function(response) {
					self.busy = false;
					if (response.message) {
						self.setup_data = response.message.setup;
						self.render_accounts();
						frappe.show_alert({message: response.message.message, indicator: "green"});
						if (self.file) {
							self.analyze();
						}
					}
				},
				error: function() {
					self.busy = false;
				}
			});
		}
	);
};


BankReconciliationPage.prototype.analyze = function() {
	var self = this;
	if (this.busy) {
		return;
	}
	var company = this.fields.company.get_value();
	if (!company) {
		frappe.msgprint(__("Select a company first."));
		return;
	}
	this.read_file(function(content) {
		self.busy = true;
		self.$results.html(
			'<div class="bra-analysis-loading"><span class="octicon octicon-sync"></span><strong>' +
			esc(__("Checking invoices, amounts, currencies and duplicates…")) + '</strong></div>'
		);
		frappe.call({
			method: self.method + ".analyze_csv",
			args: {
				content: content,
				company: company,
				tolerance: self.fields.tolerance.get_value() || 0
			},
			freeze: false,
			callback: function(response) {
				self.busy = false;
				if (!response.message) {
					return;
				}
				self.analysis = response.message;
				self.render_results();
			},
			error: function() {
				self.busy = false;
				self.$results.html('<div class="bra-empty">' + esc(__("The CSV analysis failed.")) + '</div>');
			}
		});
	});
};


BankReconciliationPage.prototype.render_results = function() {
	if (!this.analysis) {
		this.$results.html("");
		return;
	}
	var data = this.analysis;
	var summary = data.summary;
	var period = [data.metadata.from_date, data.metadata.to_date].filter(Boolean).join(" – ");
	var currency_lines = Object.keys(summary.amounts || {}).sort().map(function(currency) {
		var amount = summary.amounts[currency];
		return '<span><strong>' + esc(currency) + '</strong> ' +
			esc(__("net")) + ' ' + format_amount(amount.net, currency) + '</span>';
	}).join("");

	this.$results.html(
		'<section class="bra-panel bra-result-panel">' +
			'<div class="bra-panel-heading bra-result-heading">' +
				'<div><span class="bra-step">3</span><div><h3>' + esc(__("Reconciliation review")) + '</h3>' +
				'<p>' + esc(this.file ? this.file.name : "") +
				(period ? " · " + esc(period) : "") + '</p></div></div>' +
				'<div class="bra-net-lines">' + currency_lines + '</div>' +
			'</div>' +
			render_kpis(summary) +
			'<div class="bra-method-note"><span class="octicon octicon-info"></span><span>' +
				esc(__("Only green Ready rows can be created. New payments use the bank value date as Clearance Date; fees and non-invoice movements stay separate.")) +
			'</span></div>' +
			'<div class="bra-table-host"></div>' +
		'</section>'
	);
	this.render_table();
};


BankReconciliationPage.prototype.render_table = function() {
	if (!this.analysis) {
		return;
	}
	var self = this;
	var rows = this.analysis.rows.filter(function(row) {
		return self.status_filter === "all" || row.status === self.status_filter;
	});
	var filters = [
		["all", __("All"), this.analysis.summary.total],
		["ready", __("Ready"), this.analysis.summary.ready],
		["existing", __("Already processed"), this.analysis.summary.existing],
		["review", __("Review"), this.analysis.summary.review],
		["ignored", __("No reference"), this.analysis.summary.ignored]
	];
	var filter_html = filters.map(function(item) {
		return '<button class="bra-status-filter ' +
			(self.status_filter === item[0] ? "is-active" : "") +
			'" data-status="' + esc_attr(item[0]) + '">' +
			esc(item[1]) + '<span>' + item[2] + '</span></button>';
	}).join("");

	var row_html = rows.map(function(row) {
		var invoice_link = row.invoice ?
			doc_link(row.invoice_doctype, row.invoice) :
			'<span class="bra-muted">—</span>';
		var payment_link = row.existing_payment ?
			doc_link("Payment Entry", row.existing_payment) : "";
		var mode_source = [row.mode_of_payment_source, row.payment_terms_template].filter(Boolean).join(" · ");
		var messages = (row.messages || []).map(function(message) {
			return '<li>' + esc(message) + '</li>';
		}).join("");
		var detail = messages ?
			'<ul class="bra-row-messages">' + messages + '</ul>' :
			'<span class="bra-ok-text"><span class="octicon octicon-check"></span> ' +
				esc(__("All validations passed")) + '</span>';
		return '<tr class="bra-data-row status-' + esc_attr(row.status) + '">' +
			'<td class="bra-select-cell"><input class="bra-row-select" type="checkbox" data-row-key="' +
				esc_attr(row.row_key) + '" ' + (row.selectable ? "" : "disabled") + '></td>' +
			'<td><span class="bra-row-number">' + row.source_row + '</span></td>' +
			'<td>' + status_badge(row) + '</td>' +
			'<td><strong>' + esc(format_date_value(row.posting_date)) + '</strong>' +
				(row.value_date ? '<small>' + esc(__("Value date")) + ': ' +
					esc(format_date_value(row.value_date)) + '</small>' : '') +
				'<small>' + esc(row.iban || "") + '</small></td>' +
			'<td>' + invoice_link + '<small>' + esc(row.party_name || "") + '</small>' +
				(row.invoice_amount !== undefined ? '<small>' + esc(__("Invoice")) + ': ' +
					format_amount(row.invoice_amount, row.invoice_currency) + ' · ' +
					esc(__("Outstanding")) + ': ' +
					format_amount(Math.abs(row.outstanding_amount || 0), row.party_account_currency || row.invoice_currency) +
				'</small>' : '') + '</td>' +
			'<td class="text-right"><strong>' + format_amount(row.amount, row.currency) + '</strong>' +
				'<small>' + esc(row.direction === "credit" ? __("Credit") : row.direction === "debit" ? __("Debit") : "—") + '</small></td>' +
			'<td><span class="bra-reference">' + esc(row.check_reference || "—") + '</span>' +
				(payment_link ? '<small>' + esc(__("Payment")) + ': ' + payment_link + '</small>' : '') + '</td>' +
			'<td><span class="bra-ledger">' + esc(row.mode_of_payment || "—") + '</span>' +
				(mode_source ? '<small>' + esc(mode_source) + '</small>' : '') + '</td>' +
			'<td><span class="bra-ledger">' + esc(row.gl_account || "—") + '</span>' +
				'<small>' + esc(row.bank_account || "") + '</small></td>' +
		'</tr>' +
		'<tr class="bra-detail-row status-' + esc_attr(row.status) + '"><td></td><td colspan="8">' +
			'<div class="bra-row-detail">' + detail +
			'<details><summary>' + esc(__("Bank notification")) + '</summary><p>' +
				esc(row.notification || "") + '</p></details></div></td></tr>';
	}).join("");

	var eligible_visible = rows.some(function(row) { return row.selectable; });
	var html =
		'<div class="bra-toolbar">' +
			'<div class="bra-filters">' + filter_html + '</div>' +
			'<div class="bra-actions">' +
				'<span class="bra-selected-count">0 ' + esc(__("selected")) + '</span>' +
				'<button class="btn btn-default btn-sm bra-create-drafts" disabled>' + esc(__("Create drafts")) + '</button>' +
				'<button class="btn btn-primary btn-sm bra-create-submit" disabled>' + esc(__("Create & Submit")) + '</button>' +
			'</div>' +
		'</div>' +
		'<div class="bra-table-wrap"><table class="table bra-table"><thead><tr>' +
			'<th><input class="bra-select-all" type="checkbox" ' + (eligible_visible ? "" : "disabled") + '></th>' +
			'<th>' + esc(__("Row")) + '</th><th>' + esc(__("Status")) + '</th>' +
			'<th>' + esc(__("Bank date / IBAN")) + '</th><th>' + esc(__("Invoice / Party")) + '</th>' +
			'<th class="text-right">' + esc(__("Bank amount")) + '</th>' +
			'<th>' + esc(__("Check/Reference No")) + '</th><th>' + esc(__("Payment mode")) + '</th><th>' + esc(__("Bank ledger")) + '</th>' +
		'</tr></thead><tbody>' +
			(row_html || '<tr><td colspan="9"><div class="bra-empty">' + esc(__("No rows in this view.")) + '</div></td></tr>') +
		'</tbody></table></div>';
	this.$results.find(".bra-table-host").html(html);
	this.update_selection();
};


BankReconciliationPage.prototype.update_selection = function() {
	var selected = this.$results.find(".bra-row-select:checked").length;
	this.$results.find(".bra-selected-count").text(selected + " " + __("selected"));
	this.$results.find(".bra-create-drafts, .bra-create-submit").prop("disabled", !selected || this.busy);
	var eligible = this.$results.find(".bra-row-select:not(:disabled)").length;
	this.$results.find(".bra-select-all").prop(
		"checked",
		eligible > 0 && selected === eligible
	);
};


BankReconciliationPage.prototype.create_payments = function(submit) {
	var self = this;
	var selected = this.$results.find(".bra-row-select:checked").map(function() {
		return $(this).attr("data-row-key");
	}).get();
	if (!selected.length || this.busy) {
		return;
	}
	var prompt = submit ?
		__("Create and submit {0} Payment Entries? This will post General Ledger entries and update invoice outstanding balances.", [selected.length]) :
		__("Create {0} draft Payment Entries for review?", [selected.length]);
	frappe.confirm(prompt, function() {
		self.busy = true;
		self.update_selection();
		frappe.call({
			method: self.method + ".create_payment_entries",
			args: {
				content: self.content,
				selected_rows: JSON.stringify(selected),
				company: self.fields.company.get_value(),
				tolerance: self.fields.tolerance.get_value() || 0,
				submit: submit ? 1 : 0
			},
			freeze: true,
			freeze_message: submit ? __("Creating and submitting payments…") : __("Creating draft payments…"),
			callback: function(response) {
				self.busy = false;
				if (!response.message) {
					return;
				}
				self.show_creation_result(response.message);
				self.analyze();
			},
			error: function() {
				self.busy = false;
				self.update_selection();
			}
		});
	});
};


BankReconciliationPage.prototype.show_creation_result = function(data) {
	var rows = (data.results || []).map(function(row) {
		return '<tr><td>' + row.source_row + '</td><td>' + esc(row.invoice || "—") + '</td><td>' +
			(row.payment_entry ? doc_link("Payment Entry", row.payment_entry) : "—") +
			'</td><td>' + esc(row.message || row.status) + '</td></tr>';
	}).join("");
	frappe.msgprint({
		title: __("Payment Entry result"),
		indicator: data.errors ? "orange" : "green",
		message: '<p><strong>' + data.created + '</strong> ' + esc(__("created")) +
			' · <strong>' + data.submitted + '</strong> ' + esc(__("submitted")) +
			' · <strong>' + data.errors + '</strong> ' + esc(__("errors")) + '</p>' +
			'<div class="table-responsive"><table class="table table-bordered"><thead><tr><th>' +
			esc(__("Row")) + '</th><th>' + esc(__("Invoice")) + '</th><th>' +
			esc(__("Payment Entry")) + '</th><th>' + esc(__("Result")) +
			'</th></tr></thead><tbody>' + rows + '</tbody></table></div>'
	});
};


function render_kpis(summary) {
	var cards = [
		["octicon-list-unordered", summary.total, __("Bank rows"), "neutral"],
		["octicon-link", summary.matched, __("Invoice references"), "blue"],
		["octicon-check", summary.ready, __("Ready to create"), "green"],
		["octicon-history", summary.existing, __("Already processed"), "violet"],
		["octicon-alert", summary.review, __("Manual review"), "amber"],
		["octicon-dash", summary.ignored, __("No invoice reference"), "muted"]
	];
	return '<div class="bra-kpis">' + cards.map(function(card) {
		return '<article class="bra-kpi is-' + card[3] + '"><span class="bra-kpi-icon octicon ' +
			card[0] + '"></span><div><strong>' + card[1] + '</strong><span>' +
			esc(card[2]) + '</span></div></article>';
	}).join("") + '</div>';
}


function status_badge(row) {
	var icons = {
		ready: "octicon-check",
		existing: "octicon-history",
		review: "octicon-alert",
		ignored: "octicon-dash"
	};
	return '<span class="bra-status is-' + esc_attr(row.status) + '"><span class="octicon ' +
		(icons[row.status] || "octicon-info") + '"></span>' + esc(row.status_label) + '</span>';
}


function doc_link(doctype, name) {
	return '<a href="#" class="bra-doc-link" data-doctype="' + esc_attr(doctype) +
		'" data-name="' + esc_attr(name) + '">' + esc(name) + '</a>';
}


function format_amount(value, currency) {
	if (frappe.format && /^[A-Z]{3}$/.test(currency || "")) {
		return frappe.format(value || 0, {
			fieldtype: "Currency",
			options: currency
		});
	}
	return esc((currency || "") + " " + Number(value || 0).toFixed(2));
}


function format_date_value(value) {
	return value ? frappe.datetime.str_to_user(value) : "—";
}


function format_bytes(bytes) {
	if (bytes < 1024) {
		return bytes + " B";
	}
	return (bytes / 1024).toFixed(1) + " KB";
}


function esc(value) {
	return $("<div>").text(value === null || value === undefined ? "" : String(value)).html();
}


function esc_attr(value) {
	return esc(value).replace(/"/g, "&quot;");
}

})();
