# -*- coding: utf-8 -*-
# Copyright (c) 2024, libracore AG and Contributors
# See license.txt
from __future__ import unicode_literals

import unittest
from unittest.mock import patch

from frappe import _dict
from amf.amf.doctype.planning.planning import (
    build_planning_costing_row,
    calculate_planning_cost,
    calculate_planning_total_cost,
    calculate_planning_cost_per_part,
    sync_planning_costing_after_batch_assignment,
)


class TestPlanning(unittest.TestCase):
    def test_calculate_planning_process_cost_includes_cycle_and_fixed_time(self):
        self.assertEqual(
            calculate_planning_cost(
                quantite_validee=10,
                quantite_scrap=2,
                temps_de_cycle_min=3.5,
                temps_de_reglage_hr=1.25,
                temps_de_programmation_hr=0.75,
            ),
            202.5,
        )

    def test_calculate_planning_total_cost_adds_raw_material_cost(self):
        self.assertEqual(
            calculate_planning_total_cost(
                process_cost=202.5,
                raw_material_cost=288.6,
            ),
            491.1,
        )

    def test_calculate_planning_cost_per_part_uses_validated_qty(self):
        self.assertEqual(
            calculate_planning_cost_per_part(
                total_cost=491.1,
                quantite_validee=10,
            ),
            49.11,
        )

    def test_build_planning_costing_row_requires_batch(self):
        self.assertIsNone(build_planning_costing_row({
            'batch': '',
            'batch_matiere': 'RAW-BATCH-001',
            'used_qty': 0.3,
            'quantite_validee': 10,
            'quantite_scrap': 2,
            'temps_de_cycle_min': 3.5,
            'temps_de_reglage_hr': 1.25,
            'temps_de_programmation_hr': 0.75,
        }, raw_material_costing={
            'raw_material_prec': 'PREC-02519',
            'raw_material_cost_per_meter': 962.001813,
            'raw_material_cost': 288.6,
        }))

    def test_build_planning_costing_row_maps_batch_material_and_totals(self):
        row = build_planning_costing_row({
            'batch': 'BATCH-001',
            'batch_matiere': 'RAW-BATCH-001',
            'used_qty': 0.3,
            'quantite_validee': 10,
            'quantite_scrap': 2,
            'temps_de_cycle_min': 3.5,
            'temps_de_reglage_hr': 1.25,
            'temps_de_programmation_hr': 0.75,
        }, raw_material_costing={
            'raw_material_prec': 'PREC-02519',
            'raw_material_cost_per_meter': 962.001813,
            'raw_material_cost': 288.6,
        })

        self.assertEqual(row['batch_no'], 'BATCH-001')
        self.assertEqual(row['raw_material_prec'], 'PREC-02519')
        self.assertEqual(row['raw_material_cost_per_meter'], 962.001813)
        self.assertEqual(row['raw_material_cost'], 288.6)
        self.assertEqual(row['total_cost'], 491.1)
        self.assertEqual(row['cost_per_part'], 49.11)

    def test_sync_planning_costing_after_batch_assignment_updates_batch_dependent_outputs(self):
        doc = _dict({
            'name': 'PLAN-0001',
            'batch': '',
        })
        costing_row = {
            'batch_no': 'BATCH-001',
            'cost_per_part': 49.11,
        }

        with patch(
            'amf.amf.doctype.planning.planning.build_planning_costing_row',
            return_value=costing_row,
        ) as build_costing_row, patch(
            'amf.amf.doctype.planning.planning.persist_planning_costing_table'
        ) as persist_costing_table, patch(
            'amf.amf.doctype.planning.planning.sync_planning_batch_cost_per_part'
        ) as sync_batch_cost:
            sync_planning_costing_after_batch_assignment(doc, batch_no='BATCH-001')

        self.assertEqual(doc.batch, 'BATCH-001')
        build_costing_row.assert_called_once_with(doc)
        persist_costing_table.assert_called_once_with(doc, costing_row=costing_row)
        sync_batch_cost.assert_called_once_with(doc, costing_row=costing_row)
