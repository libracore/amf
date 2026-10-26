"""Export invoice rates to private database artifacts, without public files."""

import csv
import io
import statistics
from collections import defaultdict

import frappe
from frappe.utils import cint

from amf.amf.utils import data_artifact as artifacts


INVOICE_TYPES = ("Sales Invoice", "Purchase Invoice")


def _rates(invoice_doctype="Sales Invoice", submitted_only=True, company_currency=None):
    # These queries span all invoice records. Require an administrative role,
    # and allowlist the only identifiers interpolated into SQL.
    frappe.only_for("System Manager")
    if invoice_doctype not in INVOICE_TYPES:
        raise ValueError("Invoice type must be Sales Invoice or Purchase Invoice")
    frappe.has_permission(invoice_doctype, "read", throw=True)
    party = "customer" if invoice_doctype == "Sales Invoice" else "supplier"
    conditions, params = [], []
    if cint(submitted_only):
        conditions.append("invoice.docstatus = 1")
    if company_currency:
        conditions.append("company.default_currency = %s")
        params.append(company_currency)
    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    return frappe.db.sql("""
        SELECT line.item_code, line.{rate} AS rate, {currency} AS currency,
            invoice.{party} AS party
        FROM `tab{doctype} Item` line
        JOIN `tab{doctype}` invoice ON invoice.name = line.parent
        JOIN `tabCompany` company ON company.name = invoice.company
        {where}
        ORDER BY invoice.posting_date DESC, invoice.posting_time DESC,
            invoice.creation DESC, invoice.name DESC, line.idx DESC, line.name DESC
    """.format(doctype=invoice_doctype, party=party, where=where,
               rate="base_rate" if company_currency else "rate",
               currency="company.default_currency" if company_currency else "invoice.currency"),
        tuple(params), as_dict=True)


def _export(rows, file_name=None, latest=False, single_party=False):
    rates, parties = defaultdict(list), defaultdict(set)
    for row in rows:
        if not row.item_code:
            continue
        parties[row.item_code].add(row.party)
        # Keep currencies separate; an average of CHF and EUR is meaningless.
        key = row.item_code, row.currency
        if not latest or key not in rates:
            rates[key].append(float(row.rate or 0))
    if single_party:
        rates = {key: values for key, values in rates.items() if len(parties[key[0]]) == 1}
    if not rates:
        raise ValueError("No invoice rates found for the given criteria")
    width = max(len(values) for values in rates.values())
    with io.StringIO(newline="") as output:
        writer = csv.writer(output)
        writer.writerow(["Item Code", "Currency", "Average"] + ["Rate {}".format(i + 1) for i in range(width)])
        for (item, currency), values in sorted(rates.items()):
            # Escape spreadsheet formulas in externally supplied text cells.
            item = "'" + item if item.startswith(("=", "+", "-", "@")) else item
            writer.writerow([item, currency, "{:.2f}".format(statistics.mean(values))]
                + ["{:.2f}".format(value) for value in values] + [""] * (width - len(values)))
        name = artifacts.put(file_name or artifacts.new_name("item-last-rate" if latest else "item-rates"),
                             output.getvalue())
    return artifacts.download_url(name)


@frappe.whitelist(methods=["POST"])
def export_item_rates_to_csv(invoice_doctype="Sales Invoice", file_name=None,
                             submitted_only=True, company_currency=None):
    """Return an authenticated download URL; optional conversion uses base rates.

    Output includes Currency and groups each Item/currency independently.
    The request or bench caller owns the transaction.
    """
    return _export(_rates(invoice_doctype, submitted_only, company_currency), file_name)


def export_item_last_rate_single_customer_csv():
    """Latest rate per Item/currency, restricted to Items with one customer."""
    return _export(_rates(), latest=True, single_party=True)


def export_item_last_rate_csv():
    """Latest rate per Item/currency, as an authenticated database download."""
    return _export(_rates(), latest=True)
