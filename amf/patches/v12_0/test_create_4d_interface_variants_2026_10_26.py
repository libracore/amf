import copy
import datetime
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import frappe

from amf.patches.v12_0 import create_4d_interface_variants_2026_10_26 as migration


class Document(SimpleNamespace):
    def get(self, key, default=None):
        return getattr(self, key, default)

    def set(self, key, value):
        setattr(self, key, value)


class Test4DInterfaceMigration(unittest.TestCase):
    def test_scope_preserves_hexadecimal_suffix_and_six_pending_boms(self):
        targets, pending = set(), set()
        for code in migration.SOURCE_CODES:
            source = Document(name=code, item_name='Valve', reference_code='REF-' + code)
            for prefix, interface, body in migration.VARIANTS:
                spec = migration._spec(source, Document(name='BOM-' + code + '-002'),
                                       prefix, interface, body)
                targets.add(spec.target)
                if spec.pending:
                    pending.add(spec.target)
        self.assertEqual(len(targets), 74)
        self.assertIn('4D104D', targets)
        self.assertIn('4D204D', targets)
        self.assertEqual(pending, {'4D1058', '4D2058', '4D1062', '4D2062', '4D1068', '4D2068'})
        self.assertNotIn('4D1069-P', targets)

    def test_pending_description_does_not_claim_a_submitted_variant_bom(self):
        source = Document(name='4D0058', item_name='Valve', reference_code='REF58',
            internal_description='4D0058 / Valve / REF58 / Default active submitted BOM / BOM-4D0058-001 / 5D1000')
        spec = migration._spec(source, Document(name='BOM-4D0058-001'), '4D2', 'CAN', '5D1002')
        text = migration._description(source, spec, 'internal_description')
        self.assertIn('4D2058 / Valve/CAN / REF58/CAN', text)
        self.assertIn('Pending (source BOM: BOM-4D0058-001)', text)
        self.assertIn('300058', text)
        self.assertNotIn('BOM-4D2058-001', text)
        self.assertNotIn('Default active submitted BOM', text)
        self.assertIn('Communication interface:', text)

    def test_legacy_null_defaults_are_not_replaced_by_new_record_defaults(self):
        source = Document(valid_from=None, min_qty=0, meta=Document(fields=[
            Document(fieldname='valid_from', default='Today'),
            Document(fieldname='min_qty', default='1')]))
        with patch.object(migration.frappe, 'copy_doc', side_effect=lambda doc, **kwargs: copy.deepcopy(doc)):
            cloned = migration._copy_without_new_defaults(source)
        self.assertEqual(cloned.valid_from, '')
        self.assertEqual(cloned.min_qty, 0)
        self.assertIsNone(source.valid_from)

    def test_new_item_has_variant_identity_and_no_source_bom_or_qr(self):
        source = Document(name='4D0005', item_name='Valve', reference_code='REF5', naming_series=None,
            description='<div>Product reference: 4D0005</div>',
            default_bom='BOM-4D0005-001', item_default_bom='BOM-4D0005-001',
            bom_table=['old-body'], item_batch_costing=['old-batch'], bom_cost=149,
            qrcode='/private/files/4D0005_qr.png', route='original', image='shared.png')
        cloned = copy.deepcopy(source)

        def insert():
            cloned.name = cloned.item_code

        cloned.insert = insert
        spec = migration._spec(source, Document(name=source.default_bom), '4D1', 'RS485', '5D1001')
        db = Document(get_single_value=Mock(return_value=True))
        with patch.object(migration.frappe, 'db', db), \
                patch.object(migration, '_copy_without_new_defaults', return_value=cloned):
            item = migration._copy_item(source, spec)
        self.assertEqual((item.name, item.item_name, item.reference_code), ('4D1005', 'Valve/RS485', 'REF5/RS485'))
        self.assertIn('4D1005', item.description)
        self.assertIn('RS485', item.description)
        self.assertIsNone(item.default_bom)
        self.assertIsNone(item.item_default_bom)
        self.assertIsNone(item.qrcode)
        self.assertEqual(item.bom_table, [])
        self.assertEqual(item.item_batch_costing, [])
        self.assertEqual(item.image, source.image)
        self.assertEqual(source.bom_table, ['old-body'])

    def test_price_replay_preserves_existing_rate_and_deduplicates_business_keys(self):
        saved = [dict(price_list='CHF', valid_from=datetime.date(2026, 1, 1),
                      customer=None, min_qty=0, price_list_rate=1750)]
        original = Document(price_list='CHF', valid_from='2026-01-01',
                            customer='', min_qty=None, price_list_rate=1650)
        customer_price = Document(price_list='CHF', valid_from='2026-01-01',
                                  customer='CUSTOMER-1', min_qty=0, price_list_rate=1500)

        def clone(source):
            doc = copy.deepcopy(source)
            doc.insert = lambda: saved.append({k: v for k, v in vars(doc).items() if k != 'insert'})
            return doc

        def existing(*args, **kwargs):
            return [frappe._dict(row) for row in saved]

        with patch.object(migration.frappe, 'get_all', side_effect=existing), \
                patch.object(migration, '_copy_without_new_defaults', side_effect=clone):
            self.assertEqual(migration._copy_missing_prices([original, customer_price, customer_price], '4D1005'), 1)
            self.assertEqual(migration._copy_missing_prices([original, customer_price], '4D1005'), 0)
        self.assertEqual(saved[0]['price_list_rate'], 1750)
        self.assertEqual(saved[1]['item_code'], '4D1005')

    def test_body_replacement_clears_old_body_bom_and_keeps_head_revision(self):
        from amf.amf.utils import bom_child_bom_resolver

        for prefix, interface, body_code in migration.VARIANTS:
            with self.subTest(interface=interface):
                source = Document(name='BOM-4D0005-001', items=[
                    Document(idx=1, item_code='5D1000', bom_no='BOM-5D1000-001', qty=1),
                    Document(idx=2, item_code='300005', bom_no='BOM-300005-010', qty=1),
                    Document(idx=3, item_code='RVM.3002', bom_no=None, qty=2)])
                target = prefix + '005'
                item = Document(name=target, item_name='Valve/' + interface, description='Interface ' + interface)
                spec = migration._spec(Document(name='4D0005', item_name='Valve', reference_code=None),
                                       source, prefix, interface, body_code)
                body = Document(name=body_code, item_name='RVM mini ' + interface,
                    default_bom=None, image=None, stock_uom='Nos', include_item_in_manufacturing=1)
                bom = copy.deepcopy(source)
                bom.flags = frappe._dict()

                def insert():
                    bom_child_bom_resolver.apply_item_default_boms_to_rows(bom)
                    bom.name = spec.target_bom

                bom.insert, bom.submit = insert, Mock()
                db = Document(exists=Mock(return_value=False), commit=Mock(), rollback=Mock())

                def resolve_latest(doc, method=None):
                    for row in doc.items:
                        row.bom_no = 'LATEST-DEFAULT'

                with patch.object(migration.frappe, 'db', db), \
                        patch.object(migration.frappe, 'get_doc', side_effect=lambda doctype, code: body if code == body_code else item), \
                        patch.object(migration, '_copy_without_new_defaults', return_value=bom), \
                        patch.object(migration, '_check_existing_bom'), \
                        patch.object(bom_child_bom_resolver, 'apply_item_default_boms_to_rows', resolve_latest):
                    with migration._preserve_transaction_and_revisions():
                        migration._copy_bom(source, item, spec)
                self.assertEqual([row.item_code for row in bom.items], [body_code, '300005', 'RVM.3002'])
                self.assertEqual([row.bom_no for row in bom.items], [None, 'BOM-300005-010', None])
                self.assertEqual([row.qty for row in bom.items], [1, 1, 2])
                self.assertEqual(source.items[0].item_code, '5D1000')
                bom.submit.assert_called_once()
                db.commit.assert_not_called()

    def test_hook_failure_restores_transaction_methods_and_reaches_patch_runner(self):
        from amf.amf.utils import bom_child_bom_resolver

        commit, rollback = Mock(), Mock()
        resolver = bom_child_bom_resolver.apply_item_default_boms_to_rows
        db = Document(commit=commit, rollback=rollback)
        with patch.object(migration.frappe, 'db', db):
            with self.assertRaises(frappe.ValidationError):
                with migration._preserve_transaction_and_revisions():
                    db.commit()
                    db.rollback()
            self.assertIs(db.commit, commit)
            self.assertIs(db.rollback, rollback)
        self.assertIs(bom_child_bom_resolver.apply_item_default_boms_to_rows, resolver)
        commit.assert_not_called()
        rollback.assert_not_called()


if __name__ == '__main__':
    unittest.main()
