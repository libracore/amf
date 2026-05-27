# -*- coding: utf-8 -*-
# Copyright (c) 2026, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import cstr


PRODUCT_FAMILY_FIELD = "product_family"
PRODUCT_LINE_FIELD = "product_line"
PRODUCT_VARIANT_FIELD = "product_variant"

OBSOLETE_REPORTING_FIELDS = ("reporting_category",)

SPARE_PART_PREFIXES = ("30",)
RVM_PREFIXES = ("41", "42", "43", "44", "4D", "51", "52", "53", "54", "5D")
SPM_STD_PREFIXES = ("45", "46", "47", "48", "55", "56", "57", "58")
SPM_HD_PREFIXES = ("49", "4A", "4B", "4C", "59", "5A", "5B", "5C")
SPM_HV_PREFIXES = ("46", "48", "4A", "4C", "56", "58", "5A", "5C")

RVM_PRODUCT_LINE_RULES = (
    ("-D-", "RVM D"),
    ("-S-", "RVM S"),
    ("-O-", "RVM O"),
)

CUSTOM_PRODUCT_LINE_RULES = (
    ("NRE", "NRE"),
    ("CUSTOM VALVE", "Custom Valve"),
    ("VALVE CUSTOM", "Custom Valve"),
    ("CUSTOM SYSTEM", "Custom System"),
    ("CUSTOM CONFIGURATION", "Custom System"),
    ("CUSTOM", "Custom System"),
)

ITEM_REPORTING_CUSTOM_FIELDS = {
    "Item": [
        {
            "fieldname": "reporting_section",
            "fieldtype": "Section Break",
            "label": "Reporting",
            "insert_after": "image",
        },
        {
            "fieldname": PRODUCT_FAMILY_FIELD,
            "fieldtype": "Select",
            "label": "Product Family",
            "options": "\nSPM\nRVM\nCustom\nSpare Part",
            "insert_after": "reporting_section",
            "read_only": 1,
            "no_copy": 1,
            "in_standard_filter": 1,
        },
        {
            "fieldname": PRODUCT_LINE_FIELD,
            "fieldtype": "Select",
            "label": "Product Line",
            "options": "\nSPM HD\nSPM STD\nRVM O\nRVM D\nRVM S\nNRE\nCustom Valve\nCustom System",
            "insert_after": PRODUCT_FAMILY_FIELD,
            "read_only": 1,
            "no_copy": 1,
            "in_standard_filter": 1,
        },
        {
            "fieldname": "reporting_column_break",
            "fieldtype": "Column Break",
            "insert_after": PRODUCT_LINE_FIELD,
        },
        {
            "fieldname": PRODUCT_VARIANT_FIELD,
            "fieldtype": "Select",
            "label": "Product Variant",
            "options": "\nSPM HD LV\nSPM HD HV\nSPM STD LV\nSPM STD HV",
            "insert_after": "reporting_column_break",
            "read_only": 1,
            "no_copy": 1,
            "in_standard_filter": 1,
        },
    ]
}


def sync_item_reporting_custom_fields():
    """Create Item reporting fields and backfill existing Item records."""
    remove_obsolete_item_reporting_custom_fields()
    create_custom_fields(ITEM_REPORTING_CUSTOM_FIELDS, update=True)
    return sync_all_item_reporting_fields()


def apply_item_reporting_fields(doc, method=None):
    """Populate Item reporting values from item code and item name before save."""
    if not all(
        _doc_has_field(doc, fieldname)
        for fieldname in (PRODUCT_FAMILY_FIELD, PRODUCT_LINE_FIELD, PRODUCT_VARIANT_FIELD)
    ):
        return

    values = get_item_reporting_values(
        item_code=doc.get("item_code"),
        item_name=doc.get("item_name"),
    )
    doc.set(PRODUCT_FAMILY_FIELD, values[PRODUCT_FAMILY_FIELD])
    doc.set(PRODUCT_LINE_FIELD, values[PRODUCT_LINE_FIELD])
    doc.set(PRODUCT_VARIANT_FIELD, values[PRODUCT_VARIANT_FIELD])


@frappe.whitelist()
def sync_all_item_reporting_fields():
    """Backfill reporting fields for all Items without touching modified timestamps."""
    if not _table_has_reporting_columns():
        return {"updated": 0, "skipped": "missing_columns"}

    updated = 0
    items = frappe.get_all(
        "Item",
        fields=[
            "name",
            "item_code",
            "item_name",
            PRODUCT_FAMILY_FIELD,
            PRODUCT_LINE_FIELD,
            PRODUCT_VARIANT_FIELD,
        ],
    )

    for item in items:
        values = get_item_reporting_values(
            item_code=item.item_code,
            item_name=item.item_name,
        )
        if (
            item.get(PRODUCT_FAMILY_FIELD) == values[PRODUCT_FAMILY_FIELD]
            and item.get(PRODUCT_LINE_FIELD) == values[PRODUCT_LINE_FIELD]
            and item.get(PRODUCT_VARIANT_FIELD) == values[PRODUCT_VARIANT_FIELD]
        ):
            continue

        frappe.db.set_value(
            "Item",
            item.name,
            {
                PRODUCT_FAMILY_FIELD: values[PRODUCT_FAMILY_FIELD],
                PRODUCT_LINE_FIELD: values[PRODUCT_LINE_FIELD],
                PRODUCT_VARIANT_FIELD: values[PRODUCT_VARIANT_FIELD],
            },
            update_modified=False,
        )
        updated += 1

    return {"updated": updated}


def get_item_reporting_values(item_code=None, item_name=None):
    product_family = get_product_family(item_code, item_name)
    product_line = get_product_line(product_family, item_code, item_name)
    return {
        PRODUCT_FAMILY_FIELD: product_family,
        PRODUCT_LINE_FIELD: product_line,
        PRODUCT_VARIANT_FIELD: get_product_variant(product_line, item_code, item_name),
    }


def get_product_family(item_code, item_name=None):
    item_code = cstr(item_code).strip().upper()
    if _starts_with_any(item_code, SPARE_PART_PREFIXES):
        return "Spare Part"
    if _starts_with_any(item_code, RVM_PREFIXES):
        return "RVM"
    if _starts_with_any(item_code, SPM_STD_PREFIXES + SPM_HD_PREFIXES):
        return "SPM"
    if get_custom_product_line(item_code, item_name):
        return "Custom"
    return ""


def get_product_line(product_family, item_code=None, item_name=None):
    item_code = cstr(item_code).strip().upper()
    item_name = cstr(item_name).upper()

    if product_family == "SPM":
        if _starts_with_any(item_code, SPM_HD_PREFIXES):
            return "SPM HD"
        if _starts_with_any(item_code, SPM_STD_PREFIXES):
            return "SPM STD"

    if product_family == "RVM":
        for token, product_line in RVM_PRODUCT_LINE_RULES:
            if token in item_name:
                return product_line

    if product_family == "Custom":
        return get_custom_product_line(item_code, item_name)

    return ""


def get_product_variant(product_line, item_code=None, item_name=None):
    if product_line not in ("SPM HD", "SPM STD"):
        return ""

    item_code = cstr(item_code).strip().upper()
    item_name = cstr(item_name).upper()
    pressure = "HV" if _starts_with_any(item_code, SPM_HV_PREFIXES) or "-HV" in item_name else "LV"
    return "{0} {1}".format(product_line, pressure)


def get_custom_product_line(item_code=None, item_name=None):
    value = "{0} {1}".format(cstr(item_code), cstr(item_name)).upper()
    for token, product_line in CUSTOM_PRODUCT_LINE_RULES:
        if token in value:
            return product_line

    return ""


def remove_obsolete_item_reporting_custom_fields():
    for fieldname in OBSOLETE_REPORTING_FIELDS:
        custom_field = frappe.db.get_value(
            "Custom Field",
            {"dt": "Item", "fieldname": fieldname},
        )
        if custom_field:
            frappe.delete_doc(
                "Custom Field",
                custom_field,
                force=1,
                ignore_permissions=True,
            )


def _starts_with_any(value, prefixes):
    return any(value.startswith(prefix) for prefix in prefixes)


def _doc_has_field(doc, fieldname):
    return bool(getattr(doc, "meta", None) and doc.meta.get_field(fieldname))


def _table_has_reporting_columns():
    try:
        return (
            frappe.db.has_column("Item", PRODUCT_FAMILY_FIELD)
            and frappe.db.has_column("Item", PRODUCT_LINE_FIELD)
            and frappe.db.has_column("Item", PRODUCT_VARIANT_FIELD)
        )
    except Exception:
        return False
