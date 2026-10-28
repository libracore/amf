import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

import frappe

from amf.patches.v12_0 import create_acoustic_mixer_items_2026_10_28 as migration


class TestAcousticMixerMigration(unittest.TestCase):
    def test_allocations_include_scrap_credit_and_current_component_costs(self):
        # LV: 454.0213 materials less the source BOM's CHF 1 recovery credit.
        self.assertEqual(migration._allocation(454.0213 - 1), Decimal('2046.9787'))
        # HV: current valuation of the 5 mL syringe, rather than its older rate.
        self.assertEqual(migration._allocation(457.5114), Decimal('2042.4886'))
        for base in (2500, 2501):
            with self.subTest(base=base), self.assertRaises(frappe.ValidationError):
                migration._allocation(base)

    def test_matching_existing_products_are_a_write_free_replay(self):
        db = SimpleNamespace(exists=Mock(return_value=True),
                             get_default=Mock(return_value='Item Code'),
                             commit=Mock(), rollback=Mock())
        plans = [frappe._dict(cost=object(), item=object(), existing_bom=True)
                 for unused in migration.SPECS]
        with patch.object(migration.frappe, 'db', db), \
                patch.object(migration.frappe, 'set_user'), \
                patch.object(migration, '_plan', side_effect=plans), \
                patch.object(migration, '_new_cost_item') as create_cost, \
                patch.object(migration, '_copy_item') as create_item:
            self.assertEqual(migration.execute(), dict(items=0, boms=0))
        create_cost.assert_not_called()
        create_item.assert_not_called()
        db.commit.assert_not_called()

    def test_second_product_conflict_is_detected_before_any_insert(self):
        db = SimpleNamespace(exists=Mock(return_value=True),
                             get_default=Mock(return_value='Item Code'))
        with patch.object(migration.frappe, 'db', db), \
                patch.object(migration.frappe, 'set_user'), \
                patch.object(migration, '_plan', side_effect=[object(), frappe.ValidationError('collision')]), \
                patch.object(migration, '_new_cost_item') as create_cost, \
                patch.object(migration, '_copy_item') as create_item:
            with self.assertRaises(frappe.ValidationError):
                migration.execute()
        create_cost.assert_not_called()
        create_item.assert_not_called()

    def test_foreign_reference_owner_is_rejected(self):
        source = SimpleNamespace(name='45D040', item_name='SPM', item_group='Product', disabled=0)
        bom = SimpleNamespace(item='45D040', docstatus=1, is_active=1, quantity=1,
                              currency='CHF', rm_cost_as_per='Valuation Rate')
        db = SimpleNamespace(get_value=Mock(return_value='UNRELATED-ITEM'))
        with patch.object(migration.frappe, 'db', db), \
                patch.object(migration.frappe, 'get_doc', side_effect=[source, bom]):
            with self.assertRaisesRegex(frappe.ValidationError, 'reference collision'):
                migration._plan(frappe._dict(migration.SPECS[0]))

    def test_new_items_have_no_stock_or_price_side_effects(self):
        plan = frappe._dict(migration.SPECS[0])
        plan.item_name = 'SPM - Acoustic Mixer'
        plan.source_bom_doc = SimpleNamespace(company='Advanced Microfluidics SA')
        plan.allocation, plan.base_cost = Decimal('2046.9787'), Decimal('453.0213')
        with patch.object(migration.frappe, 'get_doc', side_effect=lambda values: values):
            cost = migration._new_cost_item(plan)
        self.assertEqual(cost['is_stock_item'], 0)
        self.assertEqual(cost['include_item_in_manufacturing'], 0)
        self.assertEqual(cost['standard_rate'], 0)
        self.assertEqual(cost['valuation_rate'], 2046.9787)
        self.assertNotIn('opening_stock', cost)

    def test_legacy_hooks_cannot_replace_reviewed_child_bom_revisions(self):
        from amf.amf.utils import bom_child_bom_resolver

        rows = [SimpleNamespace(idx=1, bom_no='BOM-551000-018'),
                SimpleNamespace(idx=2, bom_no=None)]
        doc = SimpleNamespace(items=rows, flags=frappe._dict(
            acoustic_mixer_child_boms={1: 'BOM-551000-018', 2: None}))
        def change_defaults(doc, method=None):
            for row in doc.items:
                row.bom_no = 'NEWER-DEFAULT'
        commit, rollback = Mock(), Mock()
        db = SimpleNamespace(commit=commit, rollback=rollback)
        with patch.object(migration.frappe, 'db', db), \
                patch.object(bom_child_bom_resolver, 'apply_item_default_boms_to_rows', change_defaults):
            with migration._preserve_transaction_and_revisions():
                db.commit()
                bom_child_bom_resolver.apply_item_default_boms_to_rows(doc)
            self.assertIs(db.commit, commit)
            self.assertIs(db.rollback, rollback)
            self.assertIs(bom_child_bom_resolver.apply_item_default_boms_to_rows, change_defaults)
        self.assertEqual([r.bom_no for r in rows], ['BOM-551000-018', None])
        commit.assert_not_called()

    def test_swallowed_hook_failure_reaches_the_patch_runner(self):
        commit, rollback = Mock(), Mock()
        db = SimpleNamespace(commit=commit, rollback=rollback)
        with patch.object(migration.frappe, 'db', db):
            with self.assertRaises(frappe.ValidationError):
                with migration._preserve_transaction_and_revisions():
                    try:
                        db.rollback()
                    except Exception:
                        self.fail('A legacy hook swallowed the failure')
            self.assertIs(db.commit, commit)
            self.assertIs(db.rollback, rollback)
        rollback.assert_not_called()

    def test_project_code_exception_is_scoped_and_normal_family_guard_is_restored(self):
        from amf.amf.utils import item_code_family

        plan = frappe._dict(target='45D040-AM', reference='REF-AM', item_name='SPM - Acoustic Mixer')
        project = frappe._dict(item_code=plan.target, reference_code=plan.reference,
                               item_name=plan.item_name, item_group='Product')
        normal = frappe._dict(item_code='45D041-AM', item_group='Product')
        validator = Mock()
        db = SimpleNamespace(commit=Mock(), rollback=Mock())
        with patch.object(migration.frappe, 'db', db), \
                patch.object(item_code_family, 'validate_new_item_family', validator):
            with migration._preserve_transaction_and_revisions([plan]):
                item_code_family.validate_new_item_family(project)
                validator.assert_not_called()
                item_code_family.validate_new_item_family(normal)
                validator.assert_called_once_with(normal, None)
                project.reference_code = 'WRONG-REFERENCE'
                with self.assertRaises(frappe.ValidationError):
                    item_code_family.validate_new_item_family(project)
            self.assertIs(item_code_family.validate_new_item_family, validator)


if __name__ == '__main__':
    unittest.main()
