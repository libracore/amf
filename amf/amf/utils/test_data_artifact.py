"""Private data boundaries; run with env/bin/python -m unittest ...test_data_artifact."""

import csv
import hashlib
import io
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import frappe

from amf.amf.doctype.amf_data_artifact.amf_data_artifact import AMFDataArtifact
from amf.amf.report.bom_cost_breakdown import selected_bom_reprice as selected
from amf.amf.utils import data_artifact as artifacts
from amf.amf.utils import item_rate_master as rates
from amf.amf.utils import delivery_note_api as shipping
from amf.patches.v12_0 import migrate_private_data_artifacts_2026_10_26 as migration


class TestPrivateDataArtifacts(unittest.TestCase):
    def setUp(self):
        self.saved = {}
        self.roles = ["System Manager"]
        self.db = MagicMock()
        self.db.exists.side_effect = lambda doctype, name: name in self.saved
        owner = self

        class Doc(frappe._dict):
            def is_new(self):
                return not self.get("name")

            def check_permission(self, permission):
                frappe.only_for("System Manager")

            def insert(self):
                AMFDataArtifact.validate(self)
                self.name = self.artifact_name
                owner.saved[self.name] = dict(self)
                return self

        def get_doc(doctype, name=None):
            if isinstance(doctype, dict):
                return Doc(doctype)
            return Doc(self.saved[name])

        for active in (
            patch.object(frappe, "local", frappe._dict(site="site1.local", flags=frappe._dict(in_test=False))),
            patch.object(frappe, "get_roles", side_effect=lambda: self.roles),
            patch.object(frappe, "get_doc", side_effect=get_doc),
            patch.object(frappe, "db", self.db),
            patch.object(frappe, "reload_doc"),
            patch.object(frappe, "has_permission"),
        ):
            active.start()
            self.addCleanup(active.stop)

    def test_csv_round_trip_keeps_bom_crlf_and_leading_zero_codes(self):
        payload = '\ufeff"000123"\r\n"48E040"\r\n'.encode("utf-8")
        artifacts.put("refs.csv", payload)
        self.assertEqual(artifacts.get_bytes("refs.csv"), payload)
        self.assertEqual(self.saved["refs.csv"]["byte_length"], len(payload))
        self.db.commit.assert_not_called()

    def test_identical_import_can_be_retried_but_different_content_cannot_replace_it(self):
        artifacts.put("refs.csv", "000123\n")
        artifacts.put("refs.csv", "000123\n")
        with self.assertRaisesRegex(ValueError, "different content"):
            artifacts.put("refs.csv", "999999\n")
        self.assertEqual(artifacts.get_bytes("refs.csv"), b"000123\n")

    def test_permission_denied_before_read_or_creation(self):
        self.roles = []
        for operation in (lambda: artifacts.get_bytes("refs.csv"),
                          lambda: artifacts.put("refs.csv", "sensitive"),
                          lambda: artifacts.download("refs.csv")):
            with self.assertRaises(frappe.PermissionError):
                operation()
        frappe.get_doc.assert_not_called()
        self.db.exists.assert_not_called()

    def test_paths_and_header_injection_are_rejected(self):
        for name in ("/docs/refs.csv", "../refs.csv", "public/refs.csv", "a\\refs.csv",
                     "refs.csv\r\nX-Test: yes", "https://host/refs.csv", "a" * 141 + ".csv"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                artifacts.get_bytes(name)
        frappe.get_doc.assert_not_called()

    def test_corrupt_content_and_reviewed_checksum_are_rejected(self):
        artifacts.put("data.json", '{"amount": "1.234567"}\n')
        with self.assertRaisesRegex(ValueError, "Reviewed artifact checksum"):
            artifacts.get_bytes("data.json", "0" * 64)
        self.saved["data.json"]["content"] = '{"amount": "999.000000"}\n'
        with self.assertRaisesRegex(ValueError, "integrity"):
            artifacts.download("data.json")

    def test_bad_utf8_empty_content_invalid_json_and_wrong_import_hash_are_rejected(self):
        for content in (b"\xff", b"", b"x" * (artifacts.MAX_BYTES + 1)):
            with self.assertRaises(ValueError):
                artifacts.put("data.csv", content)
        with self.assertRaises(ValueError):
            artifacts.put("data.json", "not json")
        with self.assertRaisesRegex(ValueError, "Import checksum"):
            artifacts.put("data.csv", "data", "0" * 64)
        self.assertEqual(self.saved, {})

    def test_controller_rejects_edits_to_saved_artifacts(self):
        artifacts.put("data.csv", "sensitive\n")
        doc = frappe.get_doc(artifacts.DOCTYPE, "data.csv")
        doc.content = "replacement\n"
        with self.assertRaisesRegex(frappe.ValidationError, "immutable"):
            AMFDataArtifact.validate(doc)

    def test_partial_csv_is_not_persisted_when_writer_fails(self):
        with self.assertRaises(RuntimeError):
            with artifacts.csv_output("partial.csv") as output:
                output.write("header\n")
                raise RuntimeError("generation failed")
        self.assertNotIn("partial.csv", self.saved)

    def test_download_is_attachment_without_cache_or_public_file(self):
        artifacts.put("private.csv", "sensitive\r\n")
        with patch("builtins.open", side_effect=AssertionError("filesystem access")):
            response = artifacts.download("private.csv")
        self.assertEqual(response.data, b"sensitive\r\n")
        self.assertEqual(response.headers["Cache-Control"], "private, no-store")
        self.assertIn('attachment; filename="private.csv"', response.headers["Content-Disposition"])
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual({doc["doctype"] for doc in self.saved.values()}, {artifacts.DOCTYPE})

    def test_migration_preserves_reviewed_inputs_and_is_retry_safe(self):
        migration.execute()
        self.assertEqual(len(self.saved), 3)
        digest = hashlib.sha256(artifacts.get_bytes(artifacts.SELECTED_PROPOSAL)).hexdigest()
        self.assertEqual(digest, "eacfc6fe2caaec05ef28988ea1ca0c902fa05ae7af90461d0983598093e54b26")
        self.assertEqual(len(selected.selected_refs()), 61)
        self.assertEqual(artifacts.get_json(artifacts.SELECTED_PROPOSAL)["selected_finished_items"],
                         selected.selected_refs())
        original_loader = migration.get_data
        with patch.object(migration, "get_data", wraps=original_loader) as reads:
            migration.execute()
        self.assertEqual([call.args[1] for call in reads.call_args_list],
                         [migration.RESOURCE_ROOT + "manifest.json"])
        self.db.commit.assert_not_called()

    def test_migration_refuses_conflicting_existing_data(self):
        artifacts.put(artifacts.SELECTED_REFS, "unexpected\n")
        with self.assertRaisesRegex(ValueError, "Reviewed artifact checksum"):
            migration.execute()
        self.db.commit.assert_not_called()

    def test_migration_refuses_changed_seed(self):
        original_loader = migration.get_data

        def changed_seed(package, resource):
            return b"unexpected\n" if resource.endswith(artifacts.SELECTED_REFS) else original_loader(package, resource)

        with patch.object(migration, "get_data", side_effect=changed_seed):
            with self.assertRaisesRegex(ValueError, "Import checksum"):
                migration.execute()
        self.assertEqual(self.saved, {})

    def test_migration_stops_if_packaged_inputs_are_missing(self):
        with patch.object(migration, "get_data", side_effect=FileNotFoundError("missing seed")):
            with self.assertRaises(FileNotFoundError):
                migration.execute()
        self.assertEqual(self.saved, {})
        self.db.commit.assert_not_called()

    def test_other_sites_get_schema_without_manufacturing_seed(self):
        frappe.local.site = "other.local"
        with patch.object(migration, "get_data") as reads:
            migration.execute()
        frappe.reload_doc.assert_called_once()
        reads.assert_not_called()

    def test_migration_precedes_repricing_in_patch_list(self):
        patches = (Path(__file__).resolve().parents[2] / "patches.txt").read_text().splitlines()
        prefix = "amf.patches.v12_0."
        self.assertLess(patches.index(prefix + "migrate_private_data_artifacts_2026_10_26"),
                        patches.index(prefix + "reprice_selected_61_boms_2026_10_12"))

    def test_selector_and_apply_read_database_without_filesystem_access(self):
        migration.execute()
        with patch("builtins.open", side_effect=AssertionError("filesystem access")):
            self.assertEqual(len(selected.selected_refs()), 61)
            # A changed calculation must stop before any BOM write.
            with patch.object(selected, "scoped_plan", return_value=(["CHANGED"], [])), \
                    patch.object(selected, "_outside_current_parents", return_value=[]), \
                    patch.object(selected.material_reprice, "_apply_entry") as write:
                with self.assertRaisesRegex(ValueError, "differs from current"):
                    selected.apply_scoped_proposal(commit=False)
                write.assert_not_called()
        self.db.commit.assert_not_called()

    def test_selector_rejects_scientific_notation_duplicates_and_extra_columns(self):
        valid = ["{:06d}".format(i) for i in range(61)]
        for rows in ([valid[0]] * 61, valid[:-1], valid[:-1] + ["4.8E+05"],
                     valid[:-1] + ["123456,extra"]):
            with patch.object(artifacts, "get_bytes", return_value=("\n".join(rows) + "\n").encode()):
                with self.assertRaises(ValueError):
                    selected.selected_refs()

    def test_invoice_type_allowlist_stops_sql_injection(self):
        with self.assertRaises(ValueError):
            rates.export_item_rates_to_csv(invoice_doctype="Sales Invoice` JOIN tabUser --")
        self.db.sql.assert_not_called()

    def test_invoice_export_requires_admin_before_query(self):
        self.roles = []
        for exporter in (rates.export_item_rates_to_csv, rates.export_item_last_rate_csv,
                         rates.export_item_last_rate_single_customer_csv):
            with self.assertRaises(frappe.PermissionError):
                exporter()
        self.db.sql.assert_not_called()

    def export_rows(self, exporter, rows, **kwargs):
        self.db.sql.return_value = [frappe._dict(row) for row in rows]
        with patch("builtins.open", side_effect=AssertionError("filesystem access")):
            url = exporter(**kwargs)
        self.assertTrue(url.startswith("/api/method/amf.amf.utils.data_artifact.download?name="))
        return list(csv.reader(io.StringIO(artifacts.get_bytes(url.split("name=")[1]).decode())))

    def test_latest_rates_are_grouped_by_currency_without_public_files(self):
        rows = [dict(item_code="000123", currency="CHF", rate=10, party="A"),
                dict(item_code="000123", currency="EUR", rate=20, party="A"),
                dict(item_code="000123", currency="CHF", rate=5, party="A")]
        output = self.export_rows(rates.export_item_last_rate_csv, rows)
        self.assertEqual(output[0], ["Item Code", "Currency", "Average", "Rate 1"])
        self.assertEqual(output[1:], [["000123", "CHF", "10.00", "10.00"],
                                      ["000123", "EUR", "20.00", "20.00"]])
        self.db.commit.assert_not_called()

    def test_single_customer_uses_entire_history_but_emits_latest_rate(self):
        rows = [dict(item_code="ONE", currency="CHF", rate=10, party="A"),
                dict(item_code="ONE", currency="CHF", rate=5, party="A"),
                dict(item_code="TWO", currency="CHF", rate=20, party="A"),
                dict(item_code="TWO", currency="CHF", rate=30, party="B")]
        output = self.export_rows(rates.export_item_last_rate_single_customer_csv, rows)
        self.assertEqual(output[1:], [["ONE", "CHF", "10.00", "10.00"]])

    def test_average_export_uses_all_rates_and_escapes_spreadsheet_formulas(self):
        rows = [dict(item_code="=FORMULA()", currency="CHF", rate=10, party="A"),
                dict(item_code="=FORMULA()", currency="CHF", rate=20, party="A")]
        output = self.export_rows(rates.export_item_rates_to_csv, rows, submitted_only="0",
                                  company_currency="CHF")
        self.assertEqual(output[1], ["'=FORMULA()", "CHF", "15.00", "10.00", "20.00"])
        query, params = self.db.sql.call_args.args
        self.assertIn("line.base_rate AS rate", query)
        self.assertNotIn("invoice.docstatus = 1", query)
        self.assertEqual(params, ("CHF",))
        frappe.has_permission.assert_called_with("Sales Invoice", "read", throw=True)

    def test_shipping_export_checks_delivery_note_permission_before_reading_lines(self):
        note = MagicMock()
        note.check_permission.side_effect = frappe.PermissionError
        with patch.object(frappe, "get_doc", return_value=note) as loader:
            with self.assertRaises(frappe.PermissionError):
                shipping.generate_dhl("DN-1")
        note.check_permission.assert_called_once_with("write")
        loader.assert_called_once_with("Delivery Note", "DN-1")

    def test_shipping_attachment_is_private_without_intermediate_file(self):
        note, attachment = MagicMock(), MagicMock()
        note.currency = "CHF"
        note.items = [frappe._dict(item_name="Part", item_code="000123", qty=2,
            net_rate=10, weight_per_unit=0.1, customs_tariff_number_="1234.5678",
            country_of_origin="Switzerland")]
        with patch.object(frappe, "get_doc", side_effect=[note, attachment]) as loader, \
                patch("builtins.open", side_effect=AssertionError("intermediate file")):
            result = shipping.generate_dhl("DN-1")
        data = loader.call_args.args[0]
        self.assertEqual(data["doctype"], "File")
        self.assertEqual(data["is_private"], 1)
        self.assertEqual(data["attached_to_name"], "DN-1")
        self.assertEqual(data["content"], result["data"])
        attachment.insert.assert_called_once()


if __name__ == "__main__":
    unittest.main()
