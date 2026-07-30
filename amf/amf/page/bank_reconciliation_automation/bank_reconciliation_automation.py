# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import csv
import hashlib
import io
import re
from collections import OrderedDict
from datetime import datetime

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, getdate
from six import string_types

from erpnext.accounts.doctype.payment_entry.payment_entry import (
	get_company_defaults,
	get_payment_entry,
)
from erpnext.accounts.utils import get_account_currency
from erpnext.setup.utils import get_exchange_rate


SUPPORTED_COMPANY = "Advanced Microfluidics SA"
BANK_NAME = "POSTFINANCE SA"
MAX_FILE_SIZE = 2 * 1024 * 1024
DEFAULT_TOLERANCE = 0.05
MAX_BATCH_SIZE = 200
REFERENCE_PATTERN = re.compile(
	r"\b((?:SINV|PINV)-\d+(?:-\d+)?)\b", re.IGNORECASE
)

BANK_DEFINITIONS = OrderedDict(
	[
		(
			"CHF",
			{
				"currency": "CHF",
				"iban": "CH9609000000155590589",
				"formatted_iban": "CH96 0900 0000 1555 9058 9",
				"gl_account_name": "Bank PostFinance CHF",
				"gl_account_number": "1020",
				"bank_account_name": "AMF SA ACCOUNT POSTFINANCE SA",
			},
		),
		(
			"EUR",
			{
				"currency": "EUR",
				"iban": "CH3709000000156601809",
				"formatted_iban": "CH37 0900 0000 1566 0180 9",
				"gl_account_name": "Bank PostFinance EUR",
				"gl_account_number": "1021",
				"bank_account_name": "AMF SA ACCOUNT POSTFINANCE EUR",
			},
		),
		(
			"USD",
			{
				"currency": "USD",
				"iban": "CH6909000000163516945",
				"formatted_iban": "CH69 0900 0000 1635 1694 5",
				"gl_account_name": "Bank PostFinance USD",
				"gl_account_number": "1022",
				"bank_account_name": "AMF SA ACCOUNT POSTFINANCE USD",
			},
		),
	]
)

REQUIRED_COLUMNS = (
	"Date",
	"Texte de notification",
	"Compte",
	"Crédit",
	"Débit",
	"Monnaie",
)


@frappe.whitelist()
def get_setup(company=None):
	"""Return the configured PostFinance IBAN-to-ledger mapping."""
	_assert_read_access()
	company = _resolve_company(company)
	return {
		"company": company,
		"bank": BANK_NAME,
		"accounts": _get_bank_setup_rows(company),
		"supported_file": "PostFinance mouvements CSV",
		"default_tolerance": DEFAULT_TOLERANCE,
	}


@frappe.whitelist()
def setup_bank_accounts(company=None):
	"""Idempotently create/link the CHF, EUR and USD company bank accounts."""
	_assert_setup_access()
	company = _resolve_company(company)

	if not frappe.db.exists("Bank", BANK_NAME):
		frappe.get_doc(
			{"doctype": "Bank", "bank_name": BANK_NAME}
		).insert()

	changes = []
	for definition in BANK_DEFINITIONS.values():
		gl_account, gl_created = _ensure_gl_account(company, definition)
		bank_account, bank_created, bank_updated = _ensure_bank_account(
			company, gl_account, definition
		)
		changes.append(
			{
				"currency": definition["currency"],
				"gl_account": gl_account,
				"bank_account": bank_account,
				"gl_created": gl_created,
				"bank_created": bank_created,
				"bank_updated": bank_updated,
			}
		)

	return {
		"message": _("The three PostFinance currency accounts are configured."),
		"changes": changes,
		"setup": get_setup(company),
	}


@frappe.whitelist()
def analyze_csv(content, company=None, tolerance=DEFAULT_TOLERANCE):
	"""Parse a PostFinance export and validate each transaction against ERPNext."""
	_assert_read_access()
	company = _resolve_company(company)
	tolerance = _normalize_tolerance(tolerance)
	transactions, metadata = _parse_csv(content)
	setup_by_iban = {
		_normalize_iban(row["iban"]): row
		for row in _get_bank_setup_rows(company)
	}

	rows = []
	for transaction in transactions:
		rows.append(
			_analyze_transaction(
				transaction, company, tolerance, setup_by_iban
			)
		)

	_mark_duplicates_inside_file(rows)
	return {
		"company": company,
		"metadata": metadata,
		"rows": rows,
		"summary": _build_summary(rows),
		"accounts": list(setup_by_iban.values()),
		"tolerance": tolerance,
		"methodology": {
			"references": _(
				"SINV references are matched to Sales Invoice; PINV references are matched to Purchase Invoice."
			),
			"amounts": _(
				"Only full invoice payments within the selected tolerance are eligible for automatic creation."
			),
			"currency": _(
				"The CSV currency, invoice currency, IBAN currency and bank ledger currency must agree."
			),
			"mode_of_payment": _(
				"Payment Entry Mode of Payment is taken from the invoice Payment Schedule or Payment Terms Template when available, then from the currency-specific Wire Transfer mode."
			),
			"duplicates": _(
				"Existing active Payment Entries are detected both by Check/Reference No and by invoice allocation."
			),
			"other_rows": _(
				"Bank fees and rows without an invoice reference remain visible but are never posted automatically."
			),
		},
	}


@frappe.whitelist()
def create_payment_entries(
	content,
	selected_rows,
	company=None,
	tolerance=DEFAULT_TOLERANCE,
	submit=0,
):
	"""Create draft or submitted Payment Entries for selected, revalidated rows."""
	_assert_create_access(cint(submit))
	company = _resolve_company(company)
	tolerance = _normalize_tolerance(tolerance)
	selected_rows = (
		frappe.parse_json(selected_rows)
		if isinstance(selected_rows, string_types)
		else selected_rows
	)
	if not isinstance(selected_rows, (list, tuple)):
		frappe.throw(_("Selected rows must be a list."))
	selected_rows = list(selected_rows or [])
	if any(
		not isinstance(row_key, string_types)
		or not re.match(r"^[a-f0-9]{64}$", row_key)
		for row_key in selected_rows
	):
		frappe.throw(_("The selected row identifiers are invalid."))
	if not selected_rows:
		frappe.throw(_("Select at least one eligible transaction."))
	if len(selected_rows) > MAX_BATCH_SIZE:
		frappe.throw(
			_("A maximum of {0} payments can be created at once.").format(
				MAX_BATCH_SIZE
			)
		)

	analysis = analyze_csv(content, company, tolerance)
	row_map = {row["row_key"]: row for row in analysis["rows"]}
	unknown = [key for key in selected_rows if key not in row_map]
	if unknown:
		frappe.throw(_("The selection no longer matches the uploaded file."))

	results = []
	for position, row_key in enumerate(selected_rows, 1):
		row = row_map[row_key]
		if row["status"] != "ready":
			results.append(
				{
					"row_key": row_key,
					"source_row": row["source_row"],
					"invoice": row.get("invoice"),
					"status": "skipped",
					"message": row.get("status_label"),
				}
			)
			continue

		savepoint = "bank_reconciliation_{0}".format(position)
		frappe.db.sql("savepoint {0}".format(savepoint))
		try:
			existing = _find_existing_payment(
				row["invoice_doctype"],
				row["invoice"],
				row["check_reference"],
			)
			if existing:
				results.append(
					{
						"row_key": row_key,
						"source_row": row["source_row"],
						"invoice": row["invoice"],
						"payment_entry": existing["name"],
						"status": "existing",
						"message": _("Payment Entry already exists."),
					}
				)
				continue

			payment_entry = _make_payment_entry(row, cint(submit))
			results.append(
				{
					"row_key": row_key,
					"source_row": row["source_row"],
					"invoice": row["invoice"],
					"payment_entry": payment_entry.name,
					"docstatus": payment_entry.docstatus,
					"status": "submitted" if payment_entry.docstatus == 1 else "draft",
					"message": _(
						"Submitted Payment Entry created."
						if payment_entry.docstatus == 1
						else "Draft Payment Entry created."
					),
				}
			)
		except Exception as error:
			frappe.db.sql("rollback to savepoint {0}".format(savepoint))
			frappe.log_error(
				frappe.get_traceback(),
				"Bank reconciliation row {0}".format(row["source_row"]),
			)
			results.append(
				{
					"row_key": row_key,
					"source_row": row["source_row"],
					"invoice": row.get("invoice"),
					"status": "error",
					"message": cstr(error),
				}
			)

	return {
		"results": results,
		"created": len(
			[row for row in results if row["status"] in ("draft", "submitted")]
		),
		"submitted": len(
			[row for row in results if row["status"] == "submitted"]
		),
		"errors": len([row for row in results if row["status"] == "error"]),
	}


def _parse_csv(content):
	if content is None:
		frappe.throw(_("Upload a CSV file first."))
	if isinstance(content, bytes):
		content = content.decode("utf-8-sig")
	content = cstr(content)
	if len(content.encode("utf-8")) > MAX_FILE_SIZE:
		frappe.throw(
			_("The CSV file exceeds the maximum supported size of 2 MB.")
		)

	reader = csv.reader(io.StringIO(content.lstrip("\ufeff")), delimiter=";")
	raw_rows = list(reader)
	header_index = None
	headers = None
	for index, row in enumerate(raw_rows):
		cleaned = [cstr(value).strip().lstrip("\ufeff") for value in row]
		if cleaned and cleaned[0] == "Date" and "Texte de notification" in cleaned:
			header_index = index
			headers = cleaned
			break

	if header_index is None:
		frappe.throw(
			_(
				"The PostFinance transaction header was not found. Expected a semicolon-separated export."
			)
		)
	missing = [column for column in REQUIRED_COLUMNS if column not in headers]
	if missing:
		frappe.throw(
			_("The CSV is missing required columns: {0}.").format(
				", ".join(missing)
			)
		)

	metadata = _parse_metadata(raw_rows[:header_index])
	transactions = []
	for source_row, raw_row in enumerate(
		raw_rows[header_index + 1 :], header_index + 2
	):
		if not raw_row or not any(cstr(value).strip() for value in raw_row):
			continue
		# PostFinance appends a two-line disclaimer after the transaction table.
		if len(raw_row) < len(headers):
			continue
		padded = list(raw_row) + [""] * max(0, len(headers) - len(raw_row))
		values = dict(zip(headers, padded[: len(headers)]))
		transactions.append(_parse_transaction(values, source_row))

	metadata["transaction_count"] = len(transactions)
	return transactions, metadata


def _parse_metadata(rows):
	metadata = {}
	label_map = {
		"Date de début:": "from_date",
		"Date de fin:": "to_date",
		"Genre de comptabilisation:": "booking_type",
		"Compte:": "account_scope",
	}
	for row in rows:
		if not row:
			continue
		label = cstr(row[0]).strip().lstrip("\ufeff")
		if label not in label_map:
			continue
		value = cstr(row[1] if len(row) > 1 else "").strip()
		value = re.sub(r'^="(.*)"$', r"\1", value)
		metadata[label_map[label]] = value
	return metadata


def _parse_transaction(values, source_row):
	notification = cstr(values.get("Texte de notification")).strip()
	references = []
	for match in REFERENCE_PATTERN.findall(notification):
		reference = cstr(match).upper()
		if reference not in references:
			references.append(reference)

	credit = _parse_amount(values.get("Crédit"))
	debit = _parse_amount(values.get("Débit"))
	signed_amount = credit if credit else debit
	direction = "credit" if credit else "debit" if debit else "unknown"
	date_value, date_error = _parse_date(values.get("Date"))
	raw_value_date = cstr(values.get("Valeur")).strip()
	value_date, value_date_error = (
		_parse_date(raw_value_date) if raw_value_date else (None, None)
	)
	currency = cstr(values.get("Monnaie")).strip().upper()
	iban = _normalize_iban(values.get("Compte"))
	transaction_hash = _transaction_hash(
		date_value or values.get("Date"),
		iban,
		currency,
		signed_amount,
		notification,
	)
	row_key = hashlib.sha256(
		"{0}|{1}".format(transaction_hash, source_row).encode("utf-8")
	).hexdigest()

	return {
		"source_row": source_row,
		"row_key": row_key,
		"transaction_hash": transaction_hash,
		"posting_date": cstr(date_value) if date_value else None,
		"date_error": date_error,
		"value_date": cstr(value_date) if value_date else None,
		"value_date_error": value_date_error,
		"notification": notification,
		"iban": iban,
		"account_holder": cstr(values.get("Dénomination du compte")).strip(),
		"credit": credit,
		"debit": debit,
		"signed_amount": signed_amount,
		"amount": abs(flt(signed_amount)),
		"direction": direction,
		"currency": currency,
		"references": references,
	}


def _analyze_transaction(transaction, company, tolerance, setup_by_iban):
	row = dict(transaction)
	row.update(
		{
			"status": "ignored",
			"status_label": _("No invoice reference"),
			"selectable": False,
			"messages": [],
			"invoice": None,
			"invoice_doctype": None,
			"check_reference": None,
			"existing_payment": None,
			"party": None,
			"party_name": None,
			"mode_of_payment": None,
			"mode_of_payment_source": None,
			"payment_terms_template": None,
			"payment_schedule_modes": [],
		}
	)

	if transaction["date_error"]:
		_add_issue(row, transaction["date_error"])
	if transaction["value_date_error"]:
		_add_issue(row, transaction["value_date_error"])
	if not transaction["amount"]:
		_add_issue(row, _("The transaction amount is zero or missing."))
	if transaction["direction"] == "unknown":
		_add_issue(row, _("Neither a credit nor a debit amount was found."))
	if transaction["credit"] and transaction["debit"]:
		_add_issue(row, _("Both Credit and Debit contain an amount."))
	if transaction["credit"] < 0:
		_add_issue(row, _("A credit amount cannot be negative."))
	if transaction["debit"] > 0:
		_add_issue(row, _("A debit amount must be negative."))
	if (
		transaction["account_holder"]
		and transaction["account_holder"] != company
	):
		_add_issue(
			row,
			_("Bank account holder is {0}, not {1}.").format(
				transaction["account_holder"], company
			),
		)
	if len(transaction["references"]) > 1:
		_add_issue(
			row,
			_("Multiple invoice references were found: {0}.").format(
				", ".join(transaction["references"])
			),
		)
	if not transaction["references"]:
		if row["messages"]:
			_set_review(row)
		return row

	invoice_name = transaction["references"][0]
	invoice_doctype = (
		"Sales Invoice" if invoice_name.startswith("SINV-") else "Purchase Invoice"
	)
	row["invoice"] = invoice_name
	row["invoice_doctype"] = invoice_doctype
	row["check_reference"] = _extract_check_reference(
		transaction["notification"], invoice_name
	)
	if not row["check_reference"]:
		_add_issue(row, _("A Check/Reference No could not be extracted."))
	elif len(row["check_reference"]) > 140:
		_add_issue(
			row,
			_("The extracted Check/Reference No exceeds 140 characters."),
		)

	setup = setup_by_iban.get(transaction["iban"])
	row["bank_account"] = setup.get("bank_account") if setup else None
	row["gl_account"] = setup.get("gl_account") if setup else None
	row["bank_setup_status"] = setup.get("status") if setup else "missing"
	if not setup:
		_add_issue(
			row,
			_("IBAN {0} is not part of the supported bank mapping.").format(
				transaction["iban"] or _("(blank)")
			),
		)
	else:
		if setup["currency"] != transaction["currency"]:
			_add_issue(
				row,
				_("IBAN currency is {0}, but the CSV row is {1}.").format(
					setup["currency"], transaction["currency"]
				),
			)
		if setup["status"] != "configured":
			_add_issue(
				row,
				_(
					"The {0} company Bank Account is not fully configured."
				).format(setup["currency"]),
			)

	if not frappe.db.exists(invoice_doctype, invoice_name):
		_add_issue(
			row,
			_("{0} {1} does not exist.").format(
				_(invoice_doctype), invoice_name
			),
		)
		_set_review(row)
		return row

	invoice = frappe.get_doc(invoice_doctype, invoice_name)
	party_field = "customer" if invoice_doctype == "Sales Invoice" else "supplier"
	party_doctype = "Customer" if invoice_doctype == "Sales Invoice" else "Supplier"
	party = invoice.get(party_field)
	row.update(
		{
			"invoice_docstatus": invoice.docstatus,
			"invoice_currency": invoice.currency,
			"invoice_posting_date": cstr(invoice.posting_date),
			"invoice_amount": abs(
				flt(invoice.get("rounded_total") or invoice.grand_total)
			),
			"outstanding_amount": flt(invoice.outstanding_amount),
			"company": invoice.company,
			"party": party,
			"party_name": frappe.db.get_value(
				party_doctype,
				party,
				"customer_name" if party_doctype == "Customer" else "supplier_name",
			)
			or party,
		}
	)
	row.update(
		_get_invoice_mode_of_payment(
			invoice, transaction["amount"], transaction["currency"], tolerance
		)
	)
	if row.get("mode_of_payment_error"):
		_add_issue(row, row["mode_of_payment_error"])

	existing = _find_existing_payment(
		invoice_doctype, invoice_name, row["check_reference"]
	)
	if existing:
		row["existing_payment"] = existing["name"]
		row["existing_payment_docstatus"] = existing["docstatus"]
		row["existing_clearance_date"] = cstr(
			existing.get("clearance_date")
		) or None
		row["status"] = "existing"
		row["status_label"] = _("Already processed")
		row["messages"].append(
			_("Active Payment Entry {0} already covers this transaction.").format(
				existing["name"]
			)
		)
		if not existing.get("clearance_date"):
			row["messages"].append(
				_("Its Clearance Date is not set in ERPNext.")
			)
		return row

	if invoice.docstatus != 1:
		_add_issue(
			row,
			_("{0} is not submitted (docstatus {1}).").format(
				invoice_name, invoice.docstatus
			),
		)
	if invoice.company != company:
		_add_issue(
			row,
			_("Invoice company is {0}, not {1}.").format(
				invoice.company, company
			),
		)

	is_positive_invoice = flt(invoice.grand_total) >= 0
	if invoice_doctype == "Sales Invoice":
		expected_direction = "credit" if is_positive_invoice else "debit"
	else:
		expected_direction = "debit" if is_positive_invoice else "credit"
	if transaction["direction"] != expected_direction:
		_add_issue(
			row,
			_("{0} requires a {1} bank row, but this row is {2}.").format(
				invoice_name, expected_direction, transaction["direction"]
			),
		)
	if invoice.currency != transaction["currency"]:
		_add_issue(
			row,
			_("Invoice currency is {0}, but bank currency is {1}.").format(
				invoice.currency, transaction["currency"]
			),
		)

	amount_delta = abs(row["invoice_amount"] - transaction["amount"])
	row["amount_delta"] = amount_delta
	row["amount_matches"] = amount_delta <= tolerance + 0.000001
	if not row["amount_matches"]:
		_add_issue(
			row,
			_(
				"Bank amount {0:.2f} differs from the full invoice amount {1:.2f} by {2:.2f} {3}."
			).format(
				transaction["amount"],
				row["invoice_amount"],
				amount_delta,
				transaction["currency"],
			),
		)

	if not flt(invoice.outstanding_amount):
		_add_issue(
			row,
			_(
				"The invoice has no outstanding balance and no active linked Payment Entry was found."
			),
		)
	else:
		_validate_full_outstanding(row, invoice, tolerance)

	if setup and setup.get("gl_account"):
		_validate_exchange_setup(row, invoice, company)

	if row["messages"]:
		_set_review(row)
	else:
		row["status"] = "ready"
		row["status_label"] = _("Ready")
		row["selectable"] = True
	return row


def _validate_full_outstanding(row, invoice, tolerance):
	party_account = (
		invoice.debit_to
		if row["invoice_doctype"] == "Sales Invoice"
		else invoice.credit_to
	)
	party_currency = get_account_currency(party_account)
	row["party_account"] = party_account
	row["party_account_currency"] = party_currency
	company_currency = frappe.db.get_value(
		"Company", invoice.company, "default_currency"
	)
	if party_currency == company_currency:
		expected_outstanding = abs(
			flt(
				invoice.get("base_rounded_total")
				or invoice.get("base_grand_total")
			)
		)
	else:
		expected_outstanding = abs(
			flt(invoice.get("rounded_total") or invoice.get("grand_total"))
		)
	outstanding_tolerance = max(tolerance, 0.05)

	row["expected_outstanding"] = expected_outstanding
	row["outstanding_delta"] = abs(
		abs(flt(invoice.outstanding_amount)) - expected_outstanding
	)
	if row["outstanding_delta"] > outstanding_tolerance + 0.000001:
		_add_issue(
			row,
			_(
				"The outstanding balance indicates a partial payment or a changed invoice; automatic full allocation is unsafe."
			),
		)


def _validate_exchange_setup(row, invoice, company):
	company_currency = frappe.db.get_value(
		"Company", company, "default_currency"
	)
	row["company_currency"] = company_currency
	if row["currency"] == company_currency:
		row["bank_exchange_rate"] = 1
		return
	try:
		exchange_rate = get_exchange_rate(
			row["currency"], company_currency, getdate(row["posting_date"])
		)
	except Exception as error:
		exchange_rate = None
		_add_issue(row, cstr(error))
	if not exchange_rate:
		_add_issue(
			row,
			_("No {0}/{1} exchange rate was found for {2}.").format(
				row["currency"], company_currency, row["posting_date"]
			),
		)
		return
	row["bank_exchange_rate"] = flt(exchange_rate)

	party_account = (
		invoice.debit_to
		if row["invoice_doctype"] == "Sales Invoice"
		else invoice.credit_to
	)
	if get_account_currency(party_account) != row["currency"]:
		defaults = frappe.get_cached_value(
			"Company",
			company,
			["exchange_gain_loss_account", "cost_center"],
			as_dict=True,
		)
		if not defaults.exchange_gain_loss_account or not defaults.cost_center:
			_add_issue(
				row,
				_(
					"Company exchange gain/loss account and cost center must be configured for this foreign-currency payment."
				),
			)


def _get_invoice_mode_of_payment(invoice, bank_amount, currency, tolerance):
	"""Choose the Payment Entry mode from the invoice payment terms."""
	schedule_modes = []
	for term in invoice.get("payment_schedule") or []:
		mode = cstr(term.get("mode_of_payment")).strip()
		if not mode:
			mode = _get_payment_term_mode(term.get("payment_term"))
		if not mode:
			continue
		schedule_modes.append(
			{
				"payment_term": cstr(term.get("payment_term")).strip(),
				"due_date": cstr(term.get("due_date")) or None,
				"payment_amount": abs(flt(term.get("payment_amount"))),
				"mode_of_payment": mode,
			}
		)

	selected, error = _select_mode_from_term_rows(
		schedule_modes, bank_amount, tolerance
	)
	if selected or error:
		return {
			"mode_of_payment": selected,
			"mode_of_payment_source": "Payment Schedule" if selected else None,
			"payment_terms_template": invoice.get("payment_terms_template"),
			"payment_schedule_modes": schedule_modes,
			"mode_of_payment_error": error,
		}

	template_modes = _get_template_mode_rows(invoice.get("payment_terms_template"))
	selected, error = _select_mode_from_term_rows(
		template_modes, bank_amount, tolerance
	)
	if selected or error:
		return {
			"mode_of_payment": selected,
			"mode_of_payment_source": (
				"Payment Terms Template" if selected else None
			),
			"payment_terms_template": invoice.get("payment_terms_template"),
			"payment_schedule_modes": template_modes,
			"mode_of_payment_error": error,
		}

	invoice_mode = cstr(invoice.get("mode_of_payment")).strip()
	if invoice_mode:
		return {
			"mode_of_payment": invoice_mode,
			"mode_of_payment_source": invoice.doctype,
			"payment_terms_template": invoice.get("payment_terms_template"),
			"payment_schedule_modes": [],
			"mode_of_payment_error": None,
		}

	wire_transfer_mode = _get_wire_transfer_mode(currency)
	if wire_transfer_mode:
		return {
			"mode_of_payment": wire_transfer_mode,
			"mode_of_payment_source": "Wire Transfer currency fallback",
			"payment_terms_template": invoice.get("payment_terms_template"),
			"payment_schedule_modes": [],
			"mode_of_payment_error": None,
		}

	return {
		"mode_of_payment": None,
		"mode_of_payment_source": None,
		"payment_terms_template": invoice.get("payment_terms_template"),
		"payment_schedule_modes": [],
		"mode_of_payment_error": None,
	}


def _select_mode_from_term_rows(rows, bank_amount, tolerance):
	modes = _unique(
		[row["mode_of_payment"] for row in rows if row.get("mode_of_payment")]
	)
	if not modes:
		return None, None
	if len(modes) == 1:
		return modes[0], None

	matching_amount_modes = _unique(
		[
			row["mode_of_payment"]
			for row in rows
			if row.get("mode_of_payment")
			and abs(flt(row.get("payment_amount")) - flt(bank_amount))
			<= tolerance + 0.000001
		]
	)
	if len(matching_amount_modes) == 1:
		return matching_amount_modes[0], None

	return None, _(
		"Payment terms contain multiple Modes of Payment ({0}); select the correct one manually."
	).format(", ".join(modes))


def _get_template_mode_rows(payment_terms_template):
	if not payment_terms_template:
		return []
	rows = frappe.get_all(
		"Payment Terms Template Detail",
		filters={"parent": payment_terms_template},
		fields=["payment_term", "mode_of_payment", "invoice_portion"],
		order_by="idx asc",
	)
	template_modes = []
	for row in rows:
		mode = cstr(row.get("mode_of_payment")).strip()
		if not mode:
			mode = _get_payment_term_mode(row.get("payment_term"))
		if not mode:
			continue
		template_modes.append(
			{
				"payment_term": cstr(row.get("payment_term")).strip(),
				"due_date": None,
				"payment_amount": None,
				"invoice_portion": flt(row.get("invoice_portion")),
				"mode_of_payment": mode,
			}
		)
	return template_modes


def _get_payment_term_mode(payment_term):
	if not payment_term:
		return None
	return cstr(
		frappe.db.get_value("Payment Term", payment_term, "mode_of_payment")
	).strip()


def _get_wire_transfer_mode(currency):
	mode = "Wire Transfer {0}".format(cstr(currency).strip().upper())
	return mode if frappe.db.exists("Mode of Payment", mode) else None


def _unique(values):
	unique_values = []
	for value in values:
		if value and value not in unique_values:
			unique_values.append(value)
	return unique_values


def _make_payment_entry(row, submit):
	payment_entry = get_payment_entry(
		row["invoice_doctype"],
		row["invoice"],
		bank_account=row["gl_account"],
		bank_amount=row["amount"],
	)
	payment_entry.posting_date = getdate(row["posting_date"])
	payment_entry.reference_date = getdate(row["posting_date"])
	clearance_date = getdate(row.get("value_date") or row["posting_date"])
	if clearance_date < payment_entry.reference_date:
		clearance_date = payment_entry.reference_date
	payment_entry.clearance_date = clearance_date
	payment_entry.reference_no = row["check_reference"]
	if row.get("mode_of_payment"):
		payment_entry.mode_of_payment = row["mode_of_payment"]
	payment_entry.remarks = _(
		"Imported from PostFinance bank statement row {0}."
	).format(row["source_row"])
	payment_entry.remarks += "\n" + row["notification"]

	# get_payment_entry starts with today's date. Recalculate historical FX rates
	# after applying the actual bank posting date.
	payment_entry.source_exchange_rate = 0
	payment_entry.target_exchange_rate = 0
	payment_entry.set_exchange_rate()
	payment_entry.set_amounts()
	if flt(payment_entry.difference_amount):
		defaults = get_company_defaults(payment_entry.company)
		payment_entry.set_gain_or_loss(
			{
				"account": defaults.exchange_gain_loss_account,
				"cost_center": defaults.cost_center,
			}
		)
		payment_entry.set_amounts()

	payment_entry.insert()
	if submit:
		payment_entry.submit()
	return payment_entry


def _get_bank_setup_rows(company):
	rows = []
	for definition in BANK_DEFINITIONS.values():
		gl_account = _find_gl_account(company, definition)
		bank_account = _find_bank_account_by_iban(
			company, definition["iban"]
		)
		issues = []
		if not gl_account:
			issues.append(_("GL account is missing"))
		else:
			gl_currency = frappe.db.get_value(
				"Account", gl_account, "account_currency"
			)
			account_type = frappe.db.get_value(
				"Account", gl_account, "account_type"
			)
			if gl_currency != definition["currency"]:
				issues.append(
					_("GL currency is {0}").format(gl_currency or _("blank"))
				)
			if account_type != "Bank":
				issues.append(_("GL account type is not Bank"))

		if not bank_account:
			issues.append(_("Bank Account master is missing"))
		else:
			bank_doc = frappe.get_doc("Bank Account", bank_account)
			if bank_doc.account != gl_account:
				issues.append(_("Bank Account is linked to another GL account"))
			if bank_doc.bank != BANK_NAME:
				issues.append(_("Bank master does not match PostFinance"))
			if not bank_doc.is_company_account or bank_doc.company != company:
				issues.append(_("Bank Account is not marked as a company account"))

		rows.append(
			{
				"currency": definition["currency"],
				"iban": definition["formatted_iban"],
				"normalized_iban": definition["iban"],
				"gl_account": gl_account,
				"bank_account": bank_account,
				"status": "configured" if not issues else "missing",
				"issues": issues,
			}
		)
	return rows


def _ensure_gl_account(company, definition):
	account = _find_gl_account(company, definition)
	if account:
		return account, False

	parent_account = _get_bank_parent_account(company)
	if not parent_account:
		frappe.throw(
			_(
				"No suitable bank parent account was found in the chart of accounts for {0}."
			).format(company)
		)
	doc = frappe.get_doc(
		{
			"doctype": "Account",
			"account_name": definition["gl_account_name"],
			"account_number": definition["gl_account_number"],
			"parent_account": parent_account,
			"company": company,
			"account_currency": definition["currency"],
			"account_type": "Bank",
			"is_group": 0,
		}
	)
	doc.insert()
	return doc.name, True


def _ensure_bank_account(company, gl_account, definition):
	name = _find_bank_account_by_iban(company, definition["iban"])
	created = False
	updated = False
	if name:
		doc = frappe.get_doc("Bank Account", name)
	else:
		doc = frappe.new_doc("Bank Account")
		doc.account_name = definition["bank_account_name"]
		doc.bank = BANK_NAME
		created = True

	values = {
		"account": gl_account,
		"bank": BANK_NAME,
		"bank_account_no": definition["formatted_iban"],
		"iban": definition["formatted_iban"],
		"is_company_account": 1,
		"company": company,
	}
	for fieldname, value in values.items():
		if doc.get(fieldname) != value:
			doc.set(fieldname, value)
			updated = True

	if doc.is_new():
		doc.insert()
	elif updated:
		doc.save()
	return doc.name, created, updated


def _find_gl_account(company, definition):
	return frappe.db.get_value(
		"Account",
		{
			"company": company,
			"account_name": definition["gl_account_name"],
			"is_group": 0,
			"disabled": 0,
		},
		"name",
	)


def _find_bank_account_by_iban(company, iban):
	normalized = _normalize_iban(iban)
	for row in frappe.get_all(
		"Bank Account",
		filters={"company": company},
		fields=["name", "iban", "bank_account_no"],
		limit_page_length=500,
	):
		if normalized in (
			_normalize_iban(row.iban),
			_normalize_iban(row.bank_account_no),
		):
			return row.name
	return None


def _get_bank_parent_account(company):
	default_bank = frappe.db.get_value(
		"Company", company, "default_bank_account"
	)
	if default_bank:
		parent = frappe.db.get_value("Account", default_bank, "parent_account")
		if parent:
			return parent

	for definition in BANK_DEFINITIONS.values():
		account = _find_gl_account(company, definition)
		if account:
			return frappe.db.get_value("Account", account, "parent_account")

	rows = frappe.db.sql(
		"""
		select name
		from `tabAccount`
		where company = %s
			and is_group = 1
			and root_type = 'Asset'
			and (
				lower(account_name) like '%%bank%%'
				or lower(account_name) like '%%cash%%'
			)
		order by lft desc
		limit 1
		""",
		company,
	)
	return rows[0][0] if rows else None


def _find_existing_payment(invoice_doctype, invoice_name, check_reference):
	rows = frappe.db.sql(
		"""
		select distinct pe.name, pe.docstatus, pe.posting_date,
			pe.reference_no, pe.clearance_date
		from `tabPayment Entry` pe
		left join `tabPayment Entry Reference` per
			on per.parent = pe.name
		where pe.docstatus < 2
			and (
				pe.reference_no = %(check_reference)s
				or (
					per.reference_doctype = %(invoice_doctype)s
					and per.reference_name = %(invoice_name)s
				)
			)
		order by pe.docstatus desc, pe.creation desc
		limit 1
		""",
		{
			"check_reference": check_reference,
			"invoice_doctype": invoice_doctype,
			"invoice_name": invoice_name,
		},
		as_dict=True,
	)
	return rows[0] if rows else None


def _extract_check_reference(notification, invoice_name):
	"""Mirror the reference format already used on AMF Payment Entries."""
	match = re.search(re.escape(invoice_name), notification, re.IGNORECASE)
	if not match:
		return None
	tail = notification[match.end() :]
	references_marker = re.search(r"\bREFERENCES?\s*:\s*", tail, re.IGNORECASE)
	if references_marker:
		tail = tail[references_marker.end() :]

	tail = re.sub(
		r"\b{0}\b".format(re.escape(invoice_name)),
		" ",
		tail,
		flags=re.IGNORECASE,
	)
	tail = re.sub(r"\bNOTPROVIDED\b", " ", tail, flags=re.IGNORECASE)
	tail = re.sub(r"\s+", " ", tail).strip(" \t\r\n,;/")

	# PINV rows place the bank transaction number immediately after the invoice.
	# SINV rows use the REFERENCES segment and may contain several useful tokens.
	if not references_marker:
		token_match = re.search(r"\b[A-Z0-9][A-Z0-9./-]{5,}\b", tail, re.IGNORECASE)
		tail = token_match.group(0) if token_match else ""

	return "{0} {1}".format(invoice_name, tail).strip() if tail else None


def _mark_duplicates_inside_file(rows):
	by_hash = {}
	for row in rows:
		by_hash.setdefault(row["transaction_hash"], []).append(row)
	for duplicate_rows in by_hash.values():
		if len(duplicate_rows) < 2:
			continue
		source_rows = ", ".join(
			cstr(row["source_row"]) for row in duplicate_rows
		)
		for row in duplicate_rows:
			if row["status"] == "ready":
				_add_issue(
					row,
					_("The same transaction appears on CSV rows {0}.").format(
						source_rows
					),
				)
				_set_review(row)


def _build_summary(rows):
	summary = {
		"total": len(rows),
		"matched": len([row for row in rows if row.get("invoice")]),
		"ready": len([row for row in rows if row["status"] == "ready"]),
		"existing": len(
			[row for row in rows if row["status"] == "existing"]
		),
		"review": len([row for row in rows if row["status"] == "review"]),
		"ignored": len([row for row in rows if row["status"] == "ignored"]),
		"amounts": {},
	}
	for row in rows:
		currency = row.get("currency") or _("Unknown")
		if currency not in summary["amounts"]:
			summary["amounts"][currency] = {
				"credits": 0,
				"debits": 0,
				"net": 0,
			}
		summary["amounts"][currency]["credits"] += flt(row.get("credit"))
		summary["amounts"][currency]["debits"] += flt(row.get("debit"))
		summary["amounts"][currency]["net"] += flt(row.get("signed_amount"))
	for currency_totals in summary["amounts"].values():
		for fieldname in ("credits", "debits", "net"):
			currency_totals[fieldname] = flt(
				currency_totals[fieldname], 2
			)
	return summary


def _parse_amount(value):
	text = cstr(value).strip().replace("'", "").replace(" ", "")
	if not text:
		return 0
	if "," in text and "." not in text:
		text = text.replace(",", ".")
	try:
		return flt(text)
	except (TypeError, ValueError):
		return 0


def _parse_date(value):
	text = cstr(value).strip()
	for date_format in ("%d.%m.%Y", "%Y-%m-%d"):
		try:
			return datetime.strptime(text, date_format).date(), None
		except ValueError:
			pass
	return None, _("Invalid bank date: {0}.").format(text or _("blank"))


def _transaction_hash(date_value, iban, currency, amount, notification):
	value = "|".join(
		[
			cstr(date_value),
			cstr(iban),
			cstr(currency),
			"{0:.9f}".format(flt(amount)),
			re.sub(r"\s+", " ", cstr(notification)).strip(),
		]
	)
	return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_iban(value):
	return re.sub(r"[^A-Z0-9]", "", cstr(value).upper())


def _normalize_tolerance(value):
	tolerance = flt(value)
	if tolerance < 0 or tolerance > 10:
		frappe.throw(_("Amount tolerance must be between 0 and 10."))
	return tolerance


def _resolve_company(company):
	company = (
		cstr(company).strip()
		or frappe.defaults.get_user_default("Company")
		or SUPPORTED_COMPANY
	)
	if company != SUPPORTED_COMPANY:
		frappe.throw(
			_(
				"These PostFinance IBANs belong to {0}; company {1} cannot be used."
			).format(SUPPORTED_COMPANY, company)
		)
	if not frappe.db.exists("Company", company):
		frappe.throw(_("Company {0} does not exist.").format(company))
	return company


def _add_issue(row, message):
	if message and message not in row["messages"]:
		row["messages"].append(message)


def _set_review(row):
	row["status"] = "review"
	row["status_label"] = _("Manual review")
	row["selectable"] = False


def _assert_read_access():
	if not frappe.has_permission("Payment Entry", "read"):
		frappe.throw(_("You need read access to Payment Entry."), frappe.PermissionError)


def _assert_setup_access():
	roles = set(frappe.get_roles())
	if not roles.intersection({"Accounts Manager", "System Manager"}):
		frappe.throw(
			_("Only an Accounts Manager or System Manager can configure bank accounts."),
			frappe.PermissionError,
		)


def _assert_create_access(submit):
	if not frappe.has_permission("Payment Entry", "create"):
		frappe.throw(
			_("You need create access to Payment Entry."), frappe.PermissionError
		)
	if submit and not frappe.has_permission("Payment Entry", "submit"):
		frappe.throw(
			_("You need submit access to Payment Entry."), frappe.PermissionError
		)
