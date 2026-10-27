# -*- coding: utf-8 -*-
# Copyright (c) 2024, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import re
import frappe
from frappe.utils import cint
from amf.amf.utils import item_code_family
from frappe import _
from frappe.model.document import Document


class ItemCreation(Document):
    def before_insert(self):
        from amf.amf.utils.item_creation_traceability import prepare_amendment
        prepare_amendment(self)

    def validate(self):
        from amf.amf.utils.item_creation_workflow import protect_review_fields
        from amf.amf.utils.item_creation_traceability import validate_amendment
        validate_amendment(self)
        _validate_source_family(self)
        protect_review_fields(self)

    def before_submit(self):
        from amf.amf.utils.item_creation_workflow import validate_submission
        validate_submission(self)

    def on_submit(self):
        _execute_creation_plan(self)

    def before_update_after_submit(self):
        frappe.throw(_("Submitted Item Creation requests cannot be edited. Cancel and amend the request with a fresh engineering review."))

    def before_cancel(self):
        from amf.amf.utils.item_creation_traceability import before_cancel
        before_cancel(self)

    def on_cancel(self):
        from amf.amf.utils.item_creation_traceability import on_cancel
        on_cancel(self)

    def on_trash(self):
        if self.docstatus == 2 or self.get("amended_from") or self.get("review_history") or self.get("creation_result") or self.get("execution_results"):
            frappe.throw(_("Cancelled requests, amendments and requests with review or execution history must be retained and cannot be deleted."))


def _validate_source_family(doc):
    new_head = doc.get("head_check") == "Yes"
    if not new_head and doc.get("head_item"):
        head = frappe.get_doc("Item", doc.head_item)
        head.check_permission("read")
        if head.disabled or head.item_group != "Valve Head":
            frappe.throw(_("Select an enabled Valve Head."))
        doc.head_code = head.name
        doc.head_name, doc.head_rnd = head.item_name, head.reference_code
        doc.head_description = head.description
    code = (doc.get("head_code") or "").strip().upper()
    if not code:
        return
    if not re.match(r"^30[0-9A-Z]{4}$", code):
        frappe.throw(_("The head code must be six letters/digits starting with 30."))
    suffix = item_code_family.validate_suffix(code[-3:])
    doc.head_code = code
    for group, prefix in (("plug", "10"), ("seat", "20")):
        if doc.get(group + "_check") == "Yes":
            doc.set(group + "_code", prefix + code[2:])
        elif new_head or cint(doc.get("replace_boms")):
            selected = doc.get(group + "_item") or doc.get(group + "_code")
            if selected:
                selected = selected.strip().upper()
                allowed = (prefix, prefix[0] + "1")
                if (not re.match(r"^[0-9A-Z]{6}$", selected)
                        or selected[:2] not in allowed or selected[-3:] != suffix):
                    frappe.throw(_("Selected {0} {1} does not share head suffix {2}. A reviewed replacement is required.").format(group, selected, suffix))
                doc.set(group + "_code", selected)
    if not new_head:
        if not doc.get("head_item") or doc.head_item != code:
            frappe.throw(_("Select the existing Valve Head Item."))
        if (doc.get("plug_check") == "Yes" or doc.get("seat_check") == "Yes") and not cint(doc.get("replace_boms")):
            frappe.throw(_("Enable reviewed BOM replacements before defining new parts for an existing head."))
    item_code_family.reserve_suffix(suffix, (doc.doctype, doc.name), continuation=not new_head)


def _validate_existing_head_family(head_code):
    item_code_family.validate_existing_head_family(head_code)


@frappe.whitelist()
def syringe_item_query(doctype, txt, searchfield, start, page_len, filters=None, as_dict=False):
    """Any six-character 70X___ Item, where X is a nonzero digit or letter."""
    from frappe.desk.reportview import get_match_cond

    if doctype != "Item" or not frappe.has_permission("Item", "read"):
        frappe.throw(_("Item read permission is required."), frappe.PermissionError)
    return frappe.db.sql("""SELECT name, item_name FROM `tabItem`
        WHERE item_code REGEXP %(pattern)s
        AND (name LIKE %(txt)s OR item_name LIKE %(txt)s OR reference_code LIKE %(txt)s)
        {match} ORDER BY name LIMIT %(start)s, %(page_len)s""".format(match=get_match_cond("Item")),
        dict(pattern="^70[1-9A-Za-z]...$", txt="%" + (txt or "") + "%", start=max(0, cint(start)),
             page_len=min(100, max(1, cint(page_len) or 20))), as_dict=as_dict)


def _build_creation_plan(doc):
    from amf.amf.utils.item_creation_plan import build_plan
    return build_plan(doc)


def _execute_creation_plan(doc):
    from amf.amf.utils.item_creation_workflow import execute_reviewed_plan
    return execute_reviewed_plan(doc)


# --- Mappings for Description Generation ---
# These dictionaries map codes from head_name to human-readable descriptions.
valve_type_map = {
    'D': 'Distribution',      'DS': 'Distribution/Switch',
    'B': 'Bypass',            'DA': 'Distribution/Angled',
    'O': 'On/Off',            'OS': 'On/Off-Switch',
    'SA': 'Switch/Angled',    'SL': 'Sample Loop',
    'T': 'Triangle',          'M' : 'Multiplexing',
    'C': 'Check',             'S' : 'Switch'
}
material_map = {
    'C': 'PCTFE',             'P': 'PTFE',
    'U': 'UHMW-PE',           'V': 'Viton',
    'E': 'EPDM',              'S': 'Stainless Steel',
    'K': 'PEEK',              'A': 'PMMA',
}

BOM_MANAGED_GROUP_ALIASES = {
    "plug": "Plug",
    "valve seat": "Valve Seat",
    "seat": "Valve Seat",
    "valve head": "Valve Head",
    "head": "Valve Head",
}

BOM_MANAGED_PREFIXES = {
    "Plug": {
        "component": "10",
        "sub-assembly": "11",
    },
    "Valve Seat": {
        "component": "20",
        "sub-assembly": "21",
    },
    "Valve Head": {
        "component": "30",
        "sub-assembly": "30",
    },
}

RESERVED_BOM_MANAGED_PREFIXES = ("10", "11", "20", "21", "30")
REUSABLE_COMPONENT_GROUPS = ("Plug", "Valve Seat")


def normalize_bom_managed_group(item_group):
    normalized = BOM_MANAGED_GROUP_ALIASES.get((item_group or "").strip().lower())
    if not normalized:
        raise ValueError(_("Item group must be Plug, Valve Seat, or Valve Head."))
    return normalized


def normalize_bom_managed_variant(item_group, item_type=None, has_bom=None):
    normalized_group = normalize_bom_managed_group(item_group)
    if normalized_group == "Valve Head":
        return "sub-assembly"

    if has_bom is not None:
        if isinstance(has_bom, str):
            has_bom = has_bom.strip().lower() in ("1", "true", "yes")
        return "sub-assembly" if has_bom else "component"

    normalized_item_type = (item_type or "").strip().lower().replace("_", "-")
    if normalized_item_type in ("sub-assembly", "sub assembly"):
        return "sub-assembly"

    return "component"


def _code_tail(suffix):
    # Accept old four-character arguments for existing callers, without allowing
    # the allocator to wrap a new family after 999.
    value = str(suffix or "").strip().upper()
    if len(value) == 3:
        return "0" + item_code_family.normalize_suffix(value)
    if re.match(r"^[0-9A-Z]{4}$", value):
        item_code_family.normalize_suffix(value[-3:])
        return value
    raise ValueError(_("A family suffix must contain three letters/digits."))


def get_reserved_bom_managed_codes_for_suffix(suffix):
    return ["{0}{1}".format(prefix, _code_tail(suffix)) for prefix in RESERVED_BOM_MANAGED_PREFIXES]


def build_bom_managed_item_code(item_group, suffix, item_type=None, has_bom=None):
    normalized_group = normalize_bom_managed_group(item_group)
    variant = normalize_bom_managed_variant(normalized_group, item_type=item_type, has_bom=has_bom)
    prefix = BOM_MANAGED_PREFIXES[normalized_group][variant]
    return "{0}{1}".format(prefix, _code_tail(suffix))


def get_bom_managed_family_codes(suffix):
    return {
        "plug_component": build_bom_managed_item_code("Plug", suffix, item_type="Component"),
        "plug_sub_assembly": build_bom_managed_item_code("Plug", suffix, item_type="Sub-Assembly"),
        "seat_component": build_bom_managed_item_code("Valve Seat", suffix, item_type="Component"),
        "seat_sub_assembly": build_bom_managed_item_code("Valve Seat", suffix, item_type="Sub-Assembly"),
        "head": build_bom_managed_item_code("Valve Head", suffix, item_type="Sub-Assembly"),
    }


def get_sub_assembly_item_code_for_component(item_group, component_item_code):
    normalized_group = normalize_bom_managed_group(item_group)
    if normalized_group not in REUSABLE_COMPONENT_GROUPS:
        raise ValueError(_("Only Plug and Valve Seat components can be reused for a sub-assembly."))

    component_item_code = (component_item_code or "").strip()
    component_prefix = BOM_MANAGED_PREFIXES[normalized_group]["component"]
    sub_assembly_prefix = BOM_MANAGED_PREFIXES[normalized_group]["sub-assembly"]
    if (
        len(component_item_code) != 6
        or not component_item_code.startswith(component_prefix)
        or not re.match(r"^[0-9A-Z]{6}$", component_item_code)
    ):
        raise ValueError(
            _("Component Item Code must start with {0} and contain exactly six letters/digits.").format(
                component_prefix
            )
        )

    return "{0}{1}".format(sub_assembly_prefix, component_item_code[2:])


def get_next_available_bom_managed_suffix(existing_codes):
    return item_code_family.next_available_suffix(existing_codes)


def get_existing_bom_managed_item_codes():
    rows = frappe.db.sql(
        """
        SELECT item_code
        FROM `tabItem`
        WHERE item_code REGEXP '^(10|11|20|21|30)[0-9]{4}$'
        """,
        as_dict=True,
    )
    return [row["item_code"] for row in rows]


def get_highest_bom_managed_suffix(existing_codes=None):
    occupied_codes = get_existing_bom_managed_item_codes() if existing_codes is None else existing_codes
    suffixes = [int(item_code[-4:]) for item_code in occupied_codes if item_code and item_code[-4:].isdigit()]
    return max(suffixes) if suffixes else 0


@frappe.whitelist()
def get_reusable_bom_managed_components(item_group, tag_raw_mat=None, limit=20):
    try:
        normalized_group = normalize_bom_managed_group(item_group)
        if normalized_group not in REUSABLE_COMPONENT_GROUPS:
            return []
        return _get_reusable_bom_managed_components(normalized_group, tag_raw_mat, limit)
    except ValueError as exc:
        frappe.throw(str(exc))


@frappe.whitelist()
def suggest_bom_managed_item_code(
    item_group,
    item_type=None,
    has_bom=None,
    tag_raw_mat=None,
    reuse_component_item=None,
    source_document=None,
):
    try:
        normalized_group = normalize_bom_managed_group(item_group)
        variant = normalize_bom_managed_variant(normalized_group, item_type=item_type, has_bom=has_bom)
        suggested_item_type = "Sub-Assembly" if variant == "sub-assembly" else "Component"
        reusable_components = []
        selected_component = None
        tag_raw_mat = (tag_raw_mat or "").strip()

        if variant == "sub-assembly" and normalized_group in REUSABLE_COMPONENT_GROUPS:
            reusable_components = _get_reusable_bom_managed_components(normalized_group, tag_raw_mat)

        if reuse_component_item:
            if not (variant == "sub-assembly" and normalized_group in REUSABLE_COMPONENT_GROUPS):
                raise ValueError(_("An existing component can only be reused for Plug and Valve Seat sub-assemblies."))

            selected_component = _get_reusable_component_details(normalized_group, reuse_component_item)
            if tag_raw_mat and selected_component.get("tag_raw_mat") and tag_raw_mat != selected_component.get("tag_raw_mat"):
                raise ValueError(
                    _("Component Item {0} uses Raw Material Tag {1}, not {2}.").format(
                        selected_component.get("item_code"),
                        selected_component.get("tag_raw_mat"),
                        tag_raw_mat,
                    )
                )

            suffix = selected_component["code_tail"]
            tag_raw_mat = selected_component.get("tag_raw_mat") or tag_raw_mat
        else:
            suffix = item_code_family.suggest_suffix()
            if source_document:
                source = frappe.get_doc("Item Creation", source_document)
                source.check_permission("write")
                if (source.docstatus == 0 and source.head_check == "Yes" and source.head_code
                        and item_code_family.is_reserved_for(source.head_code[-3:], (source.doctype, source.name))):
                    suffix = source.head_code[2:]

        family_codes = get_bom_managed_family_codes(suffix)
        item_code = build_bom_managed_item_code(
            normalized_group,
            suffix,
            item_type=suggested_item_type,
            has_bom=has_bom,
        )

        return {
            "item_group": normalized_group,
            "item_type": suggested_item_type if normalized_group != "Valve Head" else "Sub-Assembly",
            "family_suffix": suffix[-3:],
            "item_code": item_code,
            "family_codes": family_codes,
            "reserved_codes": _get_reserved_codes_for_suggestion(
                suffix, normalized_group, variant, selected_component
            ),
            "tag_raw_mat": tag_raw_mat,
            "reuse_component_item": selected_component.get("item_code") if selected_component else "",
            "reuse_component_item_name": selected_component.get("item_name") if selected_component else "",
            "reuse_sub_assembly_item_code": item_code if selected_component else "",
            "reuse_candidates": reusable_components,
            "rule": _get_bom_managed_suggestion_rule(selected_component),
        }
    except ValueError as exc:
        frappe.throw(str(exc))


def _get_reserved_codes_for_suggestion(suffix, item_group, variant, selected_component=None):
    if selected_component:
        return [
            selected_component["item_code"],
            build_bom_managed_item_code(item_group, suffix, has_bom=1),
        ]
    return get_reserved_bom_managed_codes_for_suffix(suffix)


def _get_bom_managed_suggestion_rule(selected_component=None):
    if selected_component:
        return _(
            "The sub-assembly reuses the suffix from existing component Item {0}."
        ).format(selected_component["item_code"])
    return _(
        "The final three characters are accepted only when unused across all Product, head, sub-assembly and component variants, including retired codes and reservations."
    )


def _get_reusable_component_details(item_group, component_item_code):
    component_item_code = (component_item_code or "").strip()
    sub_assembly_item_code = get_sub_assembly_item_code_for_component(item_group, component_item_code)
    values = frappe.db.get_value(
        "Item",
        component_item_code,
        ["item_code", "item_name", "item_group", "tag_raw_mat", "reference_code", "disabled"],
        as_dict=True,
    )
    if not values:
        raise ValueError(_("Component Item {0} does not exist.").format(component_item_code))
    if values.get("item_group") != item_group:
        raise ValueError(
            _("Component Item {0} belongs to Item Group {1}, not {2}.").format(
                component_item_code,
                values.get("item_group"),
                item_group,
            )
        )
    if values.get("disabled"):
        raise ValueError(_("Component Item {0} is disabled.").format(component_item_code))
    if not (values.get("tag_raw_mat") or "").strip():
        raise ValueError(_("Component Item {0} has no Raw Material Tag.").format(component_item_code))
    if frappe.db.exists("Item", sub_assembly_item_code):
        raise ValueError(
            _("Sub-assembly Item {0} already exists for component Item {1}.").format(
                sub_assembly_item_code,
                component_item_code,
            )
        )

    return {
        "item_code": values.get("item_code") or component_item_code,
        "item_name": values.get("item_name") or "",
        "tag_raw_mat": (values.get("tag_raw_mat") or "").strip(),
        "reference_code": values.get("reference_code") or "",
        "family_suffix": component_item_code[-3:],
        "code_tail": component_item_code[2:],
        "sub_assembly_item_code": sub_assembly_item_code,
    }


def _get_reusable_bom_managed_components(item_group, tag_raw_mat=None, limit=20):
    component_prefix = BOM_MANAGED_PREFIXES[item_group]["component"]
    sub_assembly_prefix = BOM_MANAGED_PREFIXES[item_group]["sub-assembly"]
    tag_raw_mat = (tag_raw_mat or "").strip()
    limit = max(1, min(int(limit or 20), 50))
    conditions = [
        "component.item_group = %(item_group)s",
        "IFNULL(component.disabled, 0) = 0",
        "component.item_code REGEXP %(component_pattern)s",
        "IFNULL(component.tag_raw_mat, '') != ''",
        """
        NOT EXISTS (
            SELECT 1
            FROM `tabItem` sub_assembly
            WHERE sub_assembly.item_code = CONCAT(%(sub_assembly_prefix)s, SUBSTRING(component.item_code, 3))
        )
        """,
    ]
    values = {
        "item_group": item_group,
        "component_pattern": "^{0}[0-9A-Z]{{4}}$".format(component_prefix),
        "sub_assembly_prefix": sub_assembly_prefix,
    }
    if tag_raw_mat:
        conditions.append("component.tag_raw_mat = %(tag_raw_mat)s")
        values["tag_raw_mat"] = tag_raw_mat

    rows = frappe.db.sql(
        """
        SELECT
            component.item_code,
            component.item_name,
            component.tag_raw_mat,
            component.reference_code,
            CONCAT(%(sub_assembly_prefix)s, SUBSTRING(component.item_code, 3)) AS sub_assembly_item_code
        FROM `tabItem` component
        WHERE {conditions}
        ORDER BY component.modified DESC, component.item_code DESC
        LIMIT {limit}
        """.format(conditions=" AND ".join(conditions), limit=limit),
        values,
        as_dict=True,
    )

    return [
        {
            "item_code": row.get("item_code"),
            "item_name": row.get("item_name") or "",
            "tag_raw_mat": (row.get("tag_raw_mat") or "").strip(),
            "reference_code": row.get("reference_code") or "",
            "family_suffix": row.get("item_code", "")[-3:],
            "sub_assembly_item_code": row.get("sub_assembly_item_code") or "",
        }
        for row in rows
    ]

@frappe.whitelist()
def populate_fields(head_name):
    """Suggest ordinary names; custom designs require explicit reviewed fields."""
    from amf.amf.utils.item_learned_defaults import build_item_description
    result = dict(seat_name="", plug_name="", head_rnd="", head_description="",
                  head_group="Valve Head", seat_mat="", plug_mat="", custom_definition=False)
    parts = (head_name or "").strip().split("-")
    if len(parts) < 7 or not parts[2].isdigit() or not parts[3].isdigit():
        result["custom_definition"] = True
        return result
    seat_materials = dict(material_map, U="PEI", E="EPDM-E", PFG="PTFE Food Grade")
    plug_materials = dict(material_map, E="EPDM-E", PFG="PTFE Food Grade")
    result.update(seat_name="SEAT-" + "-".join(parts[1:6]) + ("-" + "-".join(parts[7:]) if len(parts) > 7 else ""),
        plug_name="PLUG-" + "-".join(parts[1:5] + [parts[6]]),
        head_rnd="V-" + "-".join(parts[1:]), seat_mat=seat_materials.get(parts[5], ""),
        plug_mat=plug_materials.get(parts[6], ""),
        head_description=build_item_description("", head_name, "Valve Head"))
    return result


@frappe.whitelist()
def populate_fields_from_existing_item(item_code):
    """
    Fetches item details from an existing Item document based on the provided item_code.

    Args:
        item_code (str): The code of the item to fetch.
    
    Returns:
        dict: A dictionary containing 'item_name', 'Seat_name', Plug_name', Seat_code', 'Plug_code',
             'item_group', 'reference_code', and 'description'.                                     
    """
    item = frappe.get_doc("Item", item_code)
    item.check_permission("read")
    if item.disabled or item.item_group != "Valve Head":
        frappe.throw(_("Select an enabled Valve Head."))
    components = {"Plug": [], "Valve Seat": []}
    if item.default_bom:
        bom = frappe.get_doc("BOM", item.default_bom)
        if bom.item == item.name and bom.docstatus == 1 and bom.is_active:
            for row in bom.items:
                group = frappe.db.get_value("Item", row.item_code, "item_group")
                if group in components:
                    components[group].append(row)
    seat = components["Valve Seat"][0] if len(components["Valve Seat"]) == 1 else None
    plug = components["Plug"][0] if len(components["Plug"]) == 1 else None
    return {
        "head_code": item.name, "head_name": item.item_name,
        "head_group": item.item_group, "head_rnd": item.reference_code,
        "head_description": item.description,
        "seat_code": seat.item_code if seat else "",
        "seat_name": seat.item_name if seat else "",
        "plug_code": plug.item_code if plug else "",
        "plug_name": plug.item_name if plug else "",
    }

def get_item_from_name(item_name):
    """Helper function to get item_code from item_name."""
    try:
        item_code = frappe.db.get_value(
            "Item",
            filters={
                "item_name": item_name,
                "disabled": 0,
                "item_code": ["like", "_10%"],
            },
            fieldname="item_code",           
        )

        if not item_code:
            frappe.throw(f"No active item found for name '{item_name}' with matching code pattern.")
        return item_code
    
    except Exception as e:
        frappe.throw(f"Failed to retrieve item code for item name {item_name}: {e}")
        return None


@frappe.whitelist()
def get_last_item_code(*args, **kwargs):
    """
    Legacy helper kept for compatibility with older callers.
    Returns the highest occupied 4-digit suffix among the managed Plug/Seat/Head codes.
    """
    return get_highest_bom_managed_suffix()
        

@frappe.whitelist()
def get_data_for_preview(doc, group=None):
    from amf.amf.utils.item_creation_workflow import get_creation_plan
    plan = get_creation_plan(doc)
    prefixes = {"rvm": ("41", "42"), "pump": ("45", "47", "49", "4B"),
                "pump_hv": ("46", "48", "4A", "4C")}.get(group)
    if not prefixes:
        frappe.throw(_("Select a supported product family."))
    return [dict(item_code=row["item"]["item_code"], item_name=row["item"]["item_name"])
            for row in plan["actions"] if row["item"]["item_code"].startswith(prefixes)]


@frappe.whitelist(methods=["POST"])
def create_item_from_doc(doc, group=None):
    """Reject legacy per-group creation; submission owns the whole transaction."""
    frappe.throw(_("Save and submit Item Creation to create its complete reserved family. Separate group creation is no longer supported."))


# Compatibility wrappers for existing internal callers. The planner uses pure
# recipe functions directly and supplies preloaded dependency records.
def _prepare_simple_component_data(doc, group):
    from amf.amf.utils.item_creation_recipes import component_definition
    return component_definition(doc, group)


def _legacy_product_recipe(doc, motor, token, syringe_reference=None):
    from amf.amf.utils.item_creation_compatibility import BY_KEY
    from amf.amf.utils.item_creation_recipes import product_definition
    body = "5" + str(motor) + "1000"
    syringe = "70" + token + "000" if token != "0" else ""
    rule = BY_KEY.get(body + ":" + syringe)
    if not rule:
        frappe.throw(_("Unsupported product configuration; choose a reviewed compatible variant."))
    reference = syringe_reference or (frappe.db.get_value("Item", syringe, "reference_code") if syringe else "")
    return product_definition(doc, rule, dict(name=body), dict(reference_code=reference) if syringe else None)


def _prepare_rvm_data(doc, motor_info):
    data, materials, _scraps = _legacy_product_recipe(doc, str(int(motor_info) + 1), "0")
    return data, materials


def _prepare_pump_data(doc, motor_code, syringe_code, syringe_reference=None):
    return _legacy_product_recipe(doc, motor_code, syringe_code, syringe_reference)


def _prepare_pump_hv_data(doc, motor_code, syringe_code, syringe_reference=None):
    data, materials, _scraps = _legacy_product_recipe(doc, motor_code, syringe_code, syringe_reference)
    return data, materials
