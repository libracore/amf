#!/usr/bin/env python3
"""Run AMF feedback checks without committing surveys or queued emails."""
import argparse
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import frappe


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", required=True, help="A local site with the feedback migration installed")
    args = parser.parse_args()
    bench = Path(__file__).resolve().parents[3]
    frappe.init(site=args.site, sites_path=str(bench / "sites"))
    frappe.connect()
    frappe.set_user("Administrator")
    tables = ("Customer Satisfaction Survey", "Satisfaction Feedback Request", "Communication", "Email Queue")
    try:
        missing = [name for name in tables if not frappe.db.exists("DocType", name)]
        if missing:
            print("Install the feedback migration first. Missing: " + ", ".join(missing), file=sys.stderr)
            return 2
        before = {name: frappe.db.count(name) for name in tables}
        suite = unittest.defaultTestLoader.loadTestsFromName("amf.master_crm.test_feedback")
        with patch.object(frappe.db, "commit", side_effect=AssertionError("Test commits are forbidden")):
            result = unittest.TextTestRunner(verbosity=2).run(suite)
        frappe.db.rollback()
        after = {name: frappe.db.count(name) for name in tables}
        print("\nDatabase counts before / after rollback:")
        for name in tables:
            print("  {0}: {1} / {2}".format(name, before[name], after[name]))
        if result.skipped:
            print("Skipped checks need source Sales Orders/Issues with customer Contacts and email addresses.")
        return 0 if result.wasSuccessful() else 1
    finally:
        frappe.db.rollback()
        frappe.destroy()


if __name__ == "__main__":
    raise SystemExit(main())
