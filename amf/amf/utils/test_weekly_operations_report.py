# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from amf.amf.report.on_time_delivery_kpis.on_time_delivery_kpis import (
    get_conditions as get_otif_conditions,
)
from amf.amf.utils.weekly_operations_report import (
    _date_sort_key,
    _priority_date_sort_key,
    _shorten,
    build_management_signals,
    build_slide_html,
    collect_quality_control,
    get_output_vs_plan,
    get_reporting_months,
    parse_recipients,
    render_slide_png,
)


class TestWeeklyOperationsReport(unittest.TestCase):
    def test_reporting_months_end_at_snapshot_date(self):
        periods = get_reporting_months(date(2026, 8, 14), count=3)
        self.assertEqual(
            periods,
            [
                (date(2026, 6, 1), date(2026, 6, 30)),
                (date(2026, 7, 1), date(2026, 7, 31)),
                (date(2026, 8, 1), date(2026, 8, 14)),
            ],
        )

    def test_recipients_are_split_and_empty_values_removed(self):
        self.assertEqual(
            parse_recipients("ops@example.com; qa@example.com\nshipping@example.com"),
            ["ops@example.com", "qa@example.com", "shipping@example.com"],
        )

    def test_management_signals_have_safe_empty_state(self):
        signals = build_management_signals(
            report_date=date(2026, 8, 14),
            overdue_deliveries=[],
            machining={"overdue_count": 0},
            current_work_orders={"overdue_count": 0},
            quality={"rejected_count": 0, "backlog_count": 0},
            shipping={"ready_total": 0},
        )
        self.assertEqual(signals["critical_risks"], ["No critical risk detected"])
        self.assertEqual(signals["alerts"], ["No operational blocker detected"])
        self.assertEqual(signals["decisions"], ["No escalation required"])

    def test_slide_template_preserves_source_geometry_and_escapes_data(self):
        row = {
            "primary": "Customer <unsafe>",
            "secondary": "WO-1",
            "due_date": date(2026, 8, 14),
            "overdue": False,
        }
        data = {
            "scope": {
                "iso_week": 33,
                "date_label": "14.08.26",
                "departure_date_label": "14.08",
                "owner": "ATR",
            },
            "delivery_performance": {
                "output_vs_plan": [
                    {
                        "month": "Août",
                        "actual": 8,
                        "planned": 9,
                        "rate": 88.9,
                        "tone": "amber",
                    }
                ],
                "otif": [
                    {"month": "Aug. 26", "rate": 92.9, "tone": "green"}
                ],
            },
            "quality": {
                "backlog_items": [],
                "backlog_count": 0,
                "items": [],
            },
            "signals": {
                "critical_risks": ["No critical risk detected"],
                "alerts": ["No operational blocker detected"],
                "decisions": ["No escalation required"],
            },
            "machining": {"items": [row]},
            "current_work_orders": {"items": []},
            "shipping": {"ready": [], "shipped": []},
        }
        html = build_slide_html(data)
        self.assertIn("width: 1280px", html)
        self.assertIn("height: 720px", html)
        self.assertIn("338.667mm 190.5mm", html)
        self.assertIn("Customer &lt;unsafe&gt;", html)
        self.assertNotIn("Customer <unsafe>", html)

    def test_short_labels_use_an_ellipsis(self):
        self.assertEqual(_shorten("abcdefgh", 6), "abcde…")

    @patch(
        "amf.amf.report.on_time_delivery_kpis.on_time_delivery_kpis."
        "get_skip_otif_kpi_condition",
        return_value="",
    )
    def test_otif_excludes_gx_items(self, _skip_condition):
        conditions, _params = get_otif_conditions(
            {"from_date": date(2026, 8, 1), "to_date": date(2026, 8, 31)}
        )
        self.assertIn("dni.item_code NOT RLIKE '^GX'", conditions)

    @patch(
        "amf.amf.utils.weekly_operations_report.get_skip_otif_kpi_condition",
        return_value="",
    )
    @patch("amf.amf.utils.weekly_operations_report.frappe.db.sql")
    def test_output_vs_plan_uses_only_production_orders(self, sql, _skip_condition):
        sql.return_value = [SimpleNamespace(planned=1, actual=1)]
        get_output_vs_plan(date(2026, 8, 1), date(2026, 8, 31))
        query = sql.call_args[0][0]
        self.assertIn("so.sales_order_type = 'Production'", query)

    @patch(
        "amf.amf.utils.weekly_operations_report.frappe.db.sql",
        return_value=[],
    )
    def test_quality_control_excludes_gx_items(self, sql):
        collect_quality_control(
            date(2026, 8, 31),
            "Quality Control - AMF21",
        )
        query = sql.call_args[0][0]
        self.assertIn("sle.item_code NOT LIKE 'GX%%'", query)

    def test_machining_sort_uses_priority_then_date(self):
        rows = [
            {"name": "WO-NO-PRIORITY", "priority": 0, "due_date": date(2026, 8, 1)},
            {"name": "WO-P2-EARLY", "priority": 2, "due_date": date(2026, 8, 10)},
            {"name": "WO-P1-LATE", "priority": 1, "due_date": date(2026, 8, 20)},
            {"name": "WO-P2-LATE", "priority": 2, "due_date": date(2026, 8, 15)},
        ]
        rows.sort(key=_priority_date_sort_key)
        self.assertEqual(
            [row["name"] for row in rows],
            ["WO-P1-LATE", "WO-P2-EARLY", "WO-P2-LATE", "WO-NO-PRIORITY"],
        )

    def test_assembly_sort_uses_due_date(self):
        rows = [
            {"name": "WO-2", "due_date": date(2026, 8, 20)},
            {"name": "WO-1", "due_date": date(2026, 8, 10)},
        ]
        rows.sort(key=_date_sort_key)
        self.assertEqual([row["name"] for row in rows], ["WO-1", "WO-2"])

    @patch("amf.amf.utils.weekly_operations_report.shutil.which")
    @patch("amf.amf.utils.weekly_operations_report.subprocess.run")
    def test_png_render_uses_full_hd_resolution(self, run, which):
        which.return_value = "/usr/bin/pdftoppm"

        def create_png(command, **kwargs):
            with open(command[-1] + ".png", "wb") as output:
                output.write(b"png-data")
            result = type("Result", (), {})()
            result.returncode = 0
            result.stderr = b""
            return result

        run.side_effect = create_png
        self.assertEqual(render_slide_png(b"pdf-data"), b"png-data")
        command = run.call_args[0][0]
        self.assertIn("-singlefile", command)
        self.assertEqual(command[command.index("-r") + 1], "144")


if __name__ == "__main__":
    unittest.main()
