import unittest
from unittest.mock import Mock, patch

import frappe
from pymysql.err import OperationalError

from amf.amf.utils import delivery_note_api


class TestDeliveryNoteTariffLookup(unittest.TestCase):
    def setUp(self):
        self.country = "Australia"
        self.tariff_row = {"eu": "EU tariff", "us": "US tariff", "ch": "CH tariff"}
        self.db = Mock()
        self.db.exists.return_value = True
        self.db.get_value.side_effect = self.get_value
        item = frappe._dict(item_code="C100", item_name="Power Supply", item_group="Accessories")

        for active_patch in (
            patch.object(frappe, "db", self.db),
            patch.object(frappe, "get_doc", return_value=item),
        ):
            active_patch.start()
            self.addCleanup(active_patch.stop)

    def get_value(self, doctype, filters, fieldname, as_dict=False):
        if doctype == "Address":
            return self.country

        self.assertEqual(doctype, "HS Code Table")
        self.assertEqual(filters, {"item_type": "C100, Power Supply"})
        if fieldname == "*" and as_dict:
            return self.tariff_row
        if fieldname not in self.tariff_row:
            raise OperationalError(1054, f"Unknown column '{fieldname}' in 'field list'")
        return self.tariff_row[fieldname]

    def test_destination_without_tariff_column_leaves_code_blank(self):
        self.assertIsNone(delivery_note_api.get_HS_code("C100", "Shipping address"))

    def test_configured_destinations_keep_using_their_tariff(self):
        self.tariff_row["au"] = "AU tariff"
        for country, expected in (
            ("Australia", "AU tariff"),
            ("France", "EU tariff"),
            ("United States", "US tariff"),
            ("Switzerland", "CH tariff"),
        ):
            with self.subTest(country=country):
                self.country = country
                self.assertEqual(delivery_note_api.get_HS_code("C100", "Shipping address"), expected)

    def test_missing_tariff_row_leaves_code_blank(self):
        self.tariff_row = None
        self.assertIsNone(delivery_note_api.get_HS_code("C100", "Shipping address"))
