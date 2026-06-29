# -*- coding: utf-8 -*-
# Copyright (c) 2026, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import json

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import cint, cstr


QUOTATION_DOCTYPE = "Quotation"
PRODUCT_ITEM_GROUPS = ("Product", "Products")


QUOTATION_PRODUCT_DEFINITION_FIELDS = {
    QUOTATION_DOCTYPE: [
        {
            "fieldname": "choice",
            "fieldtype": "Section Break",
            "label": "Product Definition",
            "insert_after": "details",
            "collapsible": 0,
        },
        {
            "fieldname": "product_definition_helper",
            "fieldtype": "HTML",
            "label": "",
            "insert_after": "choice",
        },
        {
            "fieldname": "section_break_48",
            "fieldtype": "Section Break",
            "insert_after": "product_definition_helper",
            "hidden": 1,
            "print_hide": 1,
        },
        {
            "fieldname": "rvm",
            "fieldtype": "Check",
            "label": "Microfluidic Rotary Valve",
            "insert_after": "section_break_48",
            "hidden": 1,
            "print_hide": 1,
            "no_copy": 1,
        },
        {
            "fieldname": "spm",
            "fieldtype": "Check",
            "label": "Programmable Syringe Pump",
            "insert_after": "rvm",
            "hidden": 1,
            "print_hide": 1,
            "no_copy": 1,
        },
        {
            "fieldname": "fast",
            "fieldtype": "Check",
            "label": "Fast",
            "insert_after": "spm",
            "hidden": 1,
            "print_hide": 1,
            "no_copy": 1,
        },
        {
            "fieldname": "slow",
            "fieldtype": "Check",
            "label": "Slow",
            "insert_after": "fast",
            "hidden": 1,
            "print_hide": 1,
            "no_copy": 1,
        },
        {
            "fieldname": "high_volume",
            "fieldtype": "Check",
            "label": "High Volume",
            "insert_after": "slow",
            "hidden": 1,
            "print_hide": 1,
            "no_copy": 1,
        },
        {
            "fieldname": "low_volume",
            "fieldtype": "Check",
            "label": "Low Volume",
            "insert_after": "high_volume",
            "hidden": 1,
            "print_hide": 1,
            "no_copy": 1,
        },
        {
            "fieldname": "high_definition",
            "fieldtype": "Check",
            "label": "High Definition",
            "insert_after": "low_volume",
            "hidden": 1,
            "print_hide": 1,
            "no_copy": 1,
        },
        {
            "fieldname": "standard",
            "fieldtype": "Check",
            "label": "Standard",
            "insert_after": "high_definition",
            "hidden": 1,
            "print_hide": 1,
            "no_copy": 1,
        },
        {
            "fieldname": "oem",
            "fieldtype": "Check",
            "label": "OEM",
            "insert_after": "standard",
            "hidden": 1,
            "print_hide": 1,
            "no_copy": 1,
        },
        {
            "fieldname": "laboratory",
            "fieldtype": "Check",
            "label": "Laboratory",
            "insert_after": "oem",
            "hidden": 1,
            "print_hide": 1,
            "no_copy": 1,
        },
        {
            "fieldname": "body_filter",
            "fieldtype": "Link",
            "label": "Body",
            "options": "Item",
            "insert_after": "laboratory",
            "hidden": 1,
            "print_hide": 1,
            "no_copy": 1,
        },
        {
            "fieldname": "syringe",
            "fieldtype": "Select",
            "label": "Syringe",
            "insert_after": "body_filter",
            "hidden": 1,
            "print_hide": 1,
            "no_copy": 1,
        },
        {
            "fieldname": "syringe_code_filter",
            "fieldtype": "Link",
            "label": "Syringe",
            "options": "Item",
            "insert_after": "syringe",
            "hidden": 1,
            "print_hide": 1,
            "no_copy": 1,
        },
        {
            "fieldname": "head_filter",
            "fieldtype": "Link",
            "label": "Valve Head",
            "options": "Item",
            "insert_after": "syringe_code_filter",
            "hidden": 1,
            "print_hide": 1,
            "no_copy": 1,
        },
        {
            "fieldname": "reset",
            "fieldtype": "Button",
            "label": "Reset Product Definition",
            "insert_after": "head_filter",
            "hidden": 1,
            "print_hide": 1,
        },
        {
            "fieldname": "item_table",
            "fieldtype": "Button",
            "label": "Add Generated Item",
            "insert_after": "reset",
            "hidden": 1,
            "print_hide": 1,
        },
        {
            "fieldname": "drive_code",
            "fieldtype": "Link",
            "label": "Body",
            "options": "Item",
            "insert_after": "item_table",
            "hidden": 1,
            "print_hide": 1,
            "no_copy": 1,
        },
        {
            "fieldname": "drive_head_code1",
            "fieldtype": "Column Break",
            "insert_after": "drive_code",
            "hidden": 1,
            "print_hide": 1,
        },
        {
            "fieldname": "valve_head_code",
            "fieldtype": "Link",
            "label": "Valve Head",
            "options": "Item",
            "insert_after": "drive_head_code1",
            "hidden": 1,
            "print_hide": 1,
            "no_copy": 1,
        },
        {
            "fieldname": "drive_head_code2",
            "fieldtype": "Column Break",
            "insert_after": "valve_head_code",
            "hidden": 1,
            "print_hide": 1,
        },
        {
            "fieldname": "syringe_code",
            "fieldtype": "Link",
            "label": "Syringe",
            "options": "Item",
            "insert_after": "drive_head_code2",
            "hidden": 1,
            "print_hide": 1,
            "no_copy": 1,
        },
        {
            "fieldname": "fill_items_table",
            "fieldtype": "Button",
            "label": "Fill Items Table",
            "insert_after": "syringe_code",
            "hidden": 1,
            "print_hide": 1,
        },
    ]
}


def sync_quotation_product_definition_custom_fields():
    """Install the Quotation product selector helper and hide the legacy controls."""
    create_custom_fields(QUOTATION_PRODUCT_DEFINITION_FIELDS, update=True)
    frappe.clear_cache(doctype=QUOTATION_DOCTYPE)


@frappe.whitelist()
def resolve_product_definition_item(body_item_code, head_item_code, syringe_item_code=None):
    """Resolve the real product Item from the selected body, head, and optional syringe."""
    body = get_item_reference(body_item_code)
    head = get_item_reference(head_item_code)
    syringe = get_item_reference(syringe_item_code) if syringe_item_code else None

    if not body:
        return {"error": "missing_body", "message": "Please select a product body."}
    if not head:
        return {"error": "missing_head", "message": "Please select a valve head."}
    if syringe_item_code and not syringe:
        return {"error": "missing_syringe", "message": "Please select a syringe."}

    expected_reference_code = make_expected_reference_code(body, head, syringe)
    fallback_item_code = make_fallback_item_code(body, head, syringe)
    item = get_product_item_by_reference(expected_reference_code)

    if not item and fallback_item_code:
        item = get_product_item_by_code(fallback_item_code)

    if item:
        item.update(
            {
                "expected_reference_code": expected_reference_code,
                "fallback_item_code": fallback_item_code,
            }
        )
        return item

    return {
        "missing": 1,
        "expected_reference_code": expected_reference_code,
        "fallback_item_code": fallback_item_code,
    }


@frappe.whitelist()
def get_product_definition_head_query(doctype, txt, searchfield, start, page_len, filters):
    """Link query for valve heads that can form an existing product Item."""
    filters = parse_filters(filters)
    body = get_item_reference(filters.get("body_item_code"))
    syringe = get_item_reference(filters.get("syringe_item_code")) if filters.get("syringe_item_code") else None

    if body:
        body_ref = normalize_reference(get_base_reference(body.get("reference_code")))
        syringe_ref = normalize_reference(syringe.get("reference_code")) if syringe else ""
        return get_existing_product_heads(body_ref, syringe_ref, txt, start, page_len)

    return get_generic_valve_heads(txt, start, page_len)


def parse_filters(filters):
    if isinstance(filters, dict):
        return filters
    if not filters:
        return {}
    try:
        return json.loads(filters)
    except Exception:
        return {}


def get_item_reference(item_code):
    if not item_code:
        return None

    return frappe.db.get_value(
        "Item",
        item_code,
        ["name", "item_code", "item_name", "reference_code", "disabled"],
        as_dict=True,
    )


def make_expected_reference_code(body, head, syringe=None):
    body_ref = normalize_reference(get_base_reference(body.get("reference_code")))
    head_code = cstr(head.get("item_code") or head.get("name"))
    syringe_ref = normalize_reference(syringe.get("reference_code")) if syringe else ""
    return "{0}{1}{2}".format(body_ref, head_code, syringe_ref)


def make_fallback_item_code(body, head, syringe=None):
    body_code = cstr(body.get("item_code") or body.get("name"))
    head_code = cstr(head.get("item_code") or head.get("name"))
    if len(body_code) < 2 or len(head_code) < 3:
        return None

    syringe_digit = "0"
    if syringe:
        syringe_code = cstr(syringe.get("item_code") or syringe.get("name"))
        if len(syringe_code) < 3:
            return None
        syringe_digit = syringe_code[2]

    return "4{0}{1}{2}".format(body_code[1], syringe_digit, head_code[-3:])


def get_base_reference(reference_code):
    return cstr(reference_code).split(".")[0]


def normalize_reference(reference_code):
    return cstr(reference_code).replace("-", "").replace(".", "").replace(" ", "")


def get_product_item_by_reference(reference_code):
    if not reference_code:
        return None

    rows = frappe.get_all(
        "Item",
        filters={
            "reference_code": reference_code,
            "disabled": 0,
            "item_group": ["in", PRODUCT_ITEM_GROUPS],
        },
        fields=["name", "item_code", "item_name", "reference_code", "disabled"],
        order_by="item_code asc",
        limit_page_length=1,
    )
    return rows[0] if rows else None


def get_product_item_by_code(item_code):
    if not item_code:
        return None

    return frappe.db.get_value(
        "Item",
        {
            "name": item_code,
            "disabled": 0,
            "item_group": ["in", PRODUCT_ITEM_GROUPS],
        },
        ["name", "item_code", "item_name", "reference_code", "disabled"],
        as_dict=True,
    )


def get_existing_product_heads(body_ref, syringe_ref, txt, start, page_len):
    search_text = "%{0}%".format(cstr(txt))
    return frappe.db.sql(
        """
        SELECT DISTINCT
            head.name,
            head.item_name,
            head.reference_code
        FROM `tabItem` head
        INNER JOIN `tabItem` product
            ON product.reference_code = CONCAT(%(body_ref)s, head.item_code, %(syringe_ref)s)
        WHERE
            head.disabled = 0
            AND head.item_group = 'Valve Head'
            AND product.disabled = 0
            AND product.item_group IN %(product_item_groups)s
            AND (
                head.name LIKE %(txt)s
                OR head.item_code LIKE %(txt)s
                OR head.item_name LIKE %(txt)s
                OR IFNULL(head.reference_code, '') LIKE %(txt)s
            )
        ORDER BY head.item_name ASC
        LIMIT %(start)s, %(page_len)s
        """,
        {
            "body_ref": body_ref,
            "syringe_ref": syringe_ref,
            "product_item_groups": PRODUCT_ITEM_GROUPS,
            "txt": search_text,
            "start": cint(start),
            "page_len": cint(page_len),
        },
    )


def get_generic_valve_heads(txt, start, page_len):
    search_text = "%{0}%".format(cstr(txt))
    return frappe.db.sql(
        """
        SELECT
            name,
            item_name,
            reference_code
        FROM `tabItem`
        WHERE
            disabled = 0
            AND item_group = 'Valve Head'
            AND (
                name LIKE %(txt)s
                OR item_code LIKE %(txt)s
                OR item_name LIKE %(txt)s
                OR IFNULL(reference_code, '') LIKE %(txt)s
            )
        ORDER BY item_name ASC
        LIMIT %(start)s, %(page_len)s
        """,
        {
            "txt": search_text,
            "start": cint(start),
            "page_len": cint(page_len),
        },
    )
