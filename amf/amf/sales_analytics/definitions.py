"""Shared scope, date conventions and financial precision for AMF sales reporting."""

from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

COMPANY = "Advanced Microfluidics SA"
CURRENCY = "CHF"
HISTORY_START = date(2022, 1, 1)
COMMERCIAL_ORDER_TYPES = {"Production", "R&D", "Hybrid"}
CLOSED_ORDER_STATUSES = {"Closed", "Completed", "Cancelled"}
CHARGE_CODES = {"3410": "shipping", "3495": "card_charges", "2200": "vat"}
ZERO = Decimal("0")
CENT = Decimal("0.01")
QUANTITY_TOLERANCE = Decimal("0.000001")

METRICS = {
    "revenue": ("Revenue excl. VAT", "Posted net invoice items plus shipping and card charges.", "Actual"),
    "item_net": ("Net products and services", "Posted item net, including signed credits.", "Actual"),
    "order_intake": ("Order intake", "Latest valid order net in its first submission period.", "Actual"),
    "delivered": ("Delivered value", "Submitted commercial shipments and stock returns at posted net values.", "Actual"),
    "shipping": ("Shipping charges", "Posted shipping charges, excluding VAT.", "Actual"),
    "card_charges": ("Card charges", "Posted card processing charges, excluding VAT.", "Actual"),
    "vat": ("VAT", "Posted VAT on submitted invoices.", "Actual"),
    "gross": ("Invoice gross", "Posted invoice totals including VAT.", "Actual"),
    "undelivered": ("Undelivered commitments", "Open shipping quantity valued at the original order price.", "Committed"),
    "held_shipping": ("Shipping on hold", "Undelivered quantities on orders currently On Hold.", "Committed"),
    "overdue": ("Overdue shipping", "Open shipping commitments past their ERP shipping date.", "Committed"),
    "unbilled": ("Contract value still to invoice", "Remaining billable order quantities at original order prices.", "Committed"),
    "delivered_unbilled": ("Delivered value awaiting invoice", "Delivered quantities awaiting billing, valued at original order prices where linked.", "Committed"),
    "dated_billing": ("Dated confirmed billing", "Outstanding order amounts with an approved billing date.", "Outlook"),
    "unscheduled_billing": ("Unscheduled for invoicing", "Outstanding order amounts without an approved billing date.", "Committed"),
}


def number(value):
    return Decimal(str(value)) if value is not None else ZERO


def money(value):
    return number(value).quantize(CENT, rounding=ROUND_HALF_UP)


def day(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value) if value else None


def month_start(value):
    return value.replace(day=1)


def shift_month(value, offset):
    year, month = divmod(value.year * 12 + value.month - 1 + offset, 12)
    return date(year, month + 1, min(value.day, monthrange(year, month + 1)[1]))


def period_key(value, granularity):
    if granularity == "year":
        return str(value.year)
    if granularity == "quarter":
        return "{} Q{}".format(value.year, (value.month - 1) // 3 + 1)
    return value.strftime("%Y-%m")


def period_keys(start, end, granularity):
    current = month_start(start)
    keys = []
    while current <= end:
        key = period_key(current, granularity)
        if not keys or key != keys[-1]:
            keys.append(key)
        current = shift_month(current, 1)
    return keys


class Filters:
    def __init__(self, values, as_of):
        values = values or {}
        if not isinstance(values, dict):
            raise ValueError("Filters must be an object.")
        if values.get("company") not in (None, "", COMPANY):
            raise ValueError("Sales Analytics covers Advanced Microfluidics SA.")
        self.company = COMPANY
        self.as_of = day(as_of)
        self.from_date = day(values.get("from_date")) or date(self.as_of.year, 1, 1)
        self.to_date = day(values.get("to_date")) or self.as_of
        if not HISTORY_START <= self.from_date <= self.to_date <= self.as_of:
            raise ValueError("Use a date range from 1 January 2022 through today.")
        self.shipping_from = day(values.get("shipping_from"))
        self.shipping_to = day(values.get("shipping_to"))
        if self.shipping_from and self.shipping_to and self.shipping_to < self.shipping_from:
            raise ValueError("The shipping end date must be on or after the start date.")
        self.period = values.get("period") or "month"
        if self.period not in ("month", "quarter", "year"):
            raise ValueError("Choose a monthly, quarterly or annual period.")
        for field in ("customer", "item_code", "item_group", "territory", "order_status"):
            value = values.get(field) or ""
            if not isinstance(value, str) or len(value) > 140:
                raise ValueError("Invalid {}".format(field.replace("_", " ")))
            setattr(self, field, value.strip())

    @property
    def item_filtered(self):
        return bool(self.item_code or self.item_group)

    def matches(self, row, order=False):
        keys = ("customer", "item_code", "item_group", "territory")
        return all(not getattr(self, key) or row.get(key) == getattr(self, key) for key in keys) and (
            not order or not self.order_status or row.get("status") == self.order_status
        )
