from __future__ import unicode_literals

import os
import re

import frappe


PRINT_FORMAT_NAME = "Commercial Invoice from DN 2026"
LEGACY_PRINT_FORMAT_NAMES = (
    "Commercial Invoice from DN",
    "Commercial Invoice (new description)",
)
TEMPLATE_FILENAME = "commercial_invoice_from_dn_2026.html"
STYLESHEET_FILENAME = "commercial_invoice_from_dn_2026.css"


def install_commercial_invoice_print_format():
    """Install the enhanced duplicate and route Delivery Note invoice printing to it."""
    template_directory = frappe.get_app_path("amf", "templates", "print_formats")
    html = _read_text(os.path.join(template_directory, TEMPLATE_FILENAME))
    css = _read_text(os.path.join(template_directory, STYLESHEET_FILENAME))

    values = {
        "doc_type": "Delivery Note",
        "module": "Stock",
        "standard": "No",
        "custom_format": 1,
        "print_format_builder": 0,
        "print_format_type": "Jinja",
        "raw_printing": 0,
        "disabled": 0,
        "default_print_language": "en-US",
        "font": "Default",
        "html": html,
        "css": css,
        "format_data": None,
        "show_section_headings": 0,
        "line_breaks": 0,
        "align_labels_right": 0,
    }

    format_exists = frappe.db.exists("Print Format", PRINT_FORMAT_NAME)
    if format_exists:
        print_format = frappe.get_doc("Print Format", PRINT_FORMAT_NAME)
        print_format.update(values)
    else:
        print_format = frappe.get_doc(
            dict(doctype="Print Format", name=PRINT_FORMAT_NAME, **values)
        )

    if print_format.meta.has_field("disable_smart_shrinking"):
        print_format.disable_smart_shrinking = 1
    print_format.flags.ignore_permissions = True

    if format_exists:
        print_format.save()
    else:
        print_format.insert()

    _set_delivery_note_default_print_format()
    _update_commercial_invoice_buttons()
    return print_format


def _read_text(path):
    with open(path, "r", encoding="utf-8") as source_file:
        return source_file.read()


def _set_delivery_note_default_print_format():
    property_setter = "Delivery Note-default_print_format"
    if frappe.db.exists("Property Setter", property_setter):
        frappe.db.set_value("Property Setter", property_setter, "value", PRINT_FORMAT_NAME)
    else:
        frappe.get_doc(
            {
                "doctype": "Property Setter",
                "name": property_setter,
                "doc_type": "Delivery Note",
                "doctype_or_field": "DocType",
                "property": "default_print_format",
                "property_type": "Data",
                "value": PRINT_FORMAT_NAME,
            }
        ).insert(ignore_permissions=True)
    frappe.clear_cache(doctype="Delivery Note")


def _update_commercial_invoice_buttons():
    updated = False
    custom_scripts = frappe.get_all(
        "Custom Script",
        filters={"dt": "Delivery Note"},
        fields=["name", "script"],
        limit_page_length=0,
    )
    for custom_script in custom_scripts:
        script = custom_script.script or ""
        updated_script = re.sub(
            r'"Commercial Invoice from DN(?: 2026){2,}"',
            '"{}"'.format(PRINT_FORMAT_NAME),
            script,
        )
        for legacy_name in LEGACY_PRINT_FORMAT_NAMES:
            updated_script = updated_script.replace(
                '"{}"'.format(legacy_name),
                '"{}"'.format(PRINT_FORMAT_NAME),
            )
        if updated_script == script:
            continue
        frappe.db.set_value("Custom Script", custom_script.name, "script", updated_script)
        updated = True

    if updated:
        frappe.clear_cache(doctype="Delivery Note")
