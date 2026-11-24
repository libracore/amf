"""Bound financial selects to Frappe-visible parents and the reporting company."""

import json

import frappe

from .definitions import COMPANY, day

ORDER = "Sales Order"
INVOICE = "Sales Invoice"
DELIVERY = "Delivery Note"
LEDGER = "GL Entry"
ITEM = "Item"

DIMENSIONS = ("customer", "customer_name", "territory", "status")
LINE_FIELDS = ("item_code", "item_name", "item_group", "qty", "uom", "stock_qty", "stock_uom",
               "conversion_factor", "base_net_amount")
ORDER_FIELDS = DIMENSIONS + ("transaction_date", "amended_from", "sales_order_type", "base_net_total", "currency")
ORDER_LINE_FIELDS = LINE_FIELDS + ("delivery_date", "delivered_qty", "returned_qty", "delivered_by_supplier",
                                  "amount", "billed_amt", "amount_to_bill_now", "total_independent_price",
                                  "variable_price")
INVOICE_FIELDS = DIMENSIONS + ("posting_date", "creation", "conversion_rate", "currency", "is_return", "return_against",
                                "update_stock", "update_billed_amount_in_sales_order", "base_net_total",
                                "base_grand_total", "base_rounding_adjustment", "total_ht_company_currency")
INVOICE_LINE_FIELDS = LINE_FIELDS + ("so_detail", "sales_order", "dn_detail", "delivery_note")
DELIVERY_FIELDS = ("customer", "customer_name", "status", "posting_date", "is_return", "return_against",
                   "object", "issue", "loan_order", "loan_order_settlement_type")
DELIVERY_LINE_FIELDS = LINE_FIELDS + ("so_detail", "against_sales_order", "si_detail", "against_sales_invoice")
TAX_FIELDS = ("account_head", "base_tax_amount", "base_tax_amount_after_discount_amount")
LEDGER_FIELDS = ("posting_date", "voucher_type", "voucher_no", "account", "debit", "credit")
ACCOUNT_FIELDS = ("root_type",)
ORDER_ITEMS = ORDER + " Item"
INVOICE_ITEMS = INVOICE + " Item"
DELIVERY_ITEMS = DELIVERY + " Item"
TAX_TABLE = "Sales Taxes and Charges"
DECIMAL_FIELDS = {
    "qty", "stock_qty", "conversion_factor", "base_net_amount", "base_net_total", "delivered_qty",
    "returned_qty", "conversion_rate", "base_grand_total", "base_rounding_adjustment",
    "total_ht_company_currency", "base_tax_amount", "base_tax_amount_after_discount_amount",
    "debit", "credit", "quantity", "target_amount", "amount", "billed_amt", "amount_to_bill_now",
}

SOURCES = {
    ORDER: (ORDER_FIELDS, {ORDER_ITEMS: ORDER_LINE_FIELDS, "Packed Item": ("parent_detail_docname",)}),
    INVOICE: (INVOICE_FIELDS, {INVOICE_ITEMS: INVOICE_LINE_FIELDS, TAX_TABLE: TAX_FIELDS}),
    DELIVERY: (DELIVERY_FIELDS, {DELIVERY_ITEMS: DELIVERY_LINE_FIELDS}),
    LEDGER: (LEDGER_FIELDS, {}),
}


class Sources:
    def __init__(self, access, filters):
        self.access = access
        self.filters = filters
        self.readable = {
            doctype: access.can_read(doctype, fields, children)
            for doctype, (fields, children) in SOURCES.items()
        }
        self.complete = {doctype: self.readable[doctype] and access.complete(doctype) for doctype in SOURCES}

    @staticmethod
    def _query_visible(table, fields, key, names, extra="", args=None):
        rows = []
        if not names:
            return rows
        # The v12 MariaDB driver normally converts DECIMAL to Python floats.
        projection = ", ".join(
            "CAST(`{0}` AS CHAR) AS `{0}`".format(field) if field in DECIMAL_FIELDS else "`{}`".format(field)
            for field in fields
        )
        sql = "SELECT {} FROM `tab{}` WHERE `{}` IN %(names)s {}".format(projection, table, key, extra)
        for start in range(0, len(names), 500):
            params = dict(args or {}, names=tuple(names[start:start + 500]))
            rows.extend(frappe.db.sql(sql, params, as_dict=True))
        return rows

    def _names(self, doctype, filters=()):
        if not self.readable[doctype]:
            return []
        return self.access.visible_names(doctype, (("company", "=", COMPANY), *filters))

    def _children(self, parent, table, fields, names, parentfield="items"):
        return self._query_visible(
            table, ("name", "parent", "idx", *fields), "parent", names,
            "AND parenttype = %(doctype)s AND parentfield = %(parentfield)s",
            {"doctype": parent, "parentfield": parentfield},
        )

    def invoices(self):
        names = self._names(INVOICE, (("docstatus", "=", 1), ("posting_date", "<=", self.filters.as_of)))
        parents = self._query_visible(INVOICE, ("name", *INVOICE_FIELDS), "name", names)
        return (
            parents,
            self._children(INVOICE, INVOICE_ITEMS, INVOICE_LINE_FIELDS, names),
            self._children(INVOICE, TAX_TABLE, TAX_FIELDS, names, "taxes"),
        )

    def deliveries(self):
        names = self._names(DELIVERY, (("docstatus", "=", 1), ("posting_date", "<=", self.filters.as_of)))
        return (
            self._query_visible(DELIVERY, ("name", *DELIVERY_FIELDS), "name", names),
            self._children(DELIVERY, DELIVERY_ITEMS, DELIVERY_LINE_FIELDS, names),
        )

    def orders(self):
        names = self._names(ORDER, (("docstatus", ">", 0),))
        parents = self._query_visible(ORDER, ("name", "docstatus", *ORDER_FIELDS), "name", names)
        valid = [row.name for row in parents if row.docstatus == 1]
        versions = self._query_visible(
            "Version", ("docname", "creation", "data"), "docname", names,
            "AND ref_doctype = %(doctype)s AND data LIKE %(changes)s",
            {"doctype": ORDER, "changes": "%docstatus%"},
        )
        submitted = {}
        for row in versions:
            try:
                changes = json.loads(row.data).get("changed", [])
            except (TypeError, ValueError, AttributeError):
                continue
            if any(
                len(change) == 3 and change[0] == "docstatus"
                and str(change[1]) == "0" and str(change[2]) == "1"
                for change in changes
            ):
                value = day(row.creation)
                submitted[row.docname] = min(value, submitted.get(row.docname, value))
        return (
            parents,
            self._children(ORDER, ORDER_ITEMS, ORDER_LINE_FIELDS, valid),
            self._children(ORDER, "Packed Item", ("parent_detail_docname",), valid, "packed_items"),
            submitted,
        )

    def stock_items(self, codes):
        if not codes or not self.access.can_read(ITEM, ("is_stock_item",)):
            return {}
        names = []
        codes = sorted(codes)
        for start in range(0, len(codes), 500):
            names.extend(self.access.visible_names(ITEM, (("name", "in", tuple(codes[start:start + 500])),)))
        rows = self._query_visible(ITEM, ("name", "is_stock_item"), "name", names)
        return {row.name: bool(row.is_stock_item) for row in rows}

    def ledger(self):
        if not self.readable[LEDGER] or not self.access.can_read("Account", ACCOUNT_FIELDS) or not self.access.complete("Account"):
            return None
        names = self._names(LEDGER, (
            ("posting_date", ">=", self.filters.from_date), ("posting_date", "<=", self.filters.to_date),
        ))
        records = self._query_visible(LEDGER, ("name", *LEDGER_FIELDS), "name", names)
        accounts = self.access.visible_names("Account", (("company", "=", COMPANY),))
        roots = {
            row.name: row.root_type for row in self._query_visible("Account", ("name", *ACCOUNT_FIELDS), "name", accounts)
        }
        for row in records:
            row["root_type"] = roots.get(row.account)
        return [row for row in records if row.root_type]

    def approved_inputs(self):
        """Read optional AMF reporting records when the configuration is installed."""
        result = {"billings": [], "targets": []}
        definitions = {
            "billings": ("Sales Analytics Billing", ("sales_order", "order_item", "billing_date", "quantity")),
            "targets": ("Sales Analytics Target", ("metric", "from_date", "to_date", "target_amount")),
        }
        for key, (doctype, fields) in definitions.items():
            if not frappe.db.exists("DocType", doctype) or not self.access.can_read(doctype, fields):
                continue
            names = self.access.visible_names(doctype, (("company", "=", COMPANY), ("docstatus", "=", 1)))
            result[key] = self._query_visible(doctype, ("name", *fields), "name", names)
        return result
