# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import unittest
from datetime import date
from unittest.mock import patch

from amf.amf.utils.weekly_operations_report import (
    _date_sort_key,
    _priority_date_sort_key,
    _shorten,
    build_management_signals,
    build_slide_html,
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
