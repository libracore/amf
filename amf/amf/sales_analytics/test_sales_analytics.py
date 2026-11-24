"""Regression tests for the approved sales definitions, independent of a live ERP."""

import unittest
from datetime import date, datetime
from decimal import Decimal

from amf.amf.page.sales_analytics.sales_analytics import export_cell, fetch_records
from amf.amf.sales_analytics.calculations import order_facts
from amf.amf.sales_analytics.definitions import Filters, number
from amf.amf.sales_analytics.service import SalesAnalytics, detail_columns, public_row
from amf.amf.sales_analytics.sources import DELIVERY, INVOICE, LEDGER, ORDER


def parent(name, **values):
    return dict(
        dict(
            name=name, customer="CUSTOMER", customer_name="Customer", territory="Switzerland",
            docstatus=1, status="To Deliver and Bill", transaction_date=date(2026, 10, 3),
            amended_from=None, base_net_total=10000, sales_order_type="Production",
        ), **values
    )


def invoice(name, **values):
    return parent(name, **dict(
        dict(
            posting_date=date(2026, 10, 12), is_return=0, return_against=None,
            update_stock=0, update_billed_amount_in_sales_order=0,
            currency="CHF", conversion_rate=1, base_grand_total=11026.20,
            total_ht_company_currency=10200,
        ), **values
    ))


def shipment(name, **values):
    return parent(name, **dict(
        dict(posting_date=date(2026, 10, 11), is_return=0, return_against=None,
             object="Merchandise", issue=None, loan_order=None, loan_order_settlement_type=None),
        **values
    ))


def item(name, doc, **values):
    return dict(
        dict(
            name=name, parent=doc, idx=1, item_code="PUMP", item_name="Pump", item_group="Devices",
            qty=10, stock_qty=10, stock_uom="Nos", uom="Nos", conversion_factor=1,
            base_net_amount=10000, delivery_date=date(2026, 10, 20),
            delivered_qty=4, returned_qty=0, delivered_by_supplier=0,
            so_detail=None, sales_order=None, dn_detail=None, delivery_note=None,
            against_sales_order=None, si_detail=None, against_sales_invoice=None, return_against=None,
        ), **values
    )


def tax(account, value):
    return dict(parent="INV", account_head=account, base_tax_amount=value, base_tax_amount_after_discount_amount=value)


class Facts:
    def __init__(self):
        self.readable = {doctype: True for doctype in (INVOICE, DELIVERY, ORDER, LEDGER)}
        self.complete = self.readable.copy()
        self.order = parent("SO")
        self.orders_data = ([self.order], [item("SO-ROW", "SO")], [], {"SO": date(2026, 10, 4)})
        self.invoice_data = ([invoice("INV")], [
            item("INV-ROW", "INV", qty=2, stock_qty=2, base_net_amount=4500,
                 so_detail="SO-ROW", sales_order="SO", dn_detail="DN-ROW", delivery_note="DN"),
            item("INV-SERVICE", "INV", item_code="SERVICE", qty=1, stock_qty=1, base_net_amount=5500),
        ], [tax("3410 - Shipping", 200), tax("2200 - VAT", 826.20)])
        self.shipment_data = ([shipment("DN")], [
            item("DN-ROW", "DN", qty=4, stock_qty=4, base_net_amount=4000,
                 so_detail="SO-ROW", against_sales_order="SO")
        ])
        self.inputs = {"targets": [], "billings": []}

    def invoices(self):
        return self.invoice_data if self.readable[INVOICE] else ([], [], [])

    def orders(self):
        return self.orders_data if self.readable[ORDER] else ([], [], [], {})

    def deliveries(self):
        return self.shipment_data if self.readable[DELIVERY] else ([], [])

    def stock_items(self, codes):
        return {code: code != "SERVICE" for code in codes}

    def approved_inputs(self):
        return self.inputs

    def ledger(self):
        return [
            {"root_type": "Income", "credit": 9900, "debit": 0, "voucher_type": INVOICE, "voucher_no": "INV", "account": "3001 - Revenue"},
            {"root_type": "Expense", "credit": 300, "debit": 0, "voucher_type": INVOICE, "voucher_no": "INV", "account": "4006 - Materials"},
            {"root_type": "Income", "credit": 500, "debit": 0, "voucher_type": "Journal Entry", "voucher_no": "JE", "account": "3001 - Revenue"},
        ]


class TestSalesAnalytics(unittest.TestCase):
    def setUp(self):
        self.facts = Facts()

    def analytics(self, today=date(2026, 11, 1), **values):
        filters = Filters(dict({"from_date": "2026-10-01", "to_date": "2026-10-31"}, **values), today)
        return SalesAnalytics(self.facts, filters)

    def test_billed_turnover_bridges_items_shipping_and_vat(self):
        service = self.analytics()
        dashboard = service.summary()
        self.assertEqual(dashboard["trends"]["series"]["revenue"], [Decimal("10200.00")])
        self.assertEqual(dashboard["charges"]["item_net"], Decimal("10000.00"))
        self.assertEqual(dashboard["charges"]["shipping"], Decimal("200.00"))
        self.assertEqual(dashboard["charges"]["gross"], Decimal("11026.20"))
        reconciliation = service.records("reconciliation")[0]
        self.assertEqual(reconciliation["gross_difference"], 0)
        self.assertEqual(reconciliation["gl_difference"], 300)
        self.assertEqual(reconciliation["gl_accounts"], "4006 - Materials")
        self.assertEqual(reconciliation["income_gl"], 9900)

    def test_cumulative_revenue_rounds_after_accumulation(self):
        self.facts.invoice_data = ([
            invoice("OCT", base_net_total="1.004", base_grand_total="1.004"),
            invoice("NOV", base_net_total="1.004", base_grand_total="1.004", posting_date=date(2026, 11, 1)),
        ], [], [])
        trends = self.analytics(to_date="2026-11-01").summary()["trends"]
        self.assertEqual(trends["series"]["revenue"], [Decimal("1.00"), Decimal("1.00")])
        self.assertEqual(trends["cumulative_revenue"], [Decimal("1.00"), Decimal("2.01")])

    def test_invoice_level_charges_are_counted_once(self):
        service = self.analytics()
        self.assertEqual(len(service.records("item_net")), 2)
        self.assertEqual(len(service.records("revenue")), 1)
        filtered = self.analytics(item_code="PUMP")
        dashboard = filtered.summary()
        self.assertEqual(dashboard["trends"]["series"]["item_net"], [4500])
        self.assertIsNone(filtered.records("revenue"))
        self.assertEqual(dashboard["item"]["average_price"], 2250)

    def test_charge_only_invoice_is_revenue(self):
        self.facts.invoice_data = ([invoice("INV", base_net_total=0, base_grand_total=200)], [], [tax("3410 - Shipping", 200)])
        row = self.analytics().records("revenue")[0]
        self.assertEqual(row["revenue"], 200)
        self.assertEqual(row["gross_difference"], 0)

    def test_signed_credit_posting_and_recorded_foreign_currency_rate(self):
        self.facts.invoice_data[0].append(invoice(
            "CR", is_return=1, currency="EUR", conversion_rate=1, posting_date=date(2026, 11, 1),
            base_net_total=-500, base_grand_total=-500, return_against="INV",
        ))
        service = self.analytics(from_date="2026-11-01", to_date="2026-11-01")
        row = service.records("revenue")[0]
        self.assertEqual(row["revenue"], -500)
        self.assertEqual(row["original_invoice"], "INV")
        self.assertTrue(any("FX 1.0" in row["reason"] for row in service.records("exceptions")))

    def test_amendment_restates_original_submission(self):
        root = parent("SO", docstatus=2)
        amendment = parent("SO-1", amended_from="SO", transaction_date=date(2026, 11, 1), base_net_total=7500)
        self.facts.orders_data = ([root, amendment], [item("SO-NEW", "SO-1", base_net_amount=7500)],
                                  [], {"SO": date(2026, 10, 4), "SO-1": date(2026, 11, 1)})
        service = self.analytics()
        bookings = service.records("order_intake")
        self.assertEqual(len(bookings), 1)
        self.assertEqual(bookings[0]["date"], date(2026, 10, 4))
        self.assertEqual(bookings[0]["order_intake"], 7500)
        self.assertEqual(service.records("order_changes")[0]["revisions"], 2)

    def test_cancelled_order_is_only_in_change_detail(self):
        self.facts.order["docstatus"] = 2
        service = self.analytics()
        self.assertEqual(service.records("order_intake"), [])
        self.assertEqual(service.records("order_changes")[0]["order_intake"], 0)

    def test_unknown_amendment_parent_does_not_create_booking_date(self):
        order = parent("SO-1", amended_from="MISSING")
        active, bookings, _, _, exceptions = order_facts([order], [], {"SO-1": date(2026, 11, 1)}, date(2026, 11, 2))
        self.assertEqual(active, [order])
        self.assertEqual(bookings, [])
        self.assertEqual(len(exceptions), 1)

    def test_shipping_carry_forward_keeps_source_date_and_original_price(self):
        service = self.analytics()
        row, = service.records("undelivered", "2026-11")
        self.assertEqual(row["shipping_date"], date(2026, 10, 20))
        self.assertEqual(row["shipping_month"], date(2026, 11, 1))
        self.assertEqual(row["shipping_qty"], 6)
        self.assertEqual(row["undelivered"], 6000)
        self.assertTrue(row["overdue"])
        self.assertEqual(service.records("undelivered", "2026-10"), [])

        self.facts.orders_data[1][0]["delivered_qty"] = 6
        next_month = self.analytics(today=date(2026, 12, 1))
        self.assertEqual(next_month.records("undelivered", "2026-12")[0]["undelivered"], 4000)

    def test_on_hold_shipping_is_separate(self):
        self.facts.order["status"] = "On Hold"
        service = self.analytics()
        self.assertEqual(service.records("undelivered"), [])
        self.assertEqual(service.records("held_shipping")[0]["undelivered"], 6000)
        self.assertEqual(service.summary()["on_hold"], 6000)

    def test_inconsistent_amendment_chain_contributes_no_duplicate_commitments(self):
        root = parent("SO")
        successor = parent("SO-1", amended_from="SO")
        active, bookings, _, _, exceptions = order_facts(
            [root, successor], [], {"SO": date(2026, 10, 1), "SO-1": date(2026, 11, 1)}, date(2026, 11, 2),
        )
        self.assertEqual(active, [])
        self.assertEqual(bookings, [])
        self.assertEqual(len(exceptions), 2)

    def test_shipping_remains_committed_when_stock_classification_includes_kit(self):
        row = item("KIT-ROW", "SO", item_code="SERVICE", qty=2, delivered_qty=0, base_net_amount=1500)
        self.facts.orders_data[1].append(row)
        self.facts.orders_data[2].append({"parent_detail_docname": "KIT-ROW"})
        service = self.analytics()
        self.assertEqual({row["line"] for row in service.records("undelivered")}, {"SO-ROW", "KIT-ROW"})

    def test_delivery_and_billing_residuals_are_different(self):
        service = self.analytics()
        order, = service.records("unbilled")
        shipped, = service.records("delivered_unbilled")
        self.assertEqual(order["unbilled"], 8000)
        self.assertEqual(order["billed_actual"], 4500)
        self.assertEqual(order["billing_variance"], 2500)
        self.assertEqual(shipped["delivered_unbilled"], 2000)

    def test_partial_return_reduces_delivered_awaiting_billing(self):
        self.facts.shipment_data[0].append(shipment("DN-RET", is_return=1, return_against="DN"))
        self.facts.shipment_data[1].append(item("RET-ROW", "DN-RET", qty=-1, stock_qty=-1, base_net_amount=-1000,
                                               so_detail="SO-ROW", against_sales_order="SO"))
        service = self.analytics()
        self.assertEqual(service.records("delivered_unbilled")[0]["delivered_unbilled"], 1000)
        self.assertEqual(sum(row["delivered"] for row in service.records("delivered")), 3000)

    def test_warranty_and_return_to_supplier_are_operational_movements(self):
        for name, purpose in (("WARRANTY", "Replacement under warranty"), ("VENDOR-RETURN", "Returned Goods")):
            self.facts.shipment_data[0].append(shipment(name, object=purpose, status="To Bill"))
            self.facts.shipment_data[1].append(item(name + "-ROW", name, base_net_amount=3241.89))
        service = self.analytics()
        self.assertEqual({row["document"] for row in service.records("movements")}, {"WARRANTY", "VENDOR-RETURN"})
        self.assertEqual({row["document"] for row in service.records("delivered")}, {"DN"})
        self.assertTrue(all(row["document"] == "DN" for row in service.records("delivered_unbilled")))

    def test_commercial_return_uses_original_shipment_classification(self):
        self.facts.shipment_data[0].append(shipment("DN-RET", is_return=1, return_against="DN", object="Return to seller"))
        self.facts.shipment_data[1].append(item("RET-ROW", "DN-RET", qty=-1, stock_qty=-1, base_net_amount=-1000))
        service = self.analytics()
        self.assertEqual({row["document"] for row in service.records("delivered")}, {"DN", "DN-RET"})

    def test_credit_and_reinvoice_on_same_shipment_count_order_quantity_once(self):
        headers, lines, _ = self.facts.invoice_data
        headers[0]["creation"] = datetime(2026, 10, 12, 9)
        headers.extend([
            invoice("CREDIT", is_return=1, return_against="INV", creation=datetime(2026, 10, 12, 10)),
            invoice("REINVOICE", creation=datetime(2026, 10, 12, 11)),
        ])
        lines.append(dict(lines[0], name="CREDIT-ROW", parent="CREDIT", qty=-2, stock_qty=-2, base_net_amount=-4500))
        lines.append(dict(lines[0], name="REINVOICE-ROW", parent="REINVOICE", base_net_amount=4000))
        order, = self.analytics().records("unbilled")
        self.assertEqual(order["billed_qty"], 2)
        self.assertEqual(order["billed_actual"], 4000)
        self.assertEqual(order["unbilled"], 8000)

    def test_credit_without_reopening_or_reinvoice_keeps_order_quantity_billed(self):
        headers, lines, _ = self.facts.invoice_data
        headers.append(invoice("CREDIT", is_return=1, return_against="INV", posting_date=date(2026, 10, 13)))
        lines.append(dict(lines[0], name="CREDIT-ROW", parent="CREDIT", qty=-2, stock_qty=-2, base_net_amount=-4500))
        order, = self.analytics().records("unbilled")
        self.assertEqual(order["billed_qty"], 2)
        self.assertEqual(order["billed_actual"], 0)

    def test_erp_amount_balance_on_fully_invoiced_quantity_is_visible(self):
        self.facts.order["currency"] = "EUR"
        self.facts.orders_data[1][0].update(qty=2, amount=5000, billed_amt=4500)
        service = self.analytics()
        self.assertEqual(service.records("unbilled"), [])
        exception, = [entry for entry in service.records("exceptions") if entry.get("erp_order_balance")]
        self.assertEqual(exception["erp_order_balance"], 500)
        self.assertEqual(exception["original_currency"], "EUR")

    def test_zero_quantity_zero_amount_is_a_known_zero(self):
        self.facts.orders_data[1][0].update(qty=0, base_net_amount=0, delivered_qty=0)
        headers, lines, charges = self.facts.invoice_data
        self.facts.invoice_data = (headers, [lines[1]], charges)
        self.assertEqual(self.analytics().records("unbilled"), [])

    def test_direct_references_do_not_assume_a_shipment_allocation(self):
        self.facts.invoice_data[1][0].update(dn_detail=None, delivery_note=None)
        service = self.analytics()
        self.assertEqual(service.records("unbilled")[0]["unbilled"], 8000)
        self.assertEqual(service.records("delivered_unbilled"), [])
        self.assertTrue(any("allocated" in row["reason"] for row in service.records("exceptions")))

    def test_billing_scope_cannot_treat_hidden_invoices_as_unbilled(self):
        self.facts.readable[INVOICE] = self.facts.complete[INVOICE] = False
        service = self.analytics()
        self.assertIsNone(service.records("unbilled"))
        self.assertIsNone(service.records("delivered_unbilled"))
        self.assertEqual(service.records("undelivered")[0]["undelivered"], 6000)
        self.assertFalse(service.summary()["billing_available"])

    def test_approved_billing_dates_do_not_follow_shipping_date(self):
        self.facts.inputs["billings"].append(dict(
            name="BILL-01", sales_order="SO", order_item="SO-ROW", billing_date=date(2026, 12, 2), quantity=3,
        ))
        service = self.analytics()
        outlook = service.summary()["outlook"]
        self.assertEqual(outlook["monthly"], {"2026-12": Decimal("3000.00")})
        self.assertEqual(outlook["unscheduled"], 5000)
        self.assertEqual(outlook["year_end"], 13200)
        self.assertEqual(service.records("undelivered")[0]["shipping_month"].month, 11)

    def test_overscheduled_billing_remains_unscheduled(self):
        self.facts.inputs["billings"].append(dict(
            name="BILL-01", sales_order="SO", order_item="SO-ROW", billing_date=date(2026, 12, 2), quantity=9,
        ))
        outlook = self.analytics().summary()["outlook"]
        self.assertEqual(outlook["unscheduled"], 8000)
        self.assertIsNone(outlook["year_end"])

    def test_annual_target_uses_submitted_target_without_inventing_outlook(self):
        self.facts.inputs["targets"].append(dict(
            name="TARGET-1", metric="revenue", from_date=date(2026, 1, 1), to_date=date(2026, 12, 31), target_amount=12000,
        ))
        target, = self.analytics().summary()["outlook"]["targets"]
        self.assertEqual(target["actual"], 10200)
        self.assertEqual(target["remaining"], 1800)
        self.assertIsNone(target["outlook"])

    def test_authorized_detail_uses_same_amount_as_summary(self):
        service = self.analytics()
        columns, rows = fetch_records(service, "revenue", "2026-10", None, None, "revenue", "desc")
        self.assertEqual(sum(public_row(row, columns)["revenue"] for row in rows),
                         service.summary()["trends"]["series"]["revenue"][0])
        self.assertIn("line", {column["key"] for column in detail_columns("unbilled")})

    def test_formulas_in_exports_are_plain_text(self):
        self.assertEqual(export_cell('  =2+2'), "'  =2+2")
        self.assertEqual(export_cell(number("-2.32")), -2.32)

    def test_archive_period_is_not_selectable(self):
        with self.assertRaises(ValueError):
            self.analytics(from_date="2021-01-01")


if __name__ == "__main__":
    unittest.main()
