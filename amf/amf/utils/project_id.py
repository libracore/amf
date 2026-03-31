# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter
from frappe.model.naming import make_autoname

PROJECT_ID_FORMAT = "PRJ-YY-####"
PROJECT_ID_SERIES = "PRJ-.YY.-.####"
PROJECT_SEARCH_FIELD = "project_id"
PROJECT_CUSTOM_FIELDS = {
    "Project": [
        {
            "fieldname": "project_id",
            "label": "Project ID",
            "fieldtype": "Data",
            "insert_after": "project_name",
            "read_only": 1,
            "unique": 1,
            "no_copy": 1,
            "in_list_view": 1,
            "in_standard_filter": 1,
            "search_index": 1,
            "translatable": 0,
        }
    ]
}


def assign_project_id(doc, method=None):
    if doc.get("project_id"):
        return

    doc.project_id = make_autoname(PROJECT_ID_SERIES)


def ensure_project_custom_field():
    create_custom_fields(PROJECT_CUSTOM_FIELDS)
    frappe.clear_cache(doctype="Project")


def get_project_search_fields():
    search_fields = []

    for fieldname in (frappe.get_meta("Project").search_fields or "").split(","):
        fieldname = (fieldname or "").strip()
        if fieldname and fieldname not in search_fields:
            search_fields.append(fieldname)

    return search_fields


def ensure_project_search_fields():
    search_fields = get_project_search_fields()
    if PROJECT_SEARCH_FIELD not in search_fields:
        search_fields.append(PROJECT_SEARCH_FIELD)

    desired_value = ", ".join(search_fields)
    current_value = frappe.get_meta("Project").search_fields or ""

    if current_value == desired_value:
        return

    property_setter_filters = {
        "doc_type": "Project",
        "doctype_or_field": "DocType",
        "field_name": "",
        "property": "search_fields",
    }
    property_setter_names = frappe.get_all(
        "Property Setter",
        filters=property_setter_filters,
        fields=["name"],
    )

    if property_setter_names:
        for property_setter in property_setter_names:
            frappe.db.set_value(
                "Property Setter",
                property_setter.name,
                "value",
                desired_value,
                update_modified=False,
            )
    else:
        make_property_setter(
            "Project",
            "",
            "search_fields",
            desired_value,
            "Data",
            for_doctype=True,
            validate_fields_for_doctype=False,
        )

    frappe.clear_cache(doctype="Project")


def backfill_missing_project_ids():
    if "project_id" not in frappe.db.get_table_columns("Project"):
        return

    projects_without_id = frappe.db.sql(
        """
        SELECT name
        FROM `tabProject`
        WHERE IFNULL(project_id, '') = ''
        ORDER BY creation ASC
        """
    )

    for project_name, in projects_without_id:
        frappe.db.set_value(
            "Project",
            project_name,
            "project_id",
            make_autoname(PROJECT_ID_SERIES),
            update_modified=False,
        )


def sync_project_id_customization():
    ensure_project_custom_field()
    ensure_project_search_fields()
    backfill_missing_project_ids()


def after_install():
    sync_project_id_customization()
