# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from collections import OrderedDict

import frappe
from frappe import _
from frappe.desk.reportview import get_match_cond
from frappe.utils import cint, cstr, flt, strip_html_tags


ALLOWED_ROLES = {
	"Stock User",
	"Stock Manager",
	"Manufacturing User",
	"Manufacturing Manager",
	"System Manager",
}
MAX_DEPTH = 12
MAX_NODES = 1500
WAREHOUSE_SECTION_ORDER = {
	"Production": 0,
	"Inventory": 1,
	"External Warehouse": 2,
	"Other": 3,
}


@frappe.whitelist()
def search_items(query=None, limit=12):
	"""Return ranked, permission-filtered Item suggestions for the dashboard."""
	_assert_dashboard_access()

	query = cstr(query).strip()
	if len(query) < 2:
		return []

	limit = max(1, min(cint(limit) or 12, 25))
	item_meta = frappe.get_meta("Item")
	has_reference_code = bool(item_meta.has_field("reference_code"))

	search_conditions = [
		"tabItem.name like %(txt)s",
		"tabItem.item_code like %(txt)s",
		"tabItem.item_name like %(txt)s",
		"tabItem.item_group like %(txt)s",
		"ifnull(tabItem.brand, '') like %(txt)s",
		"ifnull(tabItem.description, '') like %(txt)s",
		"tabItem.item_code in (select parent from `tabItem Barcode` where barcode like %(txt)s)",
		"tabItem.item_code in (select parent from `tabItem Supplier` where supplier_part_no like %(txt)s)",
		"tabItem.item_code in (select parent from `tabItem Manufacturer` where manufacturer_part_no like %(txt)s)",
	]
	reference_select = "'' as reference_code"
	reference_order = ""
	if has_reference_code:
		search_conditions.append("ifnull(tabItem.reference_code, '') like %(txt)s")
		reference_select = "ifnull(tabItem.reference_code, '') as reference_code"
		reference_order = "when tabItem.reference_code = %(exact)s then 2 "

	rows = frappe.db.sql(
		"""
		select
			tabItem.name as item_code,
			tabItem.item_name,
			tabItem.item_group,
			tabItem.stock_uom,
			tabItem.description,
			tabItem.image,
			tabItem.default_bom,
			{reference_select}
		from tabItem
		where tabItem.docstatus < 2
			and tabItem.disabled = 0
			and tabItem.has_variants = 0
			and ({search_conditions})
			{match_conditions}
		order by
			case
				when tabItem.name = %(exact)s then 0
				when tabItem.item_code = %(exact)s then 1
				{reference_order}
				when tabItem.item_name = %(exact)s then 3
				when tabItem.item_code like %(prefix)s then 4
				when tabItem.item_name like %(prefix)s then 5
				else 6
			end,
			tabItem.item_code asc
		limit {limit}
		""".format(
			reference_select=reference_select,
			search_conditions=" or ".join(search_conditions),
			match_conditions=get_match_cond("Item").replace("%", "%%"),
			reference_order=reference_order,
			limit=limit,
		),
		{
			"txt": "%{0}%".format(query),
			"prefix": "{0}%".format(query),
			"exact": query,
		},
		as_dict=True,
	)

	for row in rows:
		row.description = _plain_text(row.description, 140)

	return rows


@frappe.whitelist()
def get_dashboard(item_code=None, quantity=1):
	"""Build a recursive BOM and stock snapshot for one selected Item."""
	_assert_dashboard_access()

	item_code = cstr(item_code).strip()
	quantity = flt(quantity)
	if not item_code:
		frappe.throw(_("Please select an Item."))
	if quantity <= 0:
		frappe.throw(_("Quantity must be greater than zero."))

	item = frappe.get_doc("Item", item_code)
	frappe.has_permission("Item", ptype="read", doc=item, throw=True)
	if item.disabled:
		frappe.throw(_("Item {0} is disabled.").format(item_code))

	builder = InventoryDashboardBuilder(item_code, quantity)
	return builder.build()


class InventoryDashboardBuilder(object):
	def __init__(self, item_code, quantity):
		self.item_code = item_code
		self.quantity = quantity
		self.nodes = []
		self.warnings = []
		self._warning_keys = set()
		self._bom_cache = {}
		self._resolved_bom_cache = {}
		self._item_default_bom_cache = {}
		self._node_sequence = 0

	def build(self):
		root_bom = self._resolve_bom(self.item_code)
		root = self._append_node(
			item_code=self.item_code,
			required_qty=self.quantity,
			level=0,
			parent_id=None,
			bom_no=root_bom,
			is_root=True,
		)

		if root_bom:
			self._append_bom_children(
				root,
				root_bom,
				bom_path=(root_bom,),
				item_path=(self.item_code,),
			)
		else:
			self._add_warning(
				"missing-root-bom",
				_("No active, submitted BOM was found for {0}.").format(self.item_code),
			)

		item_map = self._get_item_map()
		stock_data, stock_totals, warehouses = self._get_stock_data(item_map)
		self._enrich_nodes(item_map, stock_totals)
		requirements = self._aggregate_requirements(item_map, stock_totals)

		root_item = item_map.get(self.item_code, {})
		root_item = dict(root_item)
		root_item.update({
			"item_code": self.item_code,
			"bom_no": root_bom,
			"requested_qty": self.quantity,
		})

		shortages = [row for row in requirements if row.get("shortage_qty", 0) > 0]
		return {
			"root_item": root_item,
			"nodes": self.nodes,
			"requirements": requirements,
			"shortages": shortages,
			"warehouses": warehouses,
			"stock_by_item": stock_data,
			"stock_totals": stock_totals,
			"summary": {
				"component_rows": max(len(self.nodes) - 1, 0),
				"unique_components": len(requirements),
				"shortage_items": len(shortages),
				"warehouse_count": len(warehouses),
				"bom_levels": max([node["level"] for node in self.nodes] or [0]),
			},
			"warnings": self.warnings,
			"limits": {
				"max_depth": MAX_DEPTH,
				"max_nodes": MAX_NODES,
			},
		}

	def _append_bom_children(self, parent_node, bom_no, bom_path, item_path):
		bom = self._get_bom(bom_no)
		if not bom:
			return

		bom_quantity = flt(bom.get("quantity"))
		if bom_quantity <= 0:
			bom_quantity = 1
			self._add_warning(
				"invalid-bom-qty:{0}".format(bom_no),
				_("BOM {0} has an invalid output quantity; quantity 1 was used.").format(bom_no),
			)

		for bom_item in bom.get("items", []):
			if len(self.nodes) >= MAX_NODES:
				parent_node["truncated"] = True
				self._add_warning(
					"node-limit",
					_("The structure was limited to {0} rows. Narrower branch loading can be added in the next iteration.").format(MAX_NODES),
				)
				return

			item_code = cstr(bom_item.get("item_code"))
			if not item_code:
				continue

			stock_qty = flt(bom_item.get("stock_qty"))
			if not stock_qty:
				stock_qty = flt(bom_item.get("qty")) * (flt(bom_item.get("conversion_factor")) or 1)
			qty_per_parent = stock_qty / bom_quantity
			required_qty = flt(parent_node.get("required_qty")) * qty_per_parent
			child_bom = self._resolve_bom(item_code, bom_item.get("bom_no"))

			node = self._append_node(
				item_code=item_code,
				required_qty=required_qty,
				level=parent_node["level"] + 1,
				parent_id=parent_node["id"],
				bom_no=child_bom,
				qty_per_parent=qty_per_parent,
				source_warehouse=bom_item.get("source_warehouse"),
				description=bom_item.get("description"),
				include_item_in_manufacturing=cint(bom_item.get("include_item_in_manufacturing")),
			)
			parent_node["has_children"] = True

			if not child_bom:
				continue
			if node["level"] >= MAX_DEPTH:
				node["truncated"] = True
				self._add_warning(
					"depth-limit",
					_("Some BOM branches reached the maximum depth of {0}.").format(MAX_DEPTH),
				)
				continue
			if child_bom in bom_path or item_code in item_path:
				node["cycle"] = True
				self._add_warning(
					"cycle:{0}".format(child_bom),
					_("A circular BOM reference involving {0} was stopped safely.").format(child_bom),
				)
				continue

			self._append_bom_children(
				node,
				child_bom,
				bom_path=bom_path + (child_bom,),
				item_path=item_path + (item_code,),
			)

	def _append_node(
		self,
		item_code,
		required_qty,
		level,
		parent_id,
		bom_no=None,
		qty_per_parent=None,
		source_warehouse=None,
		description=None,
		include_item_in_manufacturing=1,
		is_root=False,
	):
		node = {
			"id": "inventory-node-{0}".format(self._node_sequence),
			"parent_id": parent_id,
			"item_code": item_code,
			"required_qty": required_qty,
			"qty_per_parent": qty_per_parent,
			"level": level,
			"bom_no": bom_no,
			"is_sub_assembly": bool(bom_no),
			"is_root": is_root,
			"has_children": False,
			"source_warehouse": source_warehouse,
			"description": description,
			"include_item_in_manufacturing": include_item_in_manufacturing,
			"cycle": False,
			"truncated": False,
		}
		self._node_sequence += 1
		self.nodes.append(node)
		return node

	def _resolve_bom(self, item_code, preferred_bom=None):
		cache_key = (item_code, cstr(preferred_bom))
		if cache_key in self._resolved_bom_cache:
			return self._resolved_bom_cache[cache_key]

		candidate_names = []
		if preferred_bom:
			candidate_names.append(preferred_bom)

		default_bom = self._get_item_default_bom(item_code)
		if default_bom and default_bom not in candidate_names:
			candidate_names.append(default_bom)

		for candidate in candidate_names:
			bom = self._get_bom(candidate)
			if bom and bom.get("item") == item_code:
				self._resolved_bom_cache[cache_key] = candidate
				return candidate

		fallback = frappe.get_all(
			"BOM",
			filters={"item": item_code, "docstatus": 1, "is_active": 1},
			fields=["name"],
			order_by="is_default desc, modified desc",
			limit_page_length=1,
		)
		resolved = fallback[0].name if fallback else None
		self._resolved_bom_cache[cache_key] = resolved
		return resolved

	def _get_item_default_bom(self, item_code):
		if item_code not in self._item_default_bom_cache:
			self._item_default_bom_cache[item_code] = frappe.db.get_value("Item", item_code, "default_bom")
		return self._item_default_bom_cache[item_code]

	def _get_bom(self, bom_no):
		if not bom_no:
			return None
		if bom_no in self._bom_cache:
			return self._bom_cache[bom_no]

		header = frappe.db.get_value(
			"BOM",
			{"name": bom_no, "docstatus": 1, "is_active": 1},
			["name", "item", "quantity"],
			as_dict=True,
		)
		if not header:
			self._bom_cache[bom_no] = None
			return None

		header["items"] = frappe.get_all(
			"BOM Item",
			filters={"parent": bom_no, "parenttype": "BOM", "docstatus": 1},
			fields=[
				"item_code",
				"item_name",
				"description",
				"stock_qty",
				"qty",
				"conversion_factor",
				"stock_uom",
				"uom",
				"bom_no",
				"source_warehouse",
				"include_item_in_manufacturing",
				"idx",
			],
			order_by="idx asc",
			limit_page_length=0,
		)
		self._bom_cache[bom_no] = header
		return header

	def _get_item_map(self):
		item_codes = sorted(set(node["item_code"] for node in self.nodes))
		item_meta = frappe.get_meta("Item")
		fields = [
			"name as item_code",
			"item_name",
			"description",
			"item_group",
			"stock_uom",
			"image",
			"is_stock_item",
			"disabled",
			"default_bom",
		]
		if item_meta.has_field("reference_code"):
			fields.append("reference_code")

		item_map = {}
		for item_chunk in _chunks(item_codes, 300):
			for item in frappe.get_all(
				"Item",
				filters={"name": ["in", item_chunk]},
				fields=fields,
				limit_page_length=0,
			):
				item["description"] = _plain_text(item.get("description"), 240)
				item.setdefault("reference_code", "")
				item_map[item.item_code] = item
		return item_map

	def _get_stock_data(self, item_map):
		return get_stock_snapshot(item_map.keys())

	def _enrich_nodes(self, item_map, stock_totals):
		for node in self.nodes:
			item = item_map.get(node["item_code"], {})
			totals = stock_totals.get(node["item_code"], {})
			node["item_name"] = item.get("item_name") or node["item_code"]
			node["item_group"] = item.get("item_group") or ""
			node["stock_uom"] = item.get("stock_uom") or ""
			node["reference_code"] = item.get("reference_code") or ""
			node["image"] = item.get("image") or ""
			node["is_stock_item"] = cint(item.get("is_stock_item"))
			node["description"] = _plain_text(node.get("description") or item.get("description"), 240)
			node["total_actual_qty"] = flt(totals.get("actual_qty"))
			node["total_available_qty"] = flt(totals.get("available_qty"))
			node["total_projected_qty"] = flt(totals.get("projected_qty"))
			node["status"] = _availability_status(
				node["is_stock_item"],
				node["required_qty"],
				node["total_available_qty"],
			)

	def _aggregate_requirements(self, item_map, stock_totals):
		aggregated = OrderedDict()
		for node in self.nodes:
			if node.get("is_root"):
				continue
			item_code = node["item_code"]
			if item_code not in aggregated:
				item = item_map.get(item_code, {})
				aggregated[item_code] = {
					"item_code": item_code,
					"item_name": item.get("item_name") or item_code,
					"reference_code": item.get("reference_code") or "",
					"item_group": item.get("item_group") or "",
					"stock_uom": item.get("stock_uom") or "",
					"is_stock_item": cint(item.get("is_stock_item")),
					"required_qty": 0.0,
					"occurrences": 0,
					"levels": set(),
					"is_sub_assembly": False,
				}

			row = aggregated[item_code]
			row["required_qty"] += flt(node.get("required_qty"))
			row["occurrences"] += 1
			row["levels"].add(node.get("level"))
			row["is_sub_assembly"] = row["is_sub_assembly"] or node.get("is_sub_assembly")

		result = []
		for item_code, row in aggregated.items():
			totals = stock_totals.get(item_code, {})
			row["levels"] = sorted(row["levels"])
			row["total_actual_qty"] = flt(totals.get("actual_qty"))
			row["total_available_qty"] = flt(totals.get("available_qty"))
			row["total_projected_qty"] = flt(totals.get("projected_qty"))
			row["status"] = _availability_status(
				row["is_stock_item"], row["required_qty"], row["total_available_qty"]
			)
			row["shortage_qty"] = (
				max(row["required_qty"] - row["total_available_qty"], 0)
				if row["is_stock_item"]
				else 0
			)
			result.append(row)

		status_order = {"shortage": 0, "partial": 1, "available": 2, "non_stock": 3}
		return sorted(
			result,
			key=lambda row: (status_order.get(row["status"], 9), cstr(row["item_code"]).lower()),
		)

	def _add_warning(self, key, message):
		if key not in self._warning_keys:
			self._warning_keys.add(key)
			self.warnings.append(message)


def _assert_dashboard_access():
	if frappe.session.user == "Guest":
		frappe.throw(_("Please sign in to use the Global Inventory Dashboard."), frappe.PermissionError)
	if frappe.session.user == "Administrator":
		return
	if not ALLOWED_ROLES.intersection(set(frappe.get_roles())):
		frappe.throw(_("You do not have access to the Global Inventory Dashboard."), frappe.PermissionError)


def _availability_status(is_stock_item, required_qty, available_qty):
	if not cint(is_stock_item):
		return "non_stock"
	if flt(available_qty) >= flt(required_qty):
		return "available"
	if flt(available_qty) > 0:
		return "partial"
	return "shortage"


def _get_warehouse_section(warehouse, warehouse_map):
	"""Classify a leaf by its warehouse-tree branch for dashboard column ordering."""
	section_names = {
		"production": "Production",
		"inventory": "Inventory",
		"external warehouse": "External Warehouse",
	}
	current = warehouse
	visited = set()
	while current and current.name not in visited:
		visited.add(current.name)
		label = cstr(current.warehouse_name or current.name).strip().lower()
		if label in section_names:
			return section_names[label]
		current = warehouse_map.get(current.parent_warehouse)
	return "Other"


def get_stock_snapshot(item_codes):
	"""Return stock by item/warehouse, totals, and operationally ordered warehouses."""
	item_codes = sorted(set(cstr(item_code) for item_code in item_codes if item_code))
	bin_rows = []
	for item_chunk in _chunks(item_codes, 300):
		bin_rows.extend(
			frappe.get_all(
				"Bin",
				filters={"item_code": ["in", item_chunk]},
				fields=[
					"item_code",
					"warehouse",
					"actual_qty",
					"reserved_qty",
					"projected_qty",
					"ordered_qty",
				],
				limit_page_length=0,
			)
		)

	warehouse_names = set(row.warehouse for row in bin_rows if row.warehouse)
	all_warehouses = frappe.get_all(
		"Warehouse",
		filters={"disabled": 0},
		fields=["name", "warehouse_name", "parent_warehouse", "company", "is_group", "lft"],
		limit_page_length=0,
	)
	all_warehouse_map = {warehouse.name: warehouse for warehouse in all_warehouses}
	warehouse_map = {
		name: all_warehouse_map[name]
		for name in warehouse_names
		if name in all_warehouse_map and not cint(all_warehouse_map[name].is_group)
	}

	for warehouse in warehouse_map.values():
		warehouse["section"] = _get_warehouse_section(warehouse, all_warehouse_map)

	warehouses = sorted(
		warehouse_map.values(),
		key=lambda row: (
			WAREHOUSE_SECTION_ORDER.get(row.section, WAREHOUSE_SECTION_ORDER["Other"]),
			cint(row.lft),
			cstr(row.warehouse_name or row.name).lower(),
		),
	)
	warehouse_names = set(warehouse_map.keys())

	stock_data = OrderedDict((item_code, {}) for item_code in item_codes)
	stock_totals = OrderedDict()
	for item_code in item_codes:
		stock_totals[item_code] = {
			"actual_qty": 0.0,
			"reserved_qty": 0.0,
			"available_qty": 0.0,
			"projected_qty": 0.0,
			"ordered_qty": 0.0,
		}

	for row in bin_rows:
		if row.warehouse not in warehouse_names or row.item_code not in stock_data:
			continue
		actual_qty = flt(row.actual_qty)
		reserved_qty = flt(row.reserved_qty)
		values = {
			"actual_qty": actual_qty,
			"reserved_qty": reserved_qty,
			"available_qty": actual_qty - reserved_qty,
			"projected_qty": flt(row.projected_qty),
			"ordered_qty": flt(row.ordered_qty),
		}
		stock_data[row.item_code][row.warehouse] = values
		for fieldname, value in values.items():
			stock_totals[row.item_code][fieldname] += value

	return stock_data, stock_totals, warehouses


def _plain_text(value, max_length=None):
	text = " ".join(cstr(strip_html_tags(value or "")).split())
	if max_length and len(text) > max_length:
		return text[: max_length - 1].rstrip() + "…"
	return text


def _chunks(values, size):
	for index in range(0, len(values), size):
		yield values[index:index + size]
