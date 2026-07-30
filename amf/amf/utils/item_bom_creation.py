# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import re

import frappe
from frappe import _
from frappe.utils import flt

from amf.amf.utils.item_learned_defaults import build_item_description


ITEM_GROUP_RULES = {
	"Plug": {
		"component_prefix": "10",
		"sub_assembly_prefix": "11",
		"raw_material_qty": 0.02,
		"accessory_item": "SPL.3013",
	},
	"Valve Seat": {
		"component_prefix": "20",
		"sub_assembly_prefix": "21",
		"raw_material_qty": 0.03,
		"accessory_item": "SPL.3039",
	},
}

RAW_MATERIAL_ITEM_GROUP = "Raw Material"


@frappe.whitelist()
def get_bom_creation_plan(
	item_code,
	item_group,
	tag_raw_mat,
	item_name=None,
	raw_material=None,
	accessory_item=None,
	accessory_qty=None,
):
	"""Build the plan displayed before the new Item is saved."""
	context = _get_creation_context(item_code, item_group, tag_raw_mat)
	component_bom = _get_existing_bom(context["component_item_code"])
	needs_raw_material = not bool(component_bom)
	candidates = []
	selected_raw_material = ""

	if needs_raw_material:
		candidates = get_raw_material_candidates(context["tag_raw_mat"])
		if not candidates:
			frappe.throw(
				_("No enabled Raw Material Item has Raw Material Tag {0}.").format(
					frappe.bold(context["tag_raw_mat"])
				)
			)

		candidate_names = [row["name"] for row in candidates]
		if raw_material and raw_material not in candidate_names:
			frappe.throw(
				_("Raw Material {0} does not match Raw Material Tag {1}.").format(
					frappe.bold(raw_material),
					frappe.bold(context["tag_raw_mat"]),
				)
			)

		selected_raw_material = raw_material or (candidate_names[0] if len(candidate_names) == 1 else "")

	rule = context["rule"]
	plan = {
		"item_code": context["item_code"],
		"item_group": context["item_group"],
		"layer": context["layer"],
		"is_sub_assembly": context["layer"] == "sub_assembly",
		"component_item_code": context["component_item_code"],
		"component_item_exists": context["component_item_exists"],
		"component_bom": component_bom,
		"needs_raw_material": needs_raw_material,
		"tag_raw_mat": context["tag_raw_mat"],
		"raw_material_qty": rule["raw_material_qty"],
		"raw_material": selected_raw_material,
		"raw_material_candidates": candidates,
	}

	if plan["is_sub_assembly"]:
		selected_accessory_item = (accessory_item or rule["accessory_item"] or "").strip()
		_validate_accessory_item(selected_accessory_item)
		plan.update({
			"upper_bom": _get_existing_bom(context["item_code"]),
			"component_qty": 1,
			"accessory_item": selected_accessory_item,
			"accessory_qty": _get_accessory_qty_suggestion(
				context["item_group"], item_name, accessory_qty
			),
		})

	return plan


@frappe.whitelist()
def create_item_boms_after_save(
	item_code,
	raw_material=None,
	accessory_item=None,
	accessory_qty=None,
):
	"""Create the base BOM, and the upper BOM too when item_code is an x1 Item."""
	item_code = (item_code or "").strip()
	if not frappe.db.exists("Item", item_code):
		frappe.throw(_("Save Item {0} before creating its BOM.").format(frappe.bold(item_code)))

	item = frappe.get_doc("Item", item_code)
	item.check_permission("write")
	_lock_item(item.name)

	context = _get_creation_context(
		item.item_code or item.name,
		item.item_group,
		item.get("tag_raw_mat"),
	)

	if context["layer"] == "component":
		bom_name, bom_created = _ensure_component_raw_material_bom(
			item,
			context,
			raw_material,
		)
		return {
			"layer": "component",
			"component_item": item.name,
			"component_item_created": False,
			"component_bom": bom_name,
			"component_bom_created": bom_created,
		}

	return _create_sub_assembly_chain(
		item,
		context,
		raw_material,
		accessory_item,
		accessory_qty,
	)


def _create_sub_assembly_chain(
	upper_item,
	context,
	raw_material,
	accessory_item=None,
	accessory_qty=None,
):
	rule = context["rule"]
	accessory_item = (accessory_item or rule["accessory_item"] or "").strip()
	_validate_accessory_item(accessory_item)
	accessory_qty = _normalize_accessory_qty(
		context["item_group"], upper_item.item_name, accessory_qty
	)

	component_item, component_item_created = _ensure_component_item(upper_item, context)
	_validate_component_item(component_item, context)

	component_bom, component_bom_created = _ensure_component_raw_material_bom(
		component_item,
		context,
		raw_material,
	)
	upper_bom, upper_bom_created = _ensure_bom(
		upper_item,
		[
			{
				"item_code": component_item.name,
				"qty": 1,
				"bom_no": component_bom,
			},
			{
				"item_code": accessory_item,
				"qty": accessory_qty,
			},
		],
	)

	return {
		"layer": "sub_assembly",
		"component_item": component_item.name,
		"component_item_created": component_item_created,
		"component_bom": component_bom,
		"component_bom_created": component_bom_created,
		"upper_bom": upper_bom,
		"upper_bom_created": upper_bom_created,
	}


def _ensure_component_raw_material_bom(component_item, context, raw_material):
	existing_bom = _get_existing_bom(component_item.name)
	if existing_bom:
		return existing_bom, False

	_validate_raw_material(raw_material, context["tag_raw_mat"])
	return _ensure_bom(
		component_item,
		[{
			"item_code": raw_material,
			"qty": context["rule"]["raw_material_qty"],
		}],
	)


def _get_creation_context(item_code, item_group, tag_raw_mat):
	item_code = (item_code or "").strip()
	item_group = (item_group or "").strip()
	rule = ITEM_GROUP_RULES.get(item_group)
	if not rule:
		frappe.throw(_("Automatic BOM creation is only available for Plug and Valve Seat Items."))

	if not re.match(r"^[0-9]{6}$", item_code):
		frappe.throw(_("Item Code must contain exactly six digits for automatic BOM creation."))

	prefix = item_code[:2]
	if prefix == rule["component_prefix"]:
		layer = "component"
	elif prefix == rule["sub_assembly_prefix"]:
		layer = "sub_assembly"
	else:
		frappe.throw(
			_("Item Code {0} does not match Item Group {1} or a supported BOM layer.").format(
				frappe.bold(item_code), frappe.bold(item_group)
			)
		)

	component_item_code = rule["component_prefix"] + item_code[2:]
	component_item_exists = bool(frappe.db.exists("Item", component_item_code))
	component_tag = ""
	if component_item_exists:
		component_tag = frappe.db.get_value("Item", component_item_code, "tag_raw_mat") or ""

	tag_raw_mat = (tag_raw_mat or "").strip()
	if tag_raw_mat and component_tag and tag_raw_mat != component_tag:
		frappe.throw(
			_("Item {0} uses Raw Material Tag {1}, which differs from {2} on Item {3}.").format(
				frappe.bold(item_code),
				frappe.bold(tag_raw_mat),
				frappe.bold(component_tag),
				frappe.bold(component_item_code),
			)
		)

	effective_tag = component_tag or tag_raw_mat
	if not effective_tag:
		frappe.throw(_("Set Raw Material Tag before creating the BOM."))

	return {
		"item_code": item_code,
		"item_group": item_group,
		"layer": layer,
		"component_item_code": component_item_code,
		"component_item_exists": component_item_exists,
		"tag_raw_mat": effective_tag,
		"rule": rule,
	}


def get_raw_material_candidates(tag_raw_mat):
	return frappe.get_all(
		"Item",
		filters={
			"item_group": RAW_MATERIAL_ITEM_GROUP,
			"tag_raw_mat": tag_raw_mat,
			"disabled": 0,
		},
		fields=["name", "item_name"],
		order_by="name asc",
	)


def _validate_raw_material(raw_material, tag_raw_mat):
	raw_material = (raw_material or "").strip()
	if not raw_material:
		frappe.throw(_("Select a Raw Material Item before saving."))

	values = frappe.db.get_value(
		"Item",
		raw_material,
		["item_group", "tag_raw_mat", "disabled"],
		as_dict=True,
	)
	if not values or values.disabled or values.item_group != RAW_MATERIAL_ITEM_GROUP:
		frappe.throw(_("Raw Material {0} is missing, disabled, or not in the Raw Material Item Group.").format(
			frappe.bold(raw_material)
		))
	if (values.tag_raw_mat or "").strip() != tag_raw_mat:
		frappe.throw(_("Raw Material {0} does not have Raw Material Tag {1}.").format(
			frappe.bold(raw_material), frappe.bold(tag_raw_mat)
		))


def _validate_accessory_item(accessory_item):
	if not frappe.db.exists("Item", accessory_item):
		frappe.throw(_("Accessory Item {0} does not exist.").format(frappe.bold(accessory_item)))
	if frappe.db.get_value("Item", accessory_item, "disabled"):
		frappe.throw(_("Accessory Item {0} is disabled.").format(frappe.bold(accessory_item)))


def _normalize_accessory_qty(item_group, item_name, accessory_qty=None):
	qty = _get_accessory_qty_suggestion(item_group, item_name, accessory_qty)
	if qty <= 0:
		frappe.throw(_("Set a positive accessory quantity for the sub-assembly BOM."))
	return qty


def _get_accessory_qty_suggestion(item_group, item_name, accessory_qty=None):
	if accessory_qty not in (None, ""):
		qty = flt(accessory_qty)
	elif item_group == "Valve Seat":
		qty = 2
	else:
		parts = (item_name or "").split("-")
		qty = flt(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
	return qty


def _ensure_component_item(upper_item, context):
	component_item_code = context["component_item_code"]
	if frappe.db.exists("Item", component_item_code):
		return frappe.get_doc("Item", component_item_code), False

	upper_reference_code = (upper_item.get("reference_code") or "").strip()
	component_reference_code = _get_component_reference_code(upper_reference_code)
	if upper_reference_code and component_reference_code == upper_reference_code:
		frappe.throw(
			_("Sub-assembly Reference Code must end with .ASM before creating its component Item.")
		)

	component = frappe.copy_doc(upper_item)
	component.item_code = component_item_code
	component.item_type = "Component"
	component.reference_code = component_reference_code
	component.reference_name = "{0}: {1}".format(component_item_code, upper_item.item_name)
	component.default_bom = None

	_clear_if_present(component, "item_default_bom")
	_clear_if_present(component, "bom_cost")
	_clear_if_present(component, "qrcode")
	_clear_table_if_present(component, "bom_table")

	if component.meta.has_field("drawing_item"):
		for row in component.get("drawing_item") or []:
			row.item_code = component_item_code
			row.item_name = component.item_name
			row.reference_code = component.reference_code

	component.description = build_item_description(
		item_code=component.item_code,
		item_name=component.item_name,
		item_group=component.item_group,
		item_type=component.item_type,
		reference_code=component.reference_code,
	)
	component.insert(ignore_permissions=True)
	return component, True


def _validate_component_item(component_item, context):
	if component_item.item_group != context["item_group"]:
		frappe.throw(_("Component Item {0} belongs to Item Group {1}, not {2}.").format(
			frappe.bold(component_item.name),
			frappe.bold(component_item.item_group),
			frappe.bold(context["item_group"]),
		))
	component_tag = (component_item.get("tag_raw_mat") or "").strip()
	if component_tag != context["tag_raw_mat"]:
		frappe.throw(_("Component Item {0} must use Raw Material Tag {1}.").format(
			frappe.bold(component_item.name), frappe.bold(context["tag_raw_mat"])
		))


def _get_component_reference_code(reference_code):
	reference_code = (reference_code or "").strip()
	if reference_code.upper().endswith(".ASM"):
		return reference_code[:-4]
	return reference_code


def _ensure_bom(item, materials):
	existing_bom = _get_existing_bom(item.name)
	if existing_bom:
		return existing_bom, False

	bom = frappe.get_doc({
		"doctype": "BOM",
		"item": item.name,
		"quantity": 1,
		"company": _get_item_company(item),
		"is_active": 1,
		"is_default": 1,
		"with_operations": 0,
		"rm_cost_as_per": "Valuation Rate",
		"items": materials,
	})
	bom.insert(ignore_permissions=True)
	bom.submit()
	return bom.name, True


def _get_existing_bom(item_code):
	rows = frappe.get_all(
		"BOM",
		filters={"item": item_code, "docstatus": 1, "is_active": 1},
		fields=["name"],
		order_by="is_default desc, modified desc",
		limit_page_length=1,
	)
	return rows[0]["name"] if rows else ""


def _get_item_company(item):
	for row in item.get("item_defaults") or []:
		if row.company:
			return row.company
	return frappe.defaults.get_user_default("Company") or frappe.defaults.get_global_default("company")


def _clear_if_present(doc, fieldname):
	if doc.meta.has_field(fieldname):
		doc.set(fieldname, None)


def _clear_table_if_present(doc, fieldname):
	if doc.meta.has_field(fieldname):
		doc.set(fieldname, [])


def _lock_item(item_code):
	frappe.db.sql("SELECT name FROM `tabItem` WHERE name = %s FOR UPDATE", item_code)
