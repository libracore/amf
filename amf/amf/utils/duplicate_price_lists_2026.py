from __future__ import unicode_literals

import codecs
import csv
import os
from collections import Counter
from decimal import Decimal, InvalidOperation

import frappe


DEFAULT_CSV_FILENAME = "Item_Price_S2_2026.csv"

PRICE_LISTS = {
    "CHF": {
        "source": "[NEW] Price List S2 2025 AMF - CHF",
        "target": "Price List S2 2026 AMF - CHF",
    },
    "USD": {
        "source": "[NEW] Price List S2 2025 AMF - USD",
        "target": "Price List S2 2026 AMF - USD",
    },
    "EUR": {
        "source": "[NEW] Price List S2 2025 AMF - EUR",
        "target": "Price List S2 2026 AMF - EUR",
    },
}

ITEM_PRICE_COPY_FIELDS = [
    "item_code",
    "uom",
    "packing_unit",
    "min_qty",
    "customer",
    "supplier",
    "price_list_rate",
    "valid_from",
    "lead_time_days",
    "valid_upto",
    "note",
]

VERIFY_FIELDS = [
    "item_code",
    "uom",
    "packing_unit",
    "min_qty",
    "valid_from",
    "valid_upto",
    "customer",
    "supplier",
    "price_list_rate",
    "lead_time_days",
    "note",
]


def to_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    return str(value or "0").lower() in ("1", "true", "yes")


def as_bool(value):
    return 1 if value else 0


def money(value):
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def normalize_date(value):
    return str(value) if value else None


def resolve_csv_path(csv_path=None):
    if csv_path:
        if os.path.isabs(csv_path):
            return csv_path
        return frappe.get_site_path(*csv_path.split("/"))

    return frappe.get_site_path("private", "files", DEFAULT_CSV_FILENAME)


def item_price_key(row):
    return (
        row.get("item_code") or None,
        row.get("uom") or None,
        int(row.get("packing_unit") or 0),
        int(row.get("min_qty") or 0),
        normalize_date(row.get("valid_from")),
        normalize_date(row.get("valid_upto")),
        row.get("customer") or None,
        row.get("supplier") or None,
    )


def verify_row_key(row):
    return item_price_key(row) + (
        money(row.get("price_list_rate")),
        int(row.get("lead_time_days") or 0),
        row.get("note") or None,
    )


def load_csv_rows(csv_path=None):
    resolved_csv_path = resolve_csv_path(csv_path)
    rows = list(csv.DictReader(codecs.open(resolved_csv_path, "r", "utf-8-sig")))
    required_columns = set(["item_code"]).union(PRICE_LISTS.keys())
    missing_columns = required_columns.difference(rows[0].keys() if rows else [])
    if missing_columns:
        raise ValueError("CSV missing columns: {0}".format(", ".join(sorted(missing_columns))))

    seen = set()
    normalized = []
    for idx, row in enumerate(rows, start=2):
        item_code = (row.get("item_code") or "").strip()
        if not item_code:
            raise ValueError("CSV row {0} has no item_code".format(idx))
        if item_code in seen:
            raise ValueError("CSV item_code appears more than once: {0}".format(item_code))
        seen.add(item_code)

        values = {"item_code": item_code}
        for currency in PRICE_LISTS:
            raw_value = (row.get(currency) or "").strip()
            try:
                values[currency] = Decimal(raw_value)
            except (InvalidOperation, TypeError):
                raise ValueError(
                    "CSV row {0} item {1} has invalid {2} price: {3}".format(
                        idx, item_code, currency, raw_value
                    )
                )
        normalized.append(frappe._dict(values))
    return resolved_csv_path, normalized


def validate_inputs(csv_rows):
    for currency, mapping in PRICE_LISTS.items():
        if not frappe.db.exists("Currency", currency):
            raise ValueError("Missing Currency: {0}".format(currency))
        if not frappe.db.exists("Price List", mapping["source"]):
            raise ValueError("Missing source Price List: {0}".format(mapping["source"]))

    missing_items = [
        row.item_code for row in csv_rows if not frappe.db.exists("Item", row.item_code)
    ]
    if missing_items:
        raise ValueError("Missing Item records: {0}".format(", ".join(missing_items)))


def ensure_price_list(currency, source_name, target_name, summary):
    source = frappe.get_doc("Price List", source_name)
    if source.currency != currency:
        raise ValueError(
            "Source Price List {0} has currency {1}, expected {2}".format(
                source_name, source.currency, currency
            )
        )

    if frappe.db.exists("Price List", target_name):
        target = frappe.get_doc("Price List", target_name)
        summary["price_lists_reused"] += 1
    else:
        target = frappe.new_doc("Price List")
        target.price_list_name = target_name
        target.name = target_name
        summary["price_lists_created"] += 1

    changed = False
    for field in ["enabled", "currency", "buying", "selling", "price_not_uom_dependent"]:
        if target.get(field) != source.get(field):
            target.set(field, source.get(field))
            changed = True

    if target.get("price_list_name") != target_name:
        target.price_list_name = target_name
        changed = True

    if target.is_new():
        target.insert(ignore_permissions=True)
    elif changed:
        target.save(ignore_permissions=True)
        summary["price_lists_updated"] += 1


def build_target_index(target_name):
    rows = frappe.get_all(
        "Item Price",
        filters={"price_list": target_name},
        fields=[
            "name",
            "item_code",
            "uom",
            "packing_unit",
            "min_qty",
            "valid_from",
            "valid_upto",
            "customer",
            "supplier",
        ],
        limit_page_length=0,
    )
    index = {}
    for row in rows:
        key = item_price_key(row)
        if key in index:
            raise ValueError(
                "Target {0} has duplicate Item Price key for item {1}".format(
                    target_name, row.item_code
                )
            )
        index[key] = row.name
    return index


def set_item_price_values(target_doc, source_values, target_name):
    for field in ITEM_PRICE_COPY_FIELDS:
        target_doc.set(field, source_values.get(field))
    target_doc.price_list = target_name


def clear_valid_from_if_blank(name, source_values):
    if not source_values.get("valid_from"):
        frappe.db.set_value(
            "Item Price",
            name,
            "valid_from",
            None,
            update_modified=False,
        )


def update_existing_item_price(name, source_values, target_name):
    values = {"price_list": target_name}
    values.update({field: source_values.get(field) for field in ITEM_PRICE_COPY_FIELDS})
    frappe.db.set_value("Item Price", name, values)
    clear_valid_from_if_blank(name, source_values)


def insert_item_price(doc, source_values):
    doc.insert(ignore_permissions=True, ignore_links=True)
    clear_valid_from_if_blank(doc.name, source_values)


def upsert_item_price(source_values, target_name, target_index, summary_key, summary):
    key = item_price_key(source_values)
    existing_name = target_index.get(key)
    if existing_name:
        update_existing_item_price(existing_name, source_values, target_name)
        summary[summary_key + "_updated"] += 1
        return

    target_doc = frappe.new_doc("Item Price")
    set_item_price_values(target_doc, source_values, target_name)
    insert_item_price(target_doc, source_values)
    target_index[key] = target_doc.name
    summary[summary_key + "_created"] += 1


def csv_item_price_values(item_code, price):
    return frappe._dict(
        {
            "item_code": item_code,
            "uom": None,
            "packing_unit": 0,
            "min_qty": 0,
            "customer": None,
            "supplier": None,
            "price_list_rate": price,
            "valid_from": None,
            "lead_time_days": 0,
            "valid_upto": None,
            "note": None,
        }
    )


def copy_price_lists(csv_rows):
    summary = {
        "price_lists_created": 0,
        "price_lists_reused": 0,
        "price_lists_updated": 0,
        "source_item_prices_created": 0,
        "source_item_prices_updated": 0,
        "csv_item_prices_created": 0,
        "csv_item_prices_updated": 0,
    }

    for currency, mapping in PRICE_LISTS.items():
        ensure_price_list(currency, mapping["source"], mapping["target"], summary)

    for currency, mapping in PRICE_LISTS.items():
        target_index = build_target_index(mapping["target"])
        source_names = frappe.get_all(
            "Item Price",
            filters={"price_list": mapping["source"]},
            fields=["name"],
            order_by="creation asc, name asc",
            limit_page_length=0,
        )
        for source_name in source_names:
            source_doc = frappe.get_doc("Item Price", source_name.name)
            upsert_item_price(
                source_doc,
                mapping["target"],
                target_index,
                "source_item_prices",
                summary,
            )

        for row in csv_rows:
            source_values = csv_item_price_values(row.item_code, row[currency])
            upsert_item_price(
                source_values,
                mapping["target"],
                target_index,
                "csv_item_prices",
                summary,
            )

    return summary


def verify(csv_rows):
    csv_codes = set(row.item_code for row in csv_rows)
    results = {}

    for currency, mapping in PRICE_LISTS.items():
        source_rows = frappe.get_all(
            "Item Price",
            filters={"price_list": mapping["source"]},
            fields=VERIFY_FIELDS,
            limit_page_length=0,
        )
        target_rows = frappe.get_all(
            "Item Price",
            filters={"price_list": mapping["target"]},
            fields=VERIFY_FIELDS + ["currency", "selling", "buying"],
            limit_page_length=0,
        )
        target_source_rows = [row for row in target_rows if row.item_code not in csv_codes]
        copied_rows_match = Counter(verify_row_key(row) for row in source_rows) == Counter(
            verify_row_key(row) for row in target_source_rows
        )

        csv_target_rows = [row for row in target_rows if row.item_code in csv_codes]
        by_code = {row.item_code: row for row in csv_target_rows}
        csv_missing = [row.item_code for row in csv_rows if row.item_code not in by_code]
        csv_mismatched = []
        for row in csv_rows:
            target_row = by_code.get(row.item_code)
            if not target_row:
                continue
            if (
                money(target_row.price_list_rate) != money(row[currency])
                or target_row.currency != currency
                or as_bool(target_row.selling) != 1
                or as_bool(target_row.buying) != 0
                or target_row.valid_from
            ):
                csv_mismatched.append(row.item_code)

        results[currency] = {
            "source_count": len(source_rows),
            "target_count": len(target_rows),
            "expected_target_count": len(source_rows) + len(csv_rows),
            "copied_source_rows_match": copied_rows_match,
            "csv_rows_found": len(csv_target_rows),
            "csv_missing": csv_missing,
            "csv_mismatched": csv_mismatched,
        }

    return results


def run(csv_path=None, dry_run=0):
    """Copy S2 2025 AMF price lists to S2 2026 and add CSV item prices.

    Intended usage:
        bench --site site execute amf.amf.utils.duplicate_price_lists_2026.run
        bench --site site execute amf.amf.utils.duplicate_price_lists_2026.run --kwargs "{'dry_run': 1}"
    """
    dry_run = to_bool(dry_run)
    resolved_csv_path, csv_rows = load_csv_rows(csv_path)
    validate_inputs(csv_rows)
    summary = copy_price_lists(csv_rows)
    verification = verify(csv_rows)

    result = {
        "dry_run": dry_run,
        "csv": resolved_csv_path,
        "summary": summary,
        "verification": verification,
    }

    if dry_run:
        frappe.db.rollback()
        result["status"] = "DRY RUN - rolled back"
    else:
        frappe.db.commit()
        result["status"] = "COMMITTED"

    return result

