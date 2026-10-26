import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from time import sleep
from unittest.mock import Mock, patch

import frappe
from frappe.utils import flt

from amf import hooks
from amf.amf.utils import purchase_receipt_gl_override as override
from erpnext.accounts.general_ledger import process_gl_map, round_off_debit_credit
from erpnext.stock.doctype.purchase_receipt.purchase_receipt import PurchaseReceipt


class Receipt(frappe._dict):
    def get_company_default(self, field):
        return {
            'expenses_included_in_valuation': '4405 - Landed freight',
            'stock_received_but_not_billed': '2210 - Received not billed',
        }[field]


def entry(account, debit=0, credit=0, project=None):
    return frappe._dict(account=account, debit=debit, credit=credit,
        debit_in_account_currency=debit, credit_in_account_currency=credit,
        project=project, company='AMF', voucher_type='Purchase Receipt')


class TestPurchaseReceiptGLOverride(unittest.TestCase):
    def setUp(self):
        self.doc = Receipt(company='AMF', is_return=0, items=[], taxes=[])
        self.precision = self.enter_patch(patch.object(override, 'get_field_precision', return_value=2))
        self.enter_patch(patch.object(frappe, 'get_meta', return_value=Mock()))
        self.enter_patch(patch.object(frappe, 'get_cached_value', return_value='CHF'))
        self.enter_patch(patch.object(frappe, 'get_system_settings', return_value="Banker's Rounding (legacy)"))
        self.enter_patch(patch('erpnext.accounts.general_ledger.get_accounting_dimensions', return_value=[]))

    def enter_patch(self, patcher):
        value = patcher.start()
        self.addCleanup(patcher.stop)
        return value

    def run_override(self, entries, accounts=None):
        original = self.enter_patch(patch.object(Receipt, override.ORIGINAL_METHOD,
            Mock(return_value=entries), create=True))
        if accounts is None:
            accounts = {'warehouse': 'stock account'}
        result = override._get_gl_entries_with_amf_plain_return_guard(self.doc, accounts)
        original.assert_called_once_with(self.doc, accounts)
        return result

    def test_normal_subcontract_receipt_sub_cent_project_adjustment(self):
        # PREC-03061: the project separates the tiny loss from the main RBNB row.
        entries = [
            entry('1210 - Stock', debit=2167.25),
            entry('2210 - Received not billed', credit=2045.9033),
            entry('1213 - External stock', credit=121.35),
            entry('2210 - Received not billed', debit=0.0033, project='IRIS Manifold'),
        ]
        result = self.run_override(entries)
        self.assertEqual(result, entries[:3])
        self.assertEqual(result[1].credit, 2045.9033)
        self.assertAlmostEqual(sum(flt(row.debit, 2) - flt(row.credit, 2) for row in result), 0)

    def test_normal_receipt_does_not_run_return_account_reclassification(self):
        entries = [entry('4405 - Landed freight', credit=12.34), entry('stock', debit=12.34)]
        with patch.object(override, '_has_valuation_charges') as has_charges, \
                patch.object(override, '_move_valuation_expense_entries_to_rbnb') as move:
            self.assertEqual(self.run_override(entries), entries)
        has_charges.assert_not_called()
        move.assert_not_called()

    def test_filters_small_debits_and_credits_but_keeps_postable_amounts(self):
        entries = [entry('tiny debit', debit=0.0049), entry('tiny credit', credit=0.0049),
            entry('zero'), entry('real debit', debit=0.01), entry('real credit', credit=0.01)]
        self.assertEqual(self.run_override(entries), entries[-2:])

    def test_uses_company_currency_precision(self):
        self.precision.return_value = 3
        entries = [entry('stock', debit=0.0033), entry('rbnb', credit=0.0033),
            entry('tiny', debit=0.0003)]
        self.assertEqual(self.run_override(entries), entries[:2])
        self.assertEqual(self.precision.call_args.kwargs['currency'], 'CHF')

    def test_plain_return_keeps_rbnb_reclassification_and_filters_after_merge(self):
        self.doc.is_return = 1
        entries = [entry('stock', credit=10), entry('2210 - Received not billed', debit=10.0033),
            entry('4405 - Landed freight', credit=0.0033)]
        with patch.object(override, '_has_linked_landed_cost_voucher', return_value=False):
            result = self.run_override(entries)
        self.assertEqual([row.account for row in result], ['stock', '2210 - Received not billed'])
        self.assertAlmostEqual(result[1].debit, 10.0033)
        self.assertAlmostEqual(result[1].credit, 0.0033)

    def test_return_with_landed_cost_keeps_valuation_account(self):
        self.doc.is_return = 1
        self.doc.items = [frappe._dict(landed_cost_voucher_amount=5)]
        entries = [entry('stock', credit=15), entry('2210 - Received not billed', debit=10),
            entry('4405 - Landed freight', debit=5), entry('tiny', debit=0.0033)]
        with patch.object(override, '_has_linked_landed_cost_voucher', return_value=False):
            result = self.run_override(entries)
        self.assertEqual(result, entries[:3])

    def test_return_with_valuation_tax_keeps_valuation_account(self):
        self.doc.is_return = 1
        self.doc.taxes = [frappe._dict(category='Valuation', base_tax_amount_after_discount_amount=5)]
        entries = [entry('stock', credit=15), entry('2210 - Received not billed', debit=10),
            entry('4405 - Landed freight', debit=5)]
        with patch.object(override, '_has_linked_landed_cost_voucher', return_value=False):
            self.assertEqual(self.run_override(entries), entries)

    def test_empty_map(self):
        self.assertEqual(self.run_override([]), [])
        self.precision.assert_not_called()

    def test_rounding_boundaries_follow_system_rounding_method(self):
        for method in ("Banker's Rounding (legacy)", "Banker's Rounding", 'Commercial Rounding'):
            with self.subTest(rounding_method=method), \
                    patch.object(frappe, 'get_system_settings', return_value=method):
                entries = [entry('below', debit=0.0049), entry('above debit', debit=0.0051),
                    entry('above credit', credit=0.0051), entry('tie', debit=0.005)]
                result = self.run_override(entries)
                expected = entries[1:3] + ([entries[3]] if flt(0.005, 2) else [])
                self.assertEqual(result, expected)

    def test_zero_decimal_currency_drops_fraction_but_keeps_whole_units(self):
        self.precision.return_value = 0
        with patch.object(frappe, 'get_cached_value', return_value='JPY'):
            entries = [entry('tiny', debit=0.49), entry('debit', debit=1), entry('credit', credit=1)]
            self.assertEqual(self.run_override(entries), entries[1:])
        self.assertEqual(self.precision.call_args.kwargs['currency'], 'JPY')

    def test_company_precision_is_not_reused_between_receipts(self):
        entries = [entry('stock', debit=0.0033), entry('rbnb', credit=0.0033)]
        self.assertEqual(override._without_zero_value_gl_entries(self.doc, entries), [])
        self.precision.return_value = 3
        self.doc.company = 'Three decimal company'
        self.assertEqual(override._without_zero_value_gl_entries(self.doc, entries), entries)
        self.assertEqual(self.precision.call_count, 2)

    def test_foreign_currency_does_not_override_company_gl_precision(self):
        entries = [entry('stock', debit=10), entry('rbnb', credit=10), entry('tiny', debit=0.0033)]
        for row in entries:
            row.account_currency = 'EUR'
            row.debit_in_account_currency = row.debit / 0.9439
            row.credit_in_account_currency = row.credit / 0.9439
        self.assertEqual(self.run_override(entries), entries[:2])
        self.assertEqual(entries[1].credit_in_account_currency, 10 / 0.9439)

    def test_merge_preserves_sub_cent_components_with_postable_total(self):
        entries = process_gl_map([entry('stock', debit=0.0033), entry('stock', debit=0.0033),
            entry('rbnb', credit=0.0066)])
        result = self.run_override(entries)
        self.assertEqual(len(result), 2)
        self.assertAlmostEqual(result[0].debit, 0.0066)
        # Follow the actual downstream posting pipeline.
        with patch('erpnext.accounts.general_ledger.get_field_precision', return_value=2):
            round_off_debit_credit(process_gl_map(result))
        self.assertEqual([(row.debit, row.credit) for row in result], [(0.01, 0), (0, 0.01)])

    def test_normalized_negative_amounts_are_filtered_at_gl_precision(self):
        entries = process_gl_map([entry('stock', debit=-10), entry('rbnb', credit=-10),
            entry('tiny', debit=-0.0033)])
        result = self.run_override(entries)
        self.assertEqual([(row.debit, row.credit) for row in result], [(0, 10), (10, 0)])

    def test_omitted_warehouse_map_uses_document_company(self):
        entries = [entry('stock', debit=10), entry('rbnb', credit=10)]
        original = self.enter_patch(patch.object(Receipt, override.ORIGINAL_METHOD,
            Mock(return_value=entries), create=True))
        accounts = {'company warehouse': 'company stock account'}
        with patch('erpnext.stock.get_warehouse_account_map', return_value=accounts) as get_accounts:
            self.assertEqual(override._get_gl_entries_with_amf_plain_return_guard(self.doc), entries)
        get_accounts.assert_called_once_with(self.doc.company)
        original.assert_called_once_with(self.doc, accounts)

    def test_explicit_empty_warehouse_map_is_preserved(self):
        with patch('erpnext.stock.get_warehouse_account_map') as get_accounts:
            self.assertEqual(self.run_override([], accounts={}), [])
        get_accounts.assert_not_called()

    def test_return_with_linked_landed_cost_keeps_valuation_account(self):
        self.doc.is_return = '1'
        entries = [entry('stock', credit=15), entry('2210 - Received not billed', debit=10),
            entry('4405 - Landed freight', debit=5), entry('tiny', debit=0.0033)]
        with patch.object(override, '_has_linked_landed_cost_voucher', return_value=True):
            self.assertEqual(self.run_override(entries), entries[:3])

    def test_original_posting_validation_errors_propagate(self):
        self.enter_patch(patch.object(Receipt, override.ORIGINAL_METHOD,
            Mock(side_effect=frappe.ValidationError('Invalid accounting configuration')), create=True))
        with self.assertRaisesRegex(frappe.ValidationError, 'Invalid accounting configuration'):
            override._get_gl_entries_with_amf_plain_return_guard(self.doc, {})

    def test_filter_preserves_document_dimensions_and_entry_identity(self):
        row = entry('stock', debit=10, project='IRIS Manifold')
        row.update({'cost_center': 'Production', 'custom_dimension': 'Dimension A',
            'voucher_no': 'PREC-TEST'})
        initial = dict(row)
        result = self.run_override([row])
        self.assertIs(result[0], row)
        self.assertEqual(result[0], initial)


class TestPurchaseReceiptGLInstallation(unittest.TestCase):
    def test_concurrent_installation_saves_original_exactly_once(self):
        saves = []
        original = Mock()

        class SlowInstall(type):
            def __setattr__(cls, name, value):
                if name == override.ORIGINAL_METHOD:
                    saves.append(value)
                    # Expose the race window before the installed flag is set.
                    sleep(0.01)
                super(SlowInstall, cls).__setattr__(name, value)

        class Controller(metaclass=SlowInstall):
            get_gl_entries = original

        barrier = Barrier(8)

        def install():
            barrier.wait(timeout=5)
            override.install_purchase_receipt_gl_override()

        with patch('erpnext.stock.doctype.purchase_receipt.purchase_receipt.PurchaseReceipt', Controller):
            with ThreadPoolExecutor(max_workers=8) as executor:
                list(executor.map(lambda _: install(), range(8)))
        self.assertEqual(saves, [original])
        self.assertIs(getattr(Controller, override.ORIGINAL_METHOD), original)
        self.assertIs(Controller.get_gl_entries, override._get_gl_entries_with_amf_plain_return_guard)

    def test_installation_is_idempotent_and_keeps_original_method(self):
        original = Mock()
        with patch.object(PurchaseReceipt, override.PATCHED_FLAG, False, create=True), \
                patch.object(PurchaseReceipt, override.ORIGINAL_METHOD, None, create=True), \
                patch.object(PurchaseReceipt, 'get_gl_entries', original):
            override.install_purchase_receipt_gl_override()
            override.install_purchase_receipt_gl_override()
            self.assertIs(getattr(PurchaseReceipt, override.ORIGINAL_METHOD), original)
            self.assertIs(PurchaseReceipt.get_gl_entries,
                override._get_gl_entries_with_amf_plain_return_guard)
            self.assertTrue(getattr(PurchaseReceipt, override.PATCHED_FLAG))

    def test_receipt_and_stock_ledger_hooks_cover_submission_and_reposting(self):
        path = 'amf.amf.utils.purchase_receipt_gl_override.install_purchase_receipt_gl_override'
        self.assertIn(path, hooks.doc_events['Purchase Receipt']['before_submit'])
        self.assertEqual(hooks.doc_events['Stock Ledger Entry']['before_validate'], path)

    def test_hook_accepts_stock_ledger_document_and_method(self):
        original = Mock()
        with patch.object(PurchaseReceipt, override.PATCHED_FLAG, False, create=True), \
                patch.object(PurchaseReceipt, override.ORIGINAL_METHOD, None, create=True), \
                patch.object(PurchaseReceipt, 'get_gl_entries', original):
            override.install_purchase_receipt_gl_override(frappe._dict(doctype='Stock Ledger Entry'),
                'before_validate')
            self.assertIs(getattr(PurchaseReceipt, override.ORIGINAL_METHOD), original)


if __name__ == '__main__':
    unittest.main()
