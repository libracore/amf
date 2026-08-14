from __future__ import unicode_literals

import os

import frappe


PRINT_FORMAT_NAME = "Packaging Branding AMF 2026"
LEGACY_PRINT_FORMAT_NAME = "Packaging Branding AMF 2023"
TEMPLATE_FILENAME = "packaging_branding_amf_2026.html"
STYLESHEET_FILENAME = "packaging_branding_amf_2026.css"


def install_packaging_print_format():
    """Create or refresh the enhanced format without modifying the 2023 original."""
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

    _update_packaging_print_button()
    return print_format


def _read_text(path):
    with open(path, "r", encoding="utf-8") as source_file:
        return source_file.read()


def _update_packaging_print_button():
    """Point Delivery Note Custom Scripts at the new format, if applicable."""
    updated = False
    custom_scripts = frappe.get_all(
        "Custom Script",
        filters={"dt": "Delivery Note"},
        fields=["name", "script"],
        limit_page_length=0,
    )
    for custom_script in custom_scripts:
        script = custom_script.script or ""
        if LEGACY_PRINT_FORMAT_NAME not in script:
            continue
        frappe.db.set_value(
            "Custom Script",
            custom_script.name,
            "script",
            script.replace(LEGACY_PRINT_FORMAT_NAME, PRINT_FORMAT_NAME),
        )
        updated = True

    if updated:
        frappe.clear_cache(doctype="Delivery Note")
