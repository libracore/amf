# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import unittest
from unittest.mock import patch

from amf.amf.utils.openai_credentials import (
    get_openai_api_key,
    store_openai_api_key,
)
from amf.amf.utils.operations_ai_insights import (
    AIConfigurationError,
    build_ai_payload,
    flatten_leaf_values,
    generate_ai_insights,
    normalize_evidence_path,
    resolve_evidence_path,
    validate_ai_output,
)
from amf.amf.utils.operations_ai_schemas import OperationsInsights


class OperationsAIInsightsTest(unittest.TestCase):
    def setUp(self):
        self.data = {
            "scope": {
                "company": "AMF",
                "currency": "CHF",
                "period_start": "2026-05-01",
                "period_end": "2026-05-31",
                "period_label": "2026-05",
            },
            "otif": {
                "current": {"total": 100, "on_time": 82, "rate": 82.0},
                "previous": {"total": 100, "on_time": 90, "rate": 90.0},
                "semester_to_date": {"total": 500, "on_time": 440, "rate": 88.0},
                "change_vs_previous_points": -8.0,
                "strict": {
                    "eligible_lines": 100,
                    "delivered_in_full_by_due": 80,
                    "rate": 80.0,
                    "open_shortfall_lines": 2,
                    "open_shortfall_qty": 15.0,
                    "open_shortfalls": [
                        {
                            "sales_order": "SO-1",
                            "customer": "Customer SA",
                            "item_code": "40001",
                            "remaining_qty": 10.0,
                        }
                    ],
                },
                "top_customers": [
                    {"name": "Customer SA", "lines": 10, "rate": 70.0}
                ],
                "top_item_groups": [],
                "worst_deliveries": [],
            },
            "machining": {
                "current": {
                    "scrap_rate": 4.2,
                    "families": {},
                    "top_scrap_items": [],
                },
                "semester_to_date": {},
            },
            "shipping": {
                "issue_count": 3,
                "delivery_note_count": 50,
                "issue_rate_per_100_delivery_notes": 6.0,
                "issues": [
                    {
                        "issue": "ISS-1",
                        "status": "Open",
                        "age_days": 12,
                        "root_cause": "Unstructured confidential detail",
                    }
                ],
            },
            "procurement": {
                "item_count": 12,
                "ratio_percent": 103.0,
                "weighted_ratio_percent": 101.5,
                "estimated_price_impact": 250.0,
                "review_items": [
                    {
                        "item_code": "100001",
                        "latest_supplier": "Supplier SA",
                        "previous_supplier": "Supplier SA",
                        "change_percent": 12.0,
                    }
                ],
                "anomalies": [],
            },
        }

    def test_payload_anonymizes_external_entities(self):
        payload = build_ai_payload(self.data, anonymize_external_parties=True)
        self.assertEqual(payload["otif"]["top_customers"][0]["name"], "Customer 01")
        self.assertEqual(
            payload["otif"]["open_shortfalls"][0]["customer"],
            "Customer 01",
        )
        self.assertEqual(
            payload["procurement"]["review_items"][0]["latest_supplier"],
            "Supplier 01",
        )

    def test_validation_uses_authoritative_evidence_value(self):
        payload = build_ai_payload(self.data)
        output = self._structured_output()
        output["insights"][0]["evidence"][0]["value"] = "invented"
        output["insights"].append(
            dict(
                output["insights"][0],
                confidence=0.2,
                title_en="Low confidence",
            )
        )

        validated = validate_ai_output(
            output,
            payload,
            minimum_confidence=0.65,
            max_insights=8,
        )

        self.assertEqual(len(validated["insights"]), 1)
        self.assertEqual(
            validated["insights"][0]["evidence"][0]["value"],
            "82",
        )

    def test_issue_free_text_is_opt_in(self):
        default_payload = build_ai_payload(self.data)
        opted_in_payload = build_ai_payload(
            self.data,
            include_issue_free_text=True,
        )
        self.assertNotIn(
            "root_cause",
            default_payload["shipping"]["issues"][0],
        )
        self.assertEqual(
            opted_in_payload["shipping"]["issues"][0]["root_cause"],
            "Unstructured confidential detail",
        )

    def test_every_evidence_path_is_a_real_leaf(self):
        payload = build_ai_payload(self.data)
        leaves = flatten_leaf_values(payload)
        self.assertIn("otif.current.rate", leaves)
        self.assertNotIn("otif.current", leaves)

    def test_common_model_path_notations_resolve_to_canonical_leaf(self):
        payload = build_ai_payload(self.data)
        leaves = flatten_leaf_values(payload)
        for path in (
            "$.otif.current.rate",
            "/otif/current/rate",
            "payload.otif.current.rate",
            "data['otif']['current']['rate']",
            "`snapshot.otif.current.rate`",
        ):
            self.assertEqual(
                resolve_evidence_path(path, "82%", leaves),
                "otif.current.rate",
            )

    def test_container_path_requires_unique_matching_canonical_value(self):
        payload = build_ai_payload(self.data)
        leaves = flatten_leaf_values(payload)
        self.assertEqual(
            resolve_evidence_path("otif.strict", "15.0", leaves),
            "otif.strict.open_shortfall_qty",
        )
        self.assertIsNone(
            resolve_evidence_path("otif.current", "999", leaves)
        )

    def test_normalize_evidence_path_handles_array_notation(self):
        self.assertEqual(
            normalize_evidence_path(
                "$.procurement['review_items'].0.change_percent"
            ),
            "procurement.review_items[0].change_percent",
        )

    def test_structured_output_schema_accepts_expected_contract(self):
        parsed = OperationsInsights(**self._structured_output())
        self.assertEqual(len(parsed.insights), 1)

    def test_missing_api_key_fails_before_any_external_call(self):
        class Settings(dict):
            def get_password(self, *args, **kwargs):
                return ""

        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}):
            with self.assertRaises(AIConfigurationError):
                generate_ai_insights(self.data, Settings())

    def test_long_api_key_is_encrypted_outside_auth_table(self):
        class Settings(dict):
            __getattr__ = dict.get
            __setattr__ = dict.__setitem__

        settings = Settings(
            openai_api_key="sk-proj-" + ("x" * 220),
            openai_api_key_encrypted="",
        )
        with patch(
            "amf.amf.utils.openai_credentials.encrypt",
            return_value="encrypted-value",
        ):
            store_openai_api_key(settings, settings["openai_api_key"])
        self.assertEqual(settings["openai_api_key"], "")
        self.assertEqual(settings["openai_api_key_encrypted"], "encrypted-value")
        self.assertEqual(settings["openai_api_key_configured"], 1)

        with patch(
            "amf.amf.utils.openai_credentials.decrypt",
            return_value="sk-proj-" + ("x" * 220),
        ):
            self.assertTrue(get_openai_api_key(settings).startswith("sk-proj-"))

    def _structured_output(self):
        return {
            "executive_summary_en": "Delivery performance requires attention.",
            "executive_summary_fr": "La performance de livraison requiert une attention.",
            "insights": [
                {
                    "category": "Delivery",
                    "severity": "High",
                    "finding_type": "Confirmed",
                    "title_en": "On-time performance declined",
                    "title_fr": "La ponctualite a recule",
                    "finding_en": "The current rate is below the previous month.",
                    "finding_fr": "Le taux actuel est inferieur au mois precedent.",
                    "operational_impact_en": "Customer commitments are exposed.",
                    "operational_impact_fr": "Les engagements clients sont exposes.",
                    "recommendation_en": "Review late orders twice weekly.",
                    "recommendation_fr": "Revoir les commandes en retard deux fois par semaine.",
                    "confidence": 0.92,
                    "evidence": [
                        {
                            "source_path": "otif.current.rate",
                            "value": "82.0",
                        }
                    ],
                }
            ],
            "management_questions_en": ["Which constraints caused the decline?"],
            "management_questions_fr": ["Quelles contraintes ont cause le recul ?"],
            "assumptions": [],
            "data_quality_warnings": [],
        }


if __name__ == "__main__":
    unittest.main()
