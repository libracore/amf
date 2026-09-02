from __future__ import unicode_literals

import os

import frappe


PRINT_FORMAT_NAME = "Standard Branding AMF 2026"
TEMPLATE_FILENAME = "sales_order_standard_branding_amf_2026.html"
STYLESHEET_FILENAME = "sales_order_standard_branding_amf_2026.css"


def install_sales_order_print_format():
    """Install the enhanced Sales Order format and make it the default."""
    template_directory = frappe.get_app_path("amf", "templates", "print_formats")
    html = _read_text(os.path.join(template_directory, TEMPLATE_FILENAME))
    css = _read_text(os.path.join(template_directory, STYLESHEET_FILENAME))

    values = {
        "doc_type": "Sales Order",
        "module": "Selling",
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

    _set_sales_order_default_print_format()
    return print_format


def _read_text(path):
    with open(path, "r", encoding="utf-8") as source_file:
        return source_file.read()


def _set_sales_order_default_print_format():
    property_setter_name = "Sales Order-default_print_format"
    values = {
        "doc_type": "Sales Order",
        "doctype_or_field": "DocType",
        "property": "default_print_format",
        "property_type": "Data",
        "value": PRINT_FORMAT_NAME,
    }

    if frappe.db.exists("Property Setter", property_setter_name):
        property_setter = frappe.get_doc("Property Setter", property_setter_name)
        property_setter.update(values)
        property_setter.save(ignore_permissions=True)
    else:
        frappe.get_doc(
            dict(doctype="Property Setter", name=property_setter_name, **values)
        ).insert(ignore_permissions=True)

    frappe.clear_cache(doctype="Sales Order")
