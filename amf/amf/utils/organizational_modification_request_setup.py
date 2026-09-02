from __future__ import unicode_literals

import os

import frappe


PRINT_FORMAT_NAME = "AMF.0053 - Organizational Modification Request"
DOCTYPE_NAME = "Organizational Modification Request"
TEMPLATE_FILENAME = "organizational_modification_request.html"
STYLESHEET_FILENAME = "organizational_modification_request.css"


def install_organizational_modification_request_print_format():
	"""Create or refresh the controlled OMR Jinja print format."""
	if not frappe.db.exists("DocType", DOCTYPE_NAME):
		return None

	template_directory = frappe.get_app_path("amf", "templates", "print_formats")
	html = _read_text(os.path.join(template_directory, TEMPLATE_FILENAME))
	css = _read_text(os.path.join(template_directory, STYLESHEET_FILENAME))
	values = {
		"doc_type": DOCTYPE_NAME,
		"module": "AMF",
		"standard": "No",
		"custom_format": 1,
		"print_format_builder": 0,
		"print_format_type": "Jinja",
		"raw_printing": 0,
		"disabled": 0,
		"default_print_language": "fr",
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

	frappe.db.set_value("DocType", DOCTYPE_NAME, "default_print_format", PRINT_FORMAT_NAME)
	frappe.clear_cache(doctype=DOCTYPE_NAME)
	return print_format


def _read_text(path):
	with open(path, "r", encoding="utf-8") as source_file:
		return source_file.read()
