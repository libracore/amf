# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from collections import OrderedDict, defaultdict

import frappe
from frappe import _
from frappe.desk.reportview import get_match_cond
from frappe.utils import cint, cstr, date_diff, flt, getdate, now_datetime, nowdate

from amf.amf.page.global_inventory_dashboard.global_inventory_dashboard import get_stock_snapshot


ALLOWED_ROLES = {
	"Sales User",
	"Sales Manager",
	"Stock User",
	"Stock Manager",
	"Manufacturing User",
	"Manufacturing Manager",
	"System Manager",
}
MAX_BOM_DEPTH = 12


@frappe.whitelist()
def get_dashboard(company=None, to_date=None, customer=None, include_on_hold=0):
	"""Return current stock coverage for outstanding submitted Sales Order demand."""
	_assert_projection_access()
	filters = _normalize_filters(company, to_date, customer, include_on_hold)

	sales_lines = _get_sales_order_lines(filters)
	packed_items = _get_packed_items(sales_lines)
	demand_lines = _build_demand_lines(sales_lines, packed_items)
	planner = SalesBOMPlanner()
	sold_item_codes = [row.item_code for row in demand_lines]
	all_item_codes = set(sold_item_codes)
	all_item_codes.update(planner.collect_item_codes(sold_item_codes))
	item_map = _get_item_map(all_item_codes)
	stock_by_item, stock_totals, warehouses = get_stock_snapshot(item_map.keys())

	component_lines = _plan_sales_and_materials(
		demand_lines, planner, item_map, stock_totals
	)
	items = _aggregate_items(demand_lines, item_map, stock_totals)
	component_items = _aggregate_component_items(component_lines, item_map, stock_totals)
	orders = _aggregate_orders(sales_lines, demand_lines, component_lines)
	shortages = [row for row in items if flt(row.shortage_qty) > 0]
	component_shortages = [
		row for row in component_items if flt(row.shortage_qty) > 0
	]
	currency = frappe.db.get_value("Company", filters.company, "default_currency") or ""

	return {
		"filters": {
			"company": filters.company,
			"to_date": cstr(filters.to_date) if filters.to_date else None,
			"customer": filters.customer,
			"include_on_hold": filters.include_on_hold,
		},
		"summary": _get_summary(
			orders,
			demand_lines,
			items,
			sales_lines,
			component_items,
			currency,
		),
		"orders": orders,
		"demand_lines": demand_lines,
		"items": items,
		"shortages": shortages,
		"component_lines": component_lines,
		"component_items": component_items,
		"component_shortages": component_shortages,
		"warehouses": warehouses,
		"stock_by_item": stock_by_item,
		"stock_totals": stock_totals,
		"currency": currency,
		"generated_at": cstr(now_datetime()),
		"warnings": planner.warnings,
		"methodology": {
			"demand": _("Ordered quantity minus delivered quantity, converted to Stock UOM."),
			"allocation": _("Actual global stock is allocated by earliest delivery date, then Sales Order and line number."),
			"available": _("Available stock is actual stock minus ERPNext reserved stock."),
			"projected": _("Projected stock is ERPNext Bin projected quantity and includes expected supply and existing commitments."),
			"bom": _("Finished-goods stock is consumed first. Only uncovered quantities are exploded; sub-assembly stock is consumed before its child components are required."),
		},
	}


class SalesBOMPlanner(object):
	"""Cached BOM resolver and net material planner for Sales Order demand."""

	def __init__(self):
		self._bom_cache = {}
		self._resolved_bom_cache = {}
		self._item_default_bom_cache = {}
		self._collected_items = set()
		self._warning_keys = set()
		self.warnings = []
		self._sequence = 0

	def collect_item_codes(self, root_item_codes):
		component_codes = set()
		for item_code in sorted(set(root_item_codes)):
			self._collect_item_codes(
				item_code,
				component_codes,
				bom_path=(),
				depth=0,
				preferred_bom=None,
			)
		return component_codes

	def _collect_item_codes(
		self, item_code, component_codes, bom_path, depth, preferred_bom=None
	):
		if not item_code or depth >= MAX_BOM_DEPTH:
			return
		collection_key = (item_code, cstr(preferred_bom))
		if collection_key in self._collected_items:
			return
		self._collected_items.add(collection_key)

		bom_no = self.resolve_bom(item_code, preferred_bom)
		if not bom_no or bom_no in bom_path:
			return
		bom = self.get_bom(bom_no)
		if not bom:
			return
		for bom_item in bom.get("bom_items", []):
			child_code = cstr(bom_item.item_code)
			if not child_code:
				continue
			component_codes.add(child_code)
			child_bom = self.resolve_bom(child_code, bom_item.bom_no)
			if child_bom and child_bom not in bom_path + (bom_no,):
				self._collect_item_codes(
					child_code,
					component_codes,
					bom_path + (bom_no,),
					depth + 1,
					preferred_bom=child_bom,
				)

	def plan_materials(
		self,
		sales_line,
		build_qty,
		stock_pool,
		item_map,
		stock_totals,
	):
		bom_no = self.resolve_bom(sales_line.item_code)
		sales_line.bom_no = bom_no
		if not bom_no:
			sales_line.planning_issue = "missing_bom"
			self._add_warning(
				"missing-bom:{0}".format(sales_line.item_code),
				_("No active submitted BOM was found for uncovered sold item {0}.").format(
					sales_line.item_code
				),
			)
			return []

		bom = self.get_bom(bom_no)
		if not bom or not bom.get("bom_items"):
			sales_line.planning_issue = "empty_bom"
			self._add_warning(
				"empty-bom:{0}".format(bom_no),
				_("BOM {0} has no material rows and cannot be projected.").format(bom_no),
			)
			return []

		return self._plan_bom_children(
			sales_line=sales_line,
			parent_item_code=sales_line.item_code,
			parent_build_qty=build_qty,
			bom_no=bom_no,
			stock_pool=stock_pool,
			item_map=item_map,
			stock_totals=stock_totals,
			level=1,
			bom_path=(bom_no,),
			item_path=(sales_line.item_code,),
		)

	def _plan_bom_children(
		self,
		sales_line,
		parent_item_code,
		parent_build_qty,
		bom_no,
		stock_pool,
		item_map,
		stock_totals,
		level,
		bom_path,
		item_path,
	):
		bom = self.get_bom(bom_no)
		if not bom:
			return []
		bom_quantity = flt(bom.quantity) or 1
		rows = []

		for bom_item in bom.get("bom_items", []):
			item_code = cstr(bom_item.item_code)
			if not item_code:
				continue
			stock_qty = flt(bom_item.stock_qty)
			if not stock_qty:
				stock_qty = flt(bom_item.qty) * (flt(bom_item.conversion_factor) or 1)
			required_qty = flt(parent_build_qty) * stock_qty / bom_quantity
			if required_qty <= 0:
				continue

			child_bom = self.resolve_bom(item_code, bom_item.bom_no)
			item = item_map.get(item_code, {})
			totals = stock_totals.get(item_code, {})
			is_stock_item = cint(item.get("is_stock_item"))
			stock_before = flt(stock_pool.get(item_code)) if is_stock_item else 0
			allocated_qty = min(max(stock_before, 0), required_qty) if is_stock_item else 0
			uncovered_qty = max(required_qty - allocated_qty, 0)
			if is_stock_item:
				stock_pool[item_code] = stock_before - required_qty

			row = frappe._dict({
				"id": "material-node-{0}".format(self._sequence),
				"demand_line_id": sales_line.id,
				"sales_order": sales_line.sales_order,
				"sales_order_item": sales_line.sales_order_item,
				"customer": sales_line.customer,
				"customer_name": sales_line.customer_name,
				"delivery_date": sales_line.delivery_date,
				"days_to_delivery": sales_line.days_to_delivery,
				"is_overdue": sales_line.is_overdue,
				"sold_item_code": sales_line.sold_item_code,
				"sold_item_name": sales_line.sold_item_name,
				"demand_item_code": sales_line.item_code,
				"parent_item_code": parent_item_code,
				"parent_bom": bom_no,
				"item_code": item_code,
				"item_name": item.get("item_name") or bom_item.item_name or item_code,
				"reference_code": item.get("reference_code") or "",
				"item_group": item.get("item_group") or "",
				"stock_uom": item.get("stock_uom") or bom_item.stock_uom or "",
				"is_stock_item": is_stock_item,
				"is_sub_assembly": bool(child_bom),
				"bom_no": child_bom,
				"level": level,
				"required_qty": required_qty,
				"allocated_qty": allocated_qty,
				"shortage_qty": uncovered_qty if is_stock_item else 0,
				"build_required_qty": uncovered_qty if child_bom else 0,
				"stock_before": stock_before,
				"balance_after": stock_before - required_qty if is_stock_item else 0,
				"total_actual_qty": flt(totals.get("actual_qty")),
				"total_available_qty": flt(totals.get("available_qty")),
				"total_projected_qty": flt(totals.get("projected_qty")),
				"source_warehouse": bom_item.source_warehouse,
				"path": list(item_path) + [item_code],
				"cycle": False,
				"truncated": False,
				"planning_issue": None,
			})
			self._sequence += 1

			if not is_stock_item:
				row.status = "non_stock"
			elif uncovered_qty <= 0.000001:
				row.status = "available"
			elif child_bom:
				row.status = "build_required"
			elif allocated_qty > 0:
				row.status = "partial"
			else:
				row.status = "shortage"
			rows.append(row)

			expand_qty = uncovered_qty if is_stock_item else required_qty
			if not child_bom or expand_qty <= 0.000001:
				continue
			if level >= MAX_BOM_DEPTH:
				row.truncated = True
				row.planning_issue = "depth_limit"
				self._add_warning(
					"depth-limit",
					_("Some material branches reached the maximum BOM depth of {0}.").format(
						MAX_BOM_DEPTH
					),
				)
				continue
			if child_bom in bom_path or item_code in item_path:
				row.cycle = True
				row.planning_issue = "cycle"
				self._add_warning(
					"cycle:{0}".format(child_bom),
					_("A circular BOM reference involving {0} was stopped safely.").format(
						child_bom
					),
				)
				continue
			child = self.get_bom(child_bom)
			if not child or not child.get("bom_items"):
				row.planning_issue = "empty_bom"
				self._add_warning(
					"empty-bom:{0}".format(child_bom),
					_("BOM {0} has no material rows and cannot be projected.").format(
						child_bom
					),
				)
				continue

			rows.extend(self._plan_bom_children(
				sales_line=sales_line,
				parent_item_code=item_code,
				parent_build_qty=expand_qty,
				bom_no=child_bom,
				stock_pool=stock_pool,
				item_map=item_map,
				stock_totals=stock_totals,
				level=level + 1,
				bom_path=bom_path + (child_bom,),
				item_path=item_path + (item_code,),
			))

		return rows

	def resolve_bom(self, item_code, preferred_bom=None):
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
			bom = self.get_bom(candidate)
			if bom and bom.item == item_code:
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
			self._item_default_bom_cache[item_code] = frappe.db.get_value(
				"Item", item_code, "default_bom"
			)
		return self._item_default_bom_cache[item_code]

	def get_bom(self, bom_no):
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
		header["bom_items"] = frappe.get_all(
			"BOM Item",
			filters={"parent": bom_no, "parenttype": "BOM", "docstatus": 1},
			fields=[
				"item_code",
				"item_name",
				"stock_qty",
				"qty",
				"conversion_factor",
				"stock_uom",
				"bom_no",
				"source_warehouse",
				"idx",
			],
			order_by="idx asc",
			limit_page_length=0,
		)
		self._bom_cache[bom_no] = header
		return header

	def _add_warning(self, key, message):
		if key not in self._warning_keys:
			self._warning_keys.add(key)
			self.warnings.append(message)


def _normalize_filters(company, to_date, customer, include_on_hold):
	company = cstr(company).strip() or (
		frappe.defaults.get_user_default("Company")
		or frappe.db.get_single_value("Global Defaults", "default_company")
	)
	if not company:
		frappe.throw(_("Please select a Company."))

	if not frappe.db.exists("Company", company):
		frappe.throw(_("Company {0} does not exist.").format(company))

	return frappe._dict({
		"company": company,
		"to_date": getdate(to_date) if to_date else None,
		"customer": cstr(customer).strip() or None,
		"include_on_hold": cint(include_on_hold),
	})


def _get_sales_order_lines(filters):
	conditions = [
		"so.docstatus = 1",
		"so.company = %(company)s",
		"so.status NOT IN ('Closed', 'Completed', 'Cancelled')",
		"IFNULL(soi.qty, 0) > IFNULL(soi.delivered_qty, 0)",
		"(so._user_tags NOT LIKE '%%template%%' OR so._user_tags IS NULL)",
	]
	params = {"company": filters.company}
	if not filters.include_on_hold:
		conditions.append("so.status != 'On Hold'")
	if filters.to_date:
		conditions.append("COALESCE(soi.delivery_date, so.delivery_date) <= %(to_date)s")
		params["to_date"] = filters.to_date
	if filters.customer:
		conditions.append("so.customer = %(customer)s")
		params["customer"] = filters.customer

	return frappe.db.sql(
		"""
		select
			so.name as sales_order,
			so.customer,
			so.customer_name,
			so.transaction_date,
			so.status as sales_order_status,
			so.currency,
			soi.name as sales_order_item,
			soi.idx,
			soi.item_code as sold_item_code,
			soi.item_name as sold_item_name,
			soi.qty as ordered_qty,
			soi.delivered_qty,
			(soi.qty - soi.delivered_qty) as remaining_sales_qty,
			(soi.qty - soi.delivered_qty) * ifnull(soi.conversion_factor, 1) as remaining_stock_qty,
			soi.uom as sales_uom,
			soi.stock_uom,
			soi.conversion_factor,
			soi.warehouse,
			coalesce(soi.delivery_date, so.delivery_date) as delivery_date,
			ifnull(soi.base_net_amount, 0) *
				((soi.qty - soi.delivered_qty) / nullif(soi.qty, 0)) as outstanding_value
		from `tabSales Order Item` soi
		inner join `tabSales Order` so on so.name = soi.parent
		where {conditions}
			{match_conditions}
		order by
			coalesce(soi.delivery_date, so.delivery_date) asc,
			so.transaction_date asc,
			so.name asc,
			soi.idx asc
		""".format(
			conditions=" and ".join(conditions),
			match_conditions=get_match_cond("Sales Order")
				.replace("`tabSales Order`", "so")
				.replace("%", "%%"),
		),
		params,
		as_dict=True,
	)


def _get_packed_items(sales_lines):
	line_names = [row.sales_order_item for row in sales_lines]
	packed_by_line = defaultdict(list)
	for line_chunk in _chunks(line_names, 300):
		for row in frappe.get_all(
			"Packed Item",
			filters={
				"parent_detail_docname": ["in", line_chunk],
				"parenttype": "Sales Order",
				"docstatus": 1,
			},
			fields=[
				"name",
				"parent_detail_docname",
				"parent_item",
				"item_code",
				"item_name",
				"qty",
				"uom",
				"warehouse",
				"idx",
			],
			order_by="idx asc",
			limit_page_length=0,
		):
			packed_by_line[row.parent_detail_docname].append(row)
	return packed_by_line


def _build_demand_lines(sales_lines, packed_items):
	demand_lines = []
	for sales_line in sales_lines:
		packed_rows = packed_items.get(sales_line.sales_order_item) or []
		if packed_rows:
			remaining_ratio = flt(sales_line.remaining_sales_qty) / flt(sales_line.ordered_qty)
			for packed in packed_rows:
				demand_lines.append(_make_demand_line(
					sales_line,
					item_code=packed.item_code,
					item_name=packed.item_name,
					demand_qty=flt(packed.qty) * remaining_ratio,
					stock_uom=packed.uom,
					warehouse=packed.warehouse,
					is_packed_item=1,
					packed_item=packed.name,
					line_sort=packed.idx,
				))
		else:
			demand_lines.append(_make_demand_line(
				sales_line,
				item_code=sales_line.sold_item_code,
				item_name=sales_line.sold_item_name,
				demand_qty=sales_line.remaining_stock_qty,
				stock_uom=sales_line.stock_uom,
				warehouse=sales_line.warehouse,
				is_packed_item=0,
				packed_item=None,
				line_sort=0,
			))
	return demand_lines


def _make_demand_line(
	sales_line,
	item_code,
	item_name,
	demand_qty,
	stock_uom,
	warehouse,
	is_packed_item,
	packed_item,
	line_sort,
):
	delivery_date = getdate(sales_line.delivery_date)
	return frappe._dict({
		"id": "{0}:{1}".format(sales_line.sales_order_item, packed_item or "item"),
		"sales_order": sales_line.sales_order,
		"sales_order_item": sales_line.sales_order_item,
		"sales_order_status": sales_line.sales_order_status,
		"customer": sales_line.customer,
		"customer_name": sales_line.customer_name,
		"transaction_date": cstr(sales_line.transaction_date),
		"delivery_date": cstr(delivery_date),
		"days_to_delivery": date_diff(delivery_date, getdate(nowdate())),
		"is_overdue": cint(delivery_date < getdate(nowdate())),
		"line_index": cint(sales_line.idx),
		"line_sort": cint(line_sort),
		"sold_item_code": sales_line.sold_item_code,
		"sold_item_name": sales_line.sold_item_name,
		"item_code": item_code,
		"item_name": item_name or item_code,
		"demand_qty": flt(demand_qty),
		"stock_uom": stock_uom,
		"warehouse": warehouse,
		"is_packed_item": cint(is_packed_item),
		"packed_item": packed_item,
		"remaining_sales_qty": flt(sales_line.remaining_sales_qty),
		"sales_uom": sales_line.sales_uom,
	})


def _get_item_map(item_codes):
	item_codes = sorted(set(item_code for item_code in item_codes if item_code))
	item_meta = frappe.get_meta("Item")
	fields = [
		"name as item_code",
		"item_name",
		"item_group",
		"stock_uom",
		"is_stock_item",
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
			item.setdefault("reference_code", "")
			item_map[item.item_code] = item
	return item_map


def _plan_sales_and_materials(demand_lines, planner, item_map, stock_totals):
	stock_pool = {
		item_code: flt(totals.get("actual_qty"))
		for item_code, totals in stock_totals.items()
	}
	demand_lines.sort(key=lambda row: (
		row.delivery_date or "9999-12-31",
		row.transaction_date or "9999-12-31",
		row.sales_order,
		row.line_index,
		row.line_sort,
	))

	component_lines = []
	for row in demand_lines:
		item = item_map.get(row.item_code, {})
		totals = stock_totals.get(row.item_code, {})
		row.item_name = item.get("item_name") or row.item_name or row.item_code
		row.item_group = item.get("item_group") or ""
		row.reference_code = item.get("reference_code") or ""
		row.stock_uom = item.get("stock_uom") or row.stock_uom or ""
		row.is_stock_item = cint(item.get("is_stock_item"))
		row.total_actual_qty = flt(totals.get("actual_qty"))
		row.total_available_qty = flt(totals.get("available_qty"))
		row.total_projected_qty = flt(totals.get("projected_qty"))
		row.bom_no = None
		row.planning_issue = None

		if not row.is_stock_item:
			row.stock_before = 0.0
			row.allocated_qty = 0.0
			row.shortage_qty = 0.0
			row.balance_after = 0.0
			row.coverage_percent = 100.0
			row.status = "non_stock"
		else:
			stock_before = flt(stock_pool.get(row.item_code))
			available_before = max(stock_before, 0)
			allocated_qty = min(available_before, flt(row.demand_qty))
			row.stock_before = stock_before
			row.allocated_qty = allocated_qty
			row.shortage_qty = max(flt(row.demand_qty) - allocated_qty, 0)
			row.balance_after = stock_before - flt(row.demand_qty)
			row.coverage_percent = (
				allocated_qty / flt(row.demand_qty) * 100 if flt(row.demand_qty) else 100
			)
			if row.shortage_qty <= 0.000001:
				row.status = "available"
			elif allocated_qty > 0:
				row.status = "partial"
			else:
				row.status = "shortage"
			stock_pool[row.item_code] = row.balance_after

		build_qty = row.shortage_qty if row.is_stock_item else flt(row.demand_qty)
		should_plan = row.is_stock_item or bool(planner.resolve_bom(row.item_code))
		if build_qty > 0.000001 and should_plan:
			planned_rows = planner.plan_materials(
				row,
				build_qty,
				stock_pool,
				item_map,
				stock_totals,
			)
			component_lines.extend(planned_rows)
			if row.bom_no and row.is_stock_item:
				row.status = "build_required"

	return component_lines


def _aggregate_items(demand_lines, item_map, stock_totals):
	items = OrderedDict()
	for line in demand_lines:
		if line.item_code not in items:
			item = item_map.get(line.item_code, {})
			items[line.item_code] = frappe._dict({
				"item_code": line.item_code,
				"item_name": item.get("item_name") or line.item_name or line.item_code,
				"reference_code": item.get("reference_code") or "",
				"item_group": item.get("item_group") or "",
				"stock_uom": item.get("stock_uom") or line.stock_uom or "",
				"is_stock_item": cint(item.get("is_stock_item")),
				"default_bom": item.get("default_bom"),
				"demand_qty": 0.0,
				"allocated_qty": 0.0,
				"shortage_qty": 0.0,
				"has_bom": False,
				"orders": set(),
				"line_count": 0,
				"next_delivery_date": line.delivery_date,
			})

		row = items[line.item_code]
		row.demand_qty += flt(line.demand_qty)
		row.allocated_qty += flt(line.allocated_qty)
		row.shortage_qty += flt(line.shortage_qty)
		row.has_bom = row.has_bom or bool(line.bom_no)
		row.orders.add(line.sales_order)
		row.line_count += 1
		if line.delivery_date and (not row.next_delivery_date or line.delivery_date < row.next_delivery_date):
			row.next_delivery_date = line.delivery_date

	result = []
	for item_code, row in items.items():
		totals = stock_totals.get(item_code, {})
		row.order_count = len(row.orders)
		row.orders = sorted(row.orders)
		row.total_actual_qty = flt(totals.get("actual_qty"))
		row.total_reserved_qty = flt(totals.get("reserved_qty"))
		row.total_available_qty = flt(totals.get("available_qty"))
		row.total_projected_qty = flt(totals.get("projected_qty"))
		row.current_balance = row.total_actual_qty - row.demand_qty
		row.projected_shortage_qty = max(-row.total_projected_qty, 0) if row.is_stock_item else 0
		row.coverage_percent = (
			min(row.allocated_qty / row.demand_qty * 100, 100)
			if row.is_stock_item and row.demand_qty > 0
			else 100
		)
		if not row.is_stock_item:
			row.status = "non_stock"
		elif row.shortage_qty <= 0.000001:
			row.status = "available"
		elif row.has_bom:
			row.status = "build_required"
		elif row.allocated_qty > 0:
			row.status = "partial"
		else:
			row.status = "shortage"
		row.projected_status = "shortage" if row.projected_shortage_qty > 0.000001 else "available"
		result.append(row)

	status_order = {
		"shortage": 0,
		"partial": 1,
		"build_required": 2,
		"available": 3,
		"non_stock": 4,
	}
	return sorted(result, key=lambda row: (
		status_order.get(row.status, 9),
		row.next_delivery_date or "9999-12-31",
		row.item_code,
	))


def _aggregate_component_items(component_lines, item_map, stock_totals):
	items = OrderedDict()
	for line in component_lines:
		if line.item_code not in items:
			item = item_map.get(line.item_code, {})
			items[line.item_code] = frappe._dict({
				"item_code": line.item_code,
				"item_name": item.get("item_name") or line.item_name or line.item_code,
				"reference_code": item.get("reference_code") or "",
				"item_group": item.get("item_group") or "",
				"stock_uom": item.get("stock_uom") or line.stock_uom or "",
				"is_stock_item": cint(item.get("is_stock_item")),
				"is_sub_assembly": bool(line.is_sub_assembly),
				"bom_no": line.bom_no,
				"demand_qty": 0.0,
				"allocated_qty": 0.0,
				"shortage_qty": 0.0,
				"build_required_qty": 0.0,
				"blocking_shortage_qty": 0.0,
				"orders": set(),
				"sold_items": set(),
				"levels": set(),
				"line_count": 0,
				"next_delivery_date": line.delivery_date,
			})

		row = items[line.item_code]
		row.demand_qty += flt(line.required_qty)
		row.allocated_qty += flt(line.allocated_qty)
		row.shortage_qty += flt(line.shortage_qty)
		row.build_required_qty += flt(line.build_required_qty)
		if not line.is_sub_assembly or line.planning_issue:
			row.blocking_shortage_qty += flt(line.shortage_qty)
		row.orders.add(line.sales_order)
		row.sold_items.add(line.sold_item_code)
		row.levels.add(line.level)
		row.line_count += 1
		row.is_sub_assembly = row.is_sub_assembly or bool(line.is_sub_assembly)
		row.bom_no = row.bom_no or line.bom_no
		if line.delivery_date and (
			not row.next_delivery_date or line.delivery_date < row.next_delivery_date
		):
			row.next_delivery_date = line.delivery_date

	result = []
	for item_code, row in items.items():
		totals = stock_totals.get(item_code, {})
		row.order_count = len(row.orders)
		row.orders = sorted(row.orders)
		row.sold_item_count = len(row.sold_items)
		row.sold_items = sorted(row.sold_items)
		row.levels = sorted(row.levels)
		row.total_actual_qty = flt(totals.get("actual_qty"))
		row.total_reserved_qty = flt(totals.get("reserved_qty"))
		row.total_available_qty = flt(totals.get("available_qty"))
		row.total_projected_qty = flt(totals.get("projected_qty"))
		row.projected_shortage_qty = (
			max(-row.total_projected_qty, 0) if row.is_stock_item else 0
		)
		row.coverage_percent = (
			min(row.allocated_qty / row.demand_qty * 100, 100)
			if row.is_stock_item and row.demand_qty > 0
			else 100
		)
		if not row.is_stock_item:
			row.status = "non_stock"
		elif row.shortage_qty <= 0.000001:
			row.status = "available"
		elif row.is_sub_assembly and row.blocking_shortage_qty <= 0.000001:
			row.status = "build_required"
		elif row.allocated_qty > 0:
			row.status = "partial"
		else:
			row.status = "shortage"
		row.projected_status = (
			"shortage" if row.projected_shortage_qty > 0.000001 else "available"
		)
		result.append(row)

	status_order = {
		"shortage": 0,
		"partial": 1,
		"build_required": 2,
		"available": 3,
		"non_stock": 4,
	}
	return sorted(result, key=lambda row: (
		status_order.get(row.status, 9),
		row.next_delivery_date or "9999-12-31",
		row.item_code,
	))


def _aggregate_orders(sales_lines, demand_lines, component_lines):
	orders = OrderedDict()
	for line in sales_lines:
		if line.sales_order not in orders:
			orders[line.sales_order] = frappe._dict({
				"sales_order": line.sales_order,
				"customer": line.customer,
				"customer_name": line.customer_name,
				"transaction_date": cstr(line.transaction_date),
				"delivery_date": cstr(line.delivery_date),
				"sales_order_status": line.sales_order_status,
				"outstanding_value": 0.0,
				"sales_line_count": 0,
				"stock_line_count": 0,
				"available_lines": 0,
				"partial_lines": 0,
				"shortage_lines": 0,
				"build_required_lines": 0,
				"non_stock_lines": 0,
				"material_line_count": 0,
				"material_allocated_lines": 0,
				"planning_issue_count": 0,
				"stock_gap_items": set(),
				"material_shortage_items": set(),
				"build_required_items": set(),
			})
		row = orders[line.sales_order]
		row.outstanding_value += flt(line.outstanding_value)
		row.sales_line_count += 1
		line_date = cstr(line.delivery_date)
		if line_date and (not row.delivery_date or line_date < row.delivery_date):
			row.delivery_date = line_date

	for line in demand_lines:
		row = orders[line.sales_order]
		if not line.is_stock_item:
			row.non_stock_lines += 1
			continue
		row.stock_line_count += 1
		if line.status == "available":
			row.available_lines += 1
		elif line.status == "partial":
			row.partial_lines += 1
			row.stock_gap_items.add(line.item_code)
		elif line.status == "build_required":
			row.build_required_lines += 1
			row.stock_gap_items.add(line.item_code)
		else:
			row.shortage_lines += 1
			row.stock_gap_items.add(line.item_code)
		if line.planning_issue:
			row.planning_issue_count += 1

	for line in component_lines:
		row = orders[line.sales_order]
		row.material_line_count += 1
		if flt(line.allocated_qty) > 0:
			row.material_allocated_lines += 1
		if line.planning_issue:
			row.planning_issue_count += 1
		if flt(line.shortage_qty) <= 0.000001:
			continue
		if line.is_sub_assembly and not line.planning_issue:
			row.build_required_items.add(line.item_code)
		else:
			row.material_shortage_items.add(line.item_code)

	today = getdate(nowdate())
	result = []
	for row in orders.values():
		row.stock_gap_item_count = len(row.stock_gap_items)
		row.stock_gap_items = sorted(row.stock_gap_items)
		row.material_shortage_item_count = len(row.material_shortage_items)
		row.material_shortage_items = sorted(row.material_shortage_items)
		row.build_required_item_count = len(row.build_required_items)
		row.build_required_items = sorted(row.build_required_items)
		row.shortage_item_count = row.material_shortage_item_count
		row.is_overdue = cint(bool(row.delivery_date) and getdate(row.delivery_date) < today)
		row.days_to_delivery = date_diff(getdate(row.delivery_date), today) if row.delivery_date else None
		if not row.stock_line_count:
			row.status = "non_stock"
		elif row.available_lines == row.stock_line_count:
			row.status = "available"
		elif not row.material_shortage_item_count and not row.planning_issue_count:
			row.status = "buildable"
		elif (
			row.available_lines
			or row.partial_lines
			or row.build_required_lines
			or row.material_allocated_lines
		):
			row.status = "partial"
		else:
			row.status = "shortage"
		row.readiness_percent = (
			(row.available_lines + (row.partial_lines * 0.5)) / row.stock_line_count * 100
			if row.stock_line_count else 100
		)
		result.append(row)

	status_order = {
		"shortage": 0,
		"partial": 1,
		"buildable": 2,
		"available": 3,
		"non_stock": 4,
	}
	return sorted(result, key=lambda row: (
		status_order.get(row.status, 9),
		row.delivery_date or "9999-12-31",
		row.sales_order,
	))


def _get_summary(
	orders, demand_lines, items, sales_lines, component_items, currency
):
	return {
		"sales_orders": len(orders),
		"sales_lines": len(sales_lines),
		"stock_demand_lines": len(demand_lines),
		"unique_items": len(items),
		"component_items": len(component_items),
		"ready_orders": len([row for row in orders if row.status == "available"]),
		"buildable_orders": len([row for row in orders if row.status == "buildable"]),
		"at_risk_orders": len([row for row in orders if row.status in ("partial", "shortage")]),
		"blocked_orders": len([row for row in orders if row.status == "shortage"]),
		"shortage_items": len([row for row in items if flt(row.shortage_qty) > 0]),
		"component_shortage_items": len([
			row for row in component_items if flt(row.shortage_qty) > 0
		]),
		"blocking_component_items": len([
			row for row in component_items if flt(row.blocking_shortage_qty) > 0
		]),
		"subassemblies_to_build": len([
			row for row in component_items
			if row.is_sub_assembly and flt(row.build_required_qty) > 0
		]),
		"overdue_orders": len([row for row in orders if row.is_overdue]),
		"outstanding_value": sum(flt(row.outstanding_value) for row in orders),
		"currency": currency,
	}


def _assert_projection_access():
	if frappe.session.user == "Guest":
		frappe.throw(_("Please sign in to use the Sales Order Stock Projection."), frappe.PermissionError)
	if frappe.session.user == "Administrator":
		return
	if not ALLOWED_ROLES.intersection(set(frappe.get_roles())):
		frappe.throw(_("You do not have access to the Sales Order Stock Projection."), frappe.PermissionError)


def _chunks(values, size):
	for index in range(0, len(values), size):
		yield values[index:index + size]
