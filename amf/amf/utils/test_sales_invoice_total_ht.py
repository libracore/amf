# -*- coding: utf-8 -*-
# Copyright (c) 2026, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import unittest

import frappe

from amf.amf.report.sales_invoice_trends.sales_invoice_trends import (
    CUSTOMER_DISPLAY_FIELD,
    TOTAL_HT_ITEM_AMOUNT_SQL,
    add_customer_display_names,
    apply_customer_link_to_conditions,
    apply_total_ht_to_conditions,
)
from amf.amf.utils.sales_invoice_total_ht import (
    TOTAL_HT_FIELD,
    TOTAL_HT_LABEL,
    get_sales_invoice_total_ht,
    is_total_ht_charge,
)


class TestSalesInvoiceTotalHT(unittest.TestCase):
    def test_product_shipping_card_processing_excluding_vat(self):
        taxes = [
            frappe._dict(
                account_head="3410 - Shipping fee - AMF21",
                description="Shipping",
                base_tax_amount_after_discount_amount=50,
            ),
            frappe._dict(
                account_head="3495 - Card Processing Surcharge - AMF21",
                description="Card processing",
                base_tax_amount_after_discount_amount=15,
            ),
            frappe._dict(
                account_head="2200 - VAT due - AMF21",
                description="VAT 8.1%",
                base_tax_amount_after_discount_amount=86.265,
            ),
        ]

        self.assertEqual(get_sales_invoice_total_ht(1000, taxes), 1065)

    def test_legacy_shipping_description_is_included(self):
        shipping = frappe._dict(
            account_head="4072 - Legacy charge - AMF_OLD",
            description="Transport & Shipping Fees",
        )
        self.assertTrue(is_total_ht_charge(shipping))

    def test_unrelated_charge_is_excluded(self):
        unrelated_charge = frappe._dict(
            account_head="3290 - Loss of sales revenue - AMF21",
            description="Adjustment",
        )
        self.assertFalse(is_total_ht_charge(unrelated_charge))

    def test_base_tax_amount_fallback(self):
        shipping = frappe._dict(
            account_head="3410 - Shipping fee - AMF21",
            description="Shipping",
            base_tax_amount=25,
            base_tax_amount_after_discount_amount=None,
        )
        self.assertEqual(get_sales_invoice_total_ht(100, [shipping]), 125)

    def test_report_uses_total_ht_and_renames_total_column(self):
        conditions = {
            "period_wise_select": (
                "SUM(t2.stock_qty), SUM(t2.base_net_amount)"
            ),
            "columns": [
                "Total(Qty):Float:120",
                "Total(Amt):Currency:120",
            ],
        }

        apply_total_ht_to_conditions(conditions)

        self.assertIn(TOTAL_HT_ITEM_AMOUNT_SQL, conditions["period_wise_select"])
        self.assertIn(TOTAL_HT_FIELD, conditions["period_wise_select"])
        self.assertEqual(
            conditions["columns"][-1],
            TOTAL_HT_LABEL + ":Currency:190",
        )

    def test_customer_link_uses_document_id_and_retains_display_name(self):
        conditions = {
            "based_on_select": "t1.customer_name, t1.territory,",
        }
        filters = frappe._dict(based_on="Customer")

        apply_customer_link_to_conditions(filters, conditions)

        self.assertEqual(
            conditions["based_on_select"],
            "t1.customer, t1.territory,",
        )

        columns = [
            "Customer:Link/Customer:120",
            "Territory:Link/Territory:120",
        ]
        data = [["O00713", "Switzerland"]]
        add_customer_display_names(
            columns,
            data,
            {"O00713": "LABMaiTE"},
        )

        self.assertEqual(data[0][0], "O00713")
        self.assertEqual(data[0][1], "LABMaiTE")
        self.assertEqual(columns[1]["fieldname"], CUSTOMER_DISPLAY_FIELD)
        self.assertEqual(columns[1]["hidden"], 1)


if __name__ == "__main__":
    unittest.main()
