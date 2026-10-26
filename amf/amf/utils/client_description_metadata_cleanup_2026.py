"""Remove internal provenance markup from customer-facing Item descriptions."""

from __future__ import unicode_literals

import argparse
import csv
import json
import os
import re
from datetime import datetime


BENCH_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../.."))
EVIDENCE_LABELS = (
	"researched",
	"self-fallback",
	"safe-fallback",
	"erp-catalog",
	"supplier-capability",
	"supplier-catalog",
	"group-specification",
	"previous-generated",
)
LABEL_PATTERN = "(?:{})".format("|".join(re.escape(label) for label in EVIDENCE_LABELS))
COMMENT_PATTERN = re.compile(r"<!--.*?-->", re.S)
LABEL_DIV_PATTERN = re.compile(r"<div>\s*{}\s*</div>".format(LABEL_PATTERN), re.I)
BARE_LABEL_PATTERN = re.compile(r"(?<=>)\s*{}\s*(?=<)".format(LABEL_PATTERN), re.I)
REMAINING_LABEL_PATTERN = re.compile(LABEL_PATTERN, re.I)


def clean_client_description(value):
	"""Preserve product wording and formatting while dropping internal-only metadata."""
	value = value or ""
	cleaned = COMMENT_PATTERN.sub("", value)
	cleaned = LABEL_DIV_PATTERN.sub("", cleaned)
	cleaned = BARE_LABEL_PATTERN.sub("", cleaned)
	return cleaned


def description_changes(frappe_module):
	rows = frappe_module.db.sql(
		"select name, description from tabItem where description is not null and description != ''",
		as_dict=True,
	)
	changes = []
	for row in rows:
		before = row.description or ""
		after = clean_client_description(before)
		if "<!--" in after or "-->" in after or REMAINING_LABEL_PATTERN.search(after):
			raise RuntimeError("Client description still contains internal metadata: {}".format(row.name))
		if before == after:
			continue
		changes.append({"name": row.name, "before": before, "after": after})
	return changes


def apply_client_description_metadata_cleanup(frappe_module, update_modified=True):
	changes = description_changes(frappe_module)
	for row in changes:
		frappe_module.db.set_value(
			"Item", row["name"], "description", row["after"],
			modified_by="Administrator", update_modified=update_modified,
		)
	for row in changes:
		persisted = frappe_module.db.get_value("Item", row["name"], "description") or ""
		if persisted != row["after"]:
			raise RuntimeError("Client description cleanup did not persist for {}".format(row["name"]))
	return len(changes)


def write_debug_csv(frappe_module, path):
	"""Export the persisted purchased-item descriptions without regenerating them."""
	from amf.amf.utils.purchased_item_description_update_2026 import load_target_items

	items = load_target_items(frappe_module)
	with open(path, "w", encoding="utf-8-sig", newline="") as handle:
		writer = csv.DictWriter(handle, fieldnames=[
			"item_code", "item_name", "new_item_group", "client_description",
			"internal_description", "customs_description",
		])
		writer.writeheader()
		for item in items:
			writer.writerow({
				"item_code": item.get("item_code") or item.name,
				"item_name": item.get("item_name") or "",
				"new_item_group": item.get("item_group") or "",
				"client_description": item.get("description") or "",
				"internal_description": item.get("internal_description") or "",
				"customs_description": item.get("custom_description") or "",
			})
	return len(items)


def main():
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--site", default="site1.local")
	parser.add_argument("--apply", action="store_true")
	parser.add_argument(
		"--output-dir",
		default=os.path.join(BENCH_PATH, "purchased_item_description_cleanup_2026-10-22"),
	)
	args = parser.parse_args()
	import frappe

	frappe.init(site=args.site, sites_path=os.path.join(BENCH_PATH, "sites"))
	frappe.connect()
	try:
		changes = description_changes(frappe)
		os.makedirs(args.output_dir, exist_ok=True)
		stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
		backup_path = os.path.join(args.output_dir, "client_description_backup_{}.json".format(stamp))
		with open(backup_path, "w", encoding="utf-8") as handle:
			json.dump(changes, handle, ensure_ascii=False, indent=2)
			if changes:
				handle.write("\n")
		applied_count = 0
		if args.apply:
			frappe.set_user("Administrator")
			applied_count = apply_client_description_metadata_cleanup(frappe)
		csv_path = os.path.join(args.output_dir, "purchased_item_descriptions_debug.csv")
		csv_count = write_debug_csv(frappe, csv_path)
		if args.apply:
			frappe.db.commit()
		else:
			frappe.db.rollback()
		print(json.dumps({
			"changed_count": len(changes), "applied_count": applied_count,
			"backup_file": backup_path, "csv_file": csv_path,
			"csv_item_count": csv_count,
		}, indent=2))
	except Exception:
		frappe.db.rollback()
		raise
	finally:
		frappe.destroy()


if __name__ == "__main__":
	main()
