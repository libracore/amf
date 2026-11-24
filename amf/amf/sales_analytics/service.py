"""Build dashboard, chart and detail responses from the same authorized facts."""

from collections import defaultdict
from datetime import date, timedelta

from .calculations import (
    delivered_unbilled, delivery_facts, invoice_facts, issue, match_billing, open_commitments,
    order_facts, total,
)
from .definitions import (
    HISTORY_START, METRICS, QUANTITY_TOLERANCE, ZERO, day, money, month_start, number,
    period_key, period_keys, shift_month,
)
from .sources import DELIVERY, INVOICE, LEDGER, ORDER

COLUMN_LABELS = {
    "document": "Document", "source": "Source", "date": "Date", "customer_name": "Customer",
    "item_code": "Item", "item_name": "Item name", "line": "Source row", "item_group": "Item group", "status": "Status",
    "order_type": "Order type", "original_order": "Original order",
    "original_invoice": "Credit against", "original_delivery": "Return against",
    "qty": "Qty", "uom": "UOM", "ordered_qty": "Ordered", "delivered_qty": "Fulfilled",
    "returned_qty": "Returned", "billed_qty": "Billed", "shipping_qty": "To ship",
    "unbilled_qty": "To invoice", "shipping_date": "ERP shipping date",
    "shipping_month": "Reporting shipping month", "overdue": "Overdue", "billed_actual": "Actual invoiced CHF",
    "billing_variance": "Billing variance CHF", "unit_price": "Original unit net CHF",
    "revisions": "Revisions", "reason": "Exception",
    "currency": "Original currency", "fx_rate": "Posting FX rate", "gross": "Gross CHF",
    "legacy_ht": "AMF Total HT CHF", "other_charges": "Other adjustments CHF",
    "gross_difference": "Gross difference CHF", "income_gl": "Invoice income GL CHF",
    "gl_difference": "Difference to income GL CHF", "gl_accounts": "Non-income GL accounts",
    "billing_date": "Expected invoice date", "billing_plan": "Approved billing record", "direct_delivery": "Direct delivery",
}

DETAILS = {
    "revenue": ("date", "document", "customer_name", "item_net", "shipping", "card_charges", "revenue", "vat", "gross", "currency", "fx_rate", "original_invoice"),
    "item_net": ("date", "document", "customer_name", "item_code", "item_name", "qty", "uom", "item_net", "original_invoice"),
    "order_intake": ("date", "document", "original_order", "customer_name", "item_code", "qty", "uom", "order_type", "order_intake"),
    "order_items": ("date", "document", "line", "original_order", "customer_name", "item_code", "qty", "uom", "order_type", "order_intake"),
    "order_changes": ("date", "document", "original_order", "customer_name", "order_type", "status", "revisions", "order_intake"),
    "delivered": ("date", "source", "document", "customer_name", "item_code", "qty", "uom", "delivered", "original_delivery"),
    "movements": ("date", "source", "document", "customer_name", "item_code", "qty", "uom", "delivered", "original_delivery"),
    "undelivered": ("document", "customer_name", "item_code", "status", "ordered_qty", "delivered_qty", "returned_qty", "shipping_qty", "uom", "unit_price", "shipping_date", "shipping_month", "overdue", "undelivered"),
    "unbilled": ("document", "customer_name", "item_code", "status", "ordered_qty", "delivered_qty", "billed_qty", "unbilled_qty", "uom", "unit_price", "billed_actual", "billing_variance", "unbilled"),
    "delivered_unbilled": ("date", "document", "line", "customer_name", "item_code", "qty", "unbilled_qty", "uom", "delivered_unbilled", "direct_delivery"),
    "dated_billing": ("billing_date", "document", "customer_name", "item_code", "dated_billing", "billing_plan"),
    "unscheduled_billing": ("document", "customer_name", "item_code", "unscheduled_billing"),
    "exceptions": ("source", "document", "item_code", "reason"),
    "reconciliation": ("date", "document", "customer_name", "item_net", "shipping", "card_charges",
                       "revenue", "vat", "other_charges", "gross", "gross_difference",
                       "legacy_ht", "income_gl", "gl_difference", "gl_accounts"),
}

for name in ("shipping", "card_charges", "vat", "gross"):
    DETAILS[name] = DETAILS["revenue"]
for name in ("item_net", "delivered", "movements", "undelivered", "unbilled", "dated_billing", "unscheduled_billing"):
    DETAILS[name] = DETAILS[name][:2] + ("line",) + DETAILS[name][2:]
DETAILS["overdue"] = DETAILS["undelivered"]
DETAILS["held_shipping"] = DETAILS["undelivered"]

MONEY_FIELDS = set(METRICS) - {"overdue"} | {
    "billed_actual", "billing_variance", "unit_price", "legacy_ht", "other_charges", "gross_difference", "income_gl", "gl_difference",
}
QUANTITY_FIELDS = {"qty", "ordered_qty", "delivered_qty", "returned_qty", "billed_qty", "shipping_qty", "unbilled_qty"}


class SalesAnalytics:
    def __init__(self, sources, filters):
        self.sources = sources
        self.filters = filters
        self.loaded = set()
        self.invoice_headers = []
        self.invoice_lines = []
        self.invoices = []
        self.invoice_items = []
        self.delivery_headers = []
        self.delivery_lines = []
        self.deliveries = []
        self.order_headers = []
        self.order_lines = []
        self.active_orders = []
        self.bookings = []
        self.booking_items = []
        self.order_changes = []
        self.commitments = []
        self.delivered_awaiting = []
        self.dated_billing = []
        self.unscheduled_billing = []
        self.targets = []
        self.exceptions = []

    def _load_invoices(self):
        if INVOICE in self.loaded:
            return
        self.invoice_headers, self.invoice_lines, charges = self.sources.invoices()
        self.invoices, self.invoice_items = invoice_facts(self.invoice_headers, self.invoice_lines, charges)
        visible = {row["name"] for row in self.invoice_headers}
        for row in self.invoices + self.invoice_items:
            if row.get("original_invoice") not in visible:
                row["original_invoice"] = None
        for row in self.invoices:
            if row["date"] >= HISTORY_START and row["currency"] != "CHF" and row["fx_rate"] <= 0:
                self.exceptions.append(issue(INVOICE, row["document"], "Invalid recorded FX rate. Posted CHF preserved."))
            if row["date"] >= HISTORY_START and row["currency"] != "CHF" and row["fx_rate"] == 1:
                self.exceptions.append(issue(INVOICE, row["document"], "Foreign-currency invoice stored at FX 1.0. Posted CHF preserved."))
            if row["date"] >= HISTORY_START and row["other_charges"]:
                self.exceptions.append(issue(INVOICE, row["document"], "Posted adjustment outside the shipping, card and VAT accounts."))
        self.loaded.add(INVOICE)

    def _load_orders(self):
        if ORDER in self.loaded:
            return
        self.order_headers, self.order_lines, self.packed, submitted = self.sources.orders()
        result = order_facts(self.order_headers, self.order_lines, submitted, self.filters.as_of)
        self.active_orders, self.bookings, self.booking_items, self.order_changes, exceptions = result
        self.exceptions.extend(exceptions)
        self.loaded.add(ORDER)

    def _load_deliveries(self):
        if DELIVERY in self.loaded:
            return
        self._load_invoices()
        self._load_orders()
        self.delivery_headers, self.delivery_lines = self.sources.deliveries()
        by_name = {row["name"]: row for row in self.delivery_headers}
        for line in self.delivery_lines:
            if line["parent"] in by_name:
                line["return_against"] = by_name[line["parent"]].get("return_against")
        self.deliveries = delivery_facts(self.delivery_headers, self.delivery_lines, self.order_headers,
                                       self.invoice_headers, self.invoice_lines)
        for row in self.deliveries:
            if row.get("original_delivery") not in by_name:
                row["original_delivery"] = None
        self.loaded.add(DELIVERY)

    def _billing_access(self):
        return all(self.sources.complete[doctype] for doctype in (ORDER, INVOICE, DELIVERY))

    def _load_commitments(self):
        if "commitments" in self.loaded:
            return
        self._load_deliveries()
        active_ids = {row["name"] for row in self.active_orders}
        stock = self.sources.stock_items({row["item_code"] for row in self.order_lines if row["parent"] in active_ids})
        linked = {row["so_detail"] for row in self.delivery_lines if row["so_detail"]}
        if self._billing_access():
            billing = match_billing(self.order_lines, self.delivery_lines, self.invoice_headers, self.invoice_lines)
            self.exceptions.extend(billing[-1])
            self.delivered_awaiting, exceptions = delivered_unbilled(
                self.delivery_lines, self.invoice_lines, billing,
                self.order_lines, self.active_orders, self.deliveries,
            )
            self.exceptions.extend(exceptions)
        else:
            billing = (defaultdict(lambda: ZERO), defaultdict(lambda: ZERO), {}, set(), set(), [])
        self.commitments, exceptions = open_commitments(
            self.active_orders, self.order_lines, self.packed, stock, linked, billing, self.filters.as_of,
        )
        self.exceptions.extend(exceptions)
        self.loaded.add("commitments")

    def _load_outlook(self):
        if "outlook" in self.loaded:
            return
        self._load_commitments()
        inputs = self.sources.approved_inputs()
        if self._billing_access():
            quantities = defaultdict(list)
            for row in inputs["billings"]:
                quantities[(row["sales_order"], row["order_item"])].append(row)
            for row in self.commitments:
                if row["is_on_hold"] or row["unbilled"] is None:
                    continue
                plans = quantities[(row["document"], row["line"])]
                qty = sum((number(plan["quantity"]) for plan in plans), ZERO)
                scheduled = ZERO
                if qty - row["unbilled_qty"] > QUANTITY_TOLERANCE:
                    self.exceptions.append(issue(ORDER, row["document"], "Approved billing schedule exceeds the current residual.", row["item_code"]))
                else:
                    remaining = row["unbilled_qty"]
                    for plan in sorted(plans, key=lambda entry: (entry["billing_date"], entry["name"])):
                        when = day(plan["billing_date"])
                        quantity = min(number(plan["quantity"]), remaining)
                        if when < self.filters.as_of or quantity <= 0:
                            continue
                        amount = quantity * row["unit_price"]
                        scheduled += amount
                        remaining -= quantity
                        self.dated_billing.append(dict(row, dated_billing=amount, billing_date=when, billing_plan=plan["name"]))
                if row["unbilled"] - scheduled:
                    self.unscheduled_billing.append(dict(row, unscheduled_billing=row["unbilled"] - scheduled))
        self.targets = inputs["targets"]
        self.loaded.add("outlook")

    def _selected(self, facts, start=None, end=None, order=False):
        for row in facts:
            if not self.filters.matches(row, order=order):
                continue
            if start and (not row["date"] or row["date"] < start):
                continue
            if end and (not row["date"] or row["date"] > end):
                continue
            yield row

    def _active_shipping(self, row, on_hold=False):
        if not row["shipping_qty"] or row["is_on_hold"] != on_hold:
            return False
        date_ = row["shipping_month"]
        if self.filters.shipping_from and (not date_ or date_ < month_start(self.filters.shipping_from)):
            return False
        if self.filters.shipping_to and (not date_ or date_ > month_start(self.filters.shipping_to)):
            return False
        return True

    def records(self, metric, period=None, group_key=None, group_value=None):
        start, end = self.filters.from_date, self.filters.to_date
        if metric in ("revenue", "item_net", "shipping", "card_charges", "vat", "gross", "reconciliation"):
            self._load_invoices()
            if metric not in ("item_net", "reconciliation") and self.filters.item_filtered:
                return None
            if not self.sources.readable[INVOICE]:
                return None
            facts = self.invoice_items if metric == "item_net" else self.invoices
            rows = list(self._selected(facts, start, end))
            if metric == "reconciliation":
                if self.filters.item_filtered or not self.sources.complete[INVOICE] or not self.sources.complete[LEDGER]:
                    return None
                rows = self._reconciliation(rows)
                if rows is None:
                    return None
        elif metric in ("order_intake", "order_items", "order_changes"):
            self._load_orders()
            if not self.sources.readable[ORDER]:
                return None
            facts = self.order_changes if metric == "order_changes" else (
                self.booking_items if self.filters.item_filtered or metric == "order_items" else self.bookings
            )
            rows = list(self._selected(facts, start, end, order=True))
        elif metric in ("delivered", "movements"):
            self._load_deliveries()
            if not self.sources.readable[DELIVERY]:
                return None
            rows = [row for row in self._selected(self.deliveries, start, end)
                    if row["commercial"] == (metric == "delivered")]
        elif metric in ("undelivered", "overdue", "held_shipping", "unbilled", "delivered_unbilled"):
            self._load_commitments()
            if not self.sources.readable[ORDER] or (metric in ("unbilled", "delivered_unbilled") and not self._billing_access()):
                return None
            facts = self.delivered_awaiting if metric == "delivered_unbilled" else self.commitments
            rows = list(self._selected(facts, order=True))
            if metric in ("undelivered", "overdue", "held_shipping"):
                rows = [row for row in rows if self._active_shipping(row, on_hold=metric == "held_shipping")
                        and (metric != "overdue" or row["overdue"])]
            elif metric == "unbilled":
                rows = [row for row in rows if row["unbilled"] is None or row["unbilled"] or row["unbilled_qty"]]
        elif metric in ("dated_billing", "unscheduled_billing"):
            self._load_outlook()
            if not self._billing_access():
                return None
            rows = list(self._selected(getattr(self, metric), order=True))
        else:
            self._load_outlook()
            return [row for row in self.exceptions if not self.filters.item_code or row.get("item_code") == self.filters.item_code]
        if period == "Without shipping date" and metric in ("undelivered", "overdue", "held_shipping"):
            rows = [row for row in rows if not row["shipping_month"]]
        elif period:
            field = "shipping_month" if metric in ("undelivered", "overdue", "held_shipping") else (
                "billing_date" if metric == "dated_billing" else "date"
            )
            rows = [row for row in rows if row.get(field) and period_key(row[field], self.filters.period) == period]
        if group_key:
            rows = [row for row in rows if row.get(group_key) == group_value]
        return rows

    def _reconciliation(self, records):
        ledger = self.sources.ledger()
        if ledger is None:
            return None
        income = defaultdict(lambda: ZERO)
        other = defaultdict(set)
        for row in ledger:
            if row["voucher_type"] != INVOICE:
                continue
            amount = number(row["credit"]) - number(row["debit"])
            if row["root_type"] == "Income":
                income[row["voucher_no"]] += amount
            elif row["root_type"] == "Expense" and amount:
                other[row["voucher_no"]].add(row["account"])
        return [
            dict(row, income_gl=income[row["document"]], gl_difference=row["revenue"] - income[row["document"]],
                 gl_accounts=", ".join(sorted(other[row["document"]])))
            for row in records
        ]

    def summary(self):
        self._load_outlook()
        f = self.filters
        revenue_key = "item_net" if f.item_filtered else "revenue"
        revenue_facts = self.invoice_items if f.item_filtered else self.invoices
        intake_facts = self.booking_items if f.item_filtered else self.bookings
        year_start = date(f.as_of.year, 1, 1)
        quarter_start = date(f.as_of.year, 3 * ((f.as_of.month - 1) // 3) + 1, 1)
        month = month_start(f.as_of)
        starts = [
            ("Current month", month, f.as_of),
            ("Current quarter", quarter_start, f.as_of),
            ("Year to date", year_start, f.as_of),
            ("Full prior year", date(f.as_of.year - 1, 1, 1), year_start - timedelta(days=1)),
            ("Rolling 12 completed months", shift_month(month, -12), month - timedelta(days=1)),
        ]
        cards = []
        if self.sources.readable[INVOICE]:
            for label, start, end in starts:
                if start >= HISTORY_START:
                    cards.append(self._dated_card(revenue_key, label, revenue_facts, start, end))
        if self.sources.readable[ORDER]:
            for label, start in (("Current month", month), ("Year to date", year_start)):
                cards.append(self._dated_card("order_intake", label, intake_facts, start, f.as_of))
        for metric in ("undelivered", "overdue", "unbilled", "delivered_unbilled", "unscheduled_billing"):
            rows = self.records(metric)
            if rows is not None:
                field = "undelivered" if metric == "overdue" else metric
                cards.append(dict(
                    metric=metric, label=METRICS[metric][0], period="As of {}".format(f.as_of),
                    value=money(total(rows, field)), change=None,
                ))

        trends = self._trends(revenue_key)
        shipping = self._shipping()
        selected_invoice_items = list(self._selected(self.invoice_items, f.from_date, f.to_date))
        selected_intake = list(self._selected(self.booking_items, f.from_date, f.to_date, order=True))
        selected_revenue = self.records(revenue_key) or []
        selected_orders = self.records("order_intake") or []
        prior_revenue = self._prior_cohort(revenue_facts)
        prior_invoice_items = self._prior_cohort(self.invoice_items)
        open_shipping = self.records("undelivered") or []
        return {
            "cards": cards, "metrics": METRICS, "period": f.period, "as_of": f.as_of,
            "from_date": f.from_date, "to_date": f.to_date,
            "readable": self.sources.readable, "billing_available": self._billing_access(),
            "revenue_metric": revenue_key, "trends": trends, "shipping_schedule": shipping,
            "selected_revenue": money(total(selected_revenue, revenue_key)) if self.sources.readable[INVOICE] else None,
            "reconciliation_available": self.sources.complete[INVOICE] and self.sources.complete[LEDGER],
            "charges": self._charges(selected_revenue) if not f.item_filtered and self.sources.readable[INVOICE] else None,
            "portfolio": {
                "customers": self._portfolio(selected_revenue, "customer", revenue_key, prior_revenue),
                "items": self._portfolio(selected_invoice_items, "item_code", "item_net", prior_invoice_items),
                "item_groups": self._portfolio(selected_invoice_items, "item_group", "item_net", prior_invoice_items),
                "quantity_leaders": self._quantity_leaders(selected_invoice_items),
                "intake_customers": self._portfolio(selected_orders, "customer", "order_intake"),
                "open_items": self._portfolio(open_shipping, "item_code", "undelivered"),
                "open_customers": self._portfolio(open_shipping, "customer", "undelivered"),
            },
            "order_statistics": {
                "orders": len({row["document"] for row in selected_orders}),
                "quantities": self._quantity_groups(selected_intake, "qty", "uom"),
            },
            "item": self._item_summary(selected_invoice_items) if f.item_code and self.sources.readable[INVOICE] else None,
            "outlook": self._outlook(year_start),
            "exceptions": len(self.records("exceptions")),
            "on_hold": money(total(self.records("held_shipping") or [], "undelivered")),
        }

    def _dated_card(self, metric, label, facts, start, end):
        value = total(self._selected(facts, start, end, order=metric == "order_intake"), metric)
        before = shift_month(start, -12)
        change = None
        if before >= HISTORY_START:
            prior = total(self._selected(facts, before, shift_month(end, -12), order=metric == "order_intake"), metric)
            if prior > 0:
                change = float((value - prior) * 100 / prior)
        return dict(metric=metric, label=METRICS[metric][0], period=label, value=money(value),
                    from_date=start, to_date=end, change=change)

    def _trends(self, revenue_key):
        f = self.filters
        keys = period_keys(f.from_date, f.to_date, f.period)
        result = {"labels": keys, "series": {}, "cumulative_revenue": []}
        for metric in (revenue_key, "order_intake", "delivered"):
            rows = self.records(metric)
            if rows is None:
                continue
            values = defaultdict(lambda: ZERO)
            previous = defaultdict(lambda: ZERO)
            for row in rows:
                values[period_key(row["date"], f.period)] += number(row[metric])
            if metric == revenue_key and shift_month(f.from_date, -12) >= HISTORY_START:
                candidates = self.invoice_items if f.item_filtered else self.invoices
                bounds = (shift_month(f.from_date, -12), shift_month(f.to_date, -12))
                for row in self._selected(candidates, *bounds):
                    previous[period_key(shift_month(row["date"], 12), f.period)] += number(row[metric])
                result["prior_revenue"] = [money(previous[key]) for key in keys]
            result["series"][metric] = [money(values[key]) for key in keys]
            if metric == revenue_key:
                cumulative = ZERO
                for key in keys:
                    cumulative += values[key]
                    result["cumulative_revenue"].append(money(cumulative))
        return result

    def _shipping(self):
        schedules = defaultdict(list)
        for row in self.records("undelivered") or []:
            key = period_key(row["shipping_month"], self.filters.period) if row["shipping_month"] else "Without shipping date"
            schedules[key].append(row)
        return [
            dict(period=key, value=money(total(rows, "undelivered")),
                 overdue=money(total((row for row in rows if row["overdue"]), "undelivered")),
                 orders=len({row["document"] for row in rows}), units=self._quantity_groups(rows, "shipping_qty", "uom"))
            for key, rows in sorted(schedules.items())
        ]

    @staticmethod
    def _quantity_groups(rows, qty, uom):
        quantities = defaultdict(lambda: ZERO)
        for row in rows:
            if row.get(uom):
                quantities[row[uom]] += number(row[qty])
        return {unit: value for unit, value in sorted(quantities.items())}

    def _prior_cohort(self, facts):
        start = shift_month(self.filters.from_date, -12)
        end = shift_month(self.filters.to_date, -12)
        return list(self._selected(facts, start, end)) if start >= HISTORY_START else None

    def _portfolio(self, rows, field, metric, previous=None):
        grouped = defaultdict(list)
        for row in rows:
            if row.get(field):
                grouped[row[field]].append(row)
        totals = []
        prior = defaultdict(list)
        if previous is not None:
            for row in previous:
                if row.get(field):
                    prior[row[field]].append(row)
        denominator = total(rows, metric)
        for key in grouped.keys() | prior.keys():
            group = grouped[key]
            value = total(group, metric)
            comparison = total(prior[key], metric) if previous is not None else None
            sample = (group or prior[key])[0]
            name = sample.get("customer_name") if field == "customer" else sample.get("item_name") if field == "item_code" else key
            totals.append(dict(key=key, label=name or key, value=money(value),
                               share=float(value * 100 / denominator) if denominator > 0 else None,
                               previous=money(comparison) if comparison is not None else None,
                               change=float((value - comparison) * 100 / comparison) if comparison and comparison > 0 else None,
                               records=len({row["document"] for row in group})))
        return sorted(totals, key=lambda row: (-row["value"], row["key"]))[:15]

    def _quantity_leaders(self, rows):
        by_unit = defaultdict(lambda: defaultdict(list))
        for row in rows:
            if row.get("stock_uom") and row.get("item_code"):
                by_unit[row["stock_uom"]][row["item_code"]].append(row)
        result = {}
        for unit, grouped in sorted(by_unit.items()):
            leaders = [
                {"key": code, "label": group[0]["item_name"] or code,
                 "qty": total(group, "stock_qty"), "value": money(total(group, "item_net"))}
                for code, group in grouped.items()
            ]
            result[unit] = sorted(leaders, key=lambda row: (-row["qty"], row["key"]))[:10]
        return result

    def _item_summary(self, rows):
        quantities = self._quantity_groups(rows, "stock_qty", "stock_uom")
        net = total(rows, "item_net")
        average = None
        if len(quantities) == 1 and next(iter(quantities.values())) > 0 and all(row["stock_uom"] for row in rows):
            average = money(net / next(iter(quantities.values())))
        grouped = defaultdict(list)
        for row in rows:
            grouped[period_key(row["date"], self.filters.period)].append(row)
        return {
            "quantity": quantities, "net": money(net), "average_price": average,
            "invoices": len({row["document"] for row in rows if not row["is_return"]}),
            "periods": [
                {"period": key, "quantities": self._quantity_groups(group, "stock_qty", "stock_uom"),
                 "value": money(total(group, "item_net")),
                 "invoices": len({row["document"] for row in group if not row["is_return"]})}
                for key, group in sorted(grouped.items())
            ],
        }

    @staticmethod
    def _charges(rows):
        return {field: money(total(rows, field)) for field in ("item_net", "shipping", "card_charges", "vat", "gross")}

    def _outlook(self, year_start):
        complete_billing = self._billing_access()
        end = date(year_start.year, 12, 31)
        billings = self.records("dated_billing") or []
        dated = [row for row in billings if year_start <= row["billing_date"] <= end]
        by_month = defaultdict(lambda: ZERO)
        for row in billings:
            by_month[period_key(row["billing_date"], "month")] += row["dated_billing"]
        unscheduled = total(self.records("unscheduled_billing") or [], "unscheduled_billing")
        metric = "item_net" if self.filters.item_filtered else "revenue"
        facts = self.invoice_items if self.filters.item_filtered else self.invoices
        actual = total(self._selected(facts, year_start, self.filters.as_of), metric)
        dated_total = total(dated, "dated_billing")
        targets = []
        f = self.filters
        scoped = f.customer or f.item_filtered or f.territory or f.order_status
        if not scoped:
            for row in self.targets:
                start, finish = day(row["from_date"]), day(row["to_date"])
                if finish < f.from_date or start > f.to_date or row["metric"] not in ("revenue", "order_intake"):
                    continue
                source_doctype = INVOICE if row["metric"] == "revenue" else ORDER
                if not self.sources.complete[source_doctype]:
                    continue
                source = self.invoices if source_doctype == INVOICE else self.bookings
                amount = number(row["target_amount"])
                value = total(self._selected(source, start, min(finish, f.as_of)), row["metric"])
                forecast = None
                if row["metric"] == "revenue" and start <= f.as_of <= finish:
                    approved = [entry for entry in billings if start <= entry["billing_date"] <= finish]
                    if approved:
                        forecast = value + total(approved, "dated_billing")
                targets.append({
                    "metric": row["metric"], "from_date": start, "to_date": finish, "target": money(amount),
                    "actual": money(value), "gap": money(value - amount),
                    "attainment": float(value * 100 / amount) if amount else None,
                    "variance_pct": float((value - amount) * 100 / amount) if amount else None,
                    "remaining": money(max(ZERO, amount - value)),
                    "outlook": money(forecast) if forecast is not None else None,
                    "outlook_gap": money(forecast - amount) if forecast is not None else None,
                })
        if not complete_billing and not targets:
            return None
        return {
            "actual": money(actual) if self.sources.readable[INVOICE] else None,
            "dated": money(dated_total) if complete_billing else None,
            "unscheduled": money(unscheduled) if complete_billing else None,
            "year_end": money(actual + dated_total) if dated else None,
            "monthly": {month: money(amount) for month, amount in sorted(by_month.items())}, "targets": targets,
        }


def detail_columns(metric):
    columns = []
    for key in DETAILS[metric]:
        definition = METRICS.get(key)
        label = COLUMN_LABELS.get(key) or (definition[0] + " (CHF)" if definition else key)
        kind = "currency" if key in MONEY_FIELDS else "number" if key in QUANTITY_FIELDS or key == "fx_rate" else "text"
        columns.append({"key": key, "label": label, "kind": kind})
    return columns


def public_row(row, columns, rounded=True):
    result = {column["key"]: row.get(column["key"]) for column in columns}
    for column in columns:
        key = column["key"]
        if rounded and column["kind"] == "currency" and result[key] is not None:
            result[key] = money(result[key])
    result.update(source=row.get("source"), is_return=bool(row.get("is_return")))
    return result
