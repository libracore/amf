"""Read-only recursive BOM cost reconciliation in company base currency.

ERPNext v12 prices a parent from its own BOM Item.amount values, operations,
and scrap. A linked child BOM can change later, so its current total must not
silently replace the amount booked in the parent row. This walker expands the
recorded child link and exposes that difference explicitly.
"""
from __future__ import unicode_literals

from decimal import Decimal
from collections import defaultdict

import frappe
from frappe import _

from amf.amf.report.bom_cost_breakdown.bom_cost_breakdown import (
	ALL_CATEGORIES, CATEGORIES, operation_category,
)


def money(value):
	if value in (None, ""):
		return Decimal("0")
	return Decimal(str(value))


def display(value):
	return round(float(value), 6) if value is not None else None


def execute_recursive(filters):
	if not filters.get("item_code"):
		frappe.throw(_("Select a finished Item for Recursive BOM"))
	item = frappe.get_doc("Item", filters.item_code)
	check_read(item)
	work_order = frappe.get_doc("Work Order", filters.work_order) if filters.get("work_order") else None
	if work_order:
		check_read(work_order)
		if work_order.production_item != item.name:
			frappe.throw(_("Work Order does not produce the selected Item"))
	bom_name = filters.get("bom") or (work_order.bom_no if work_order else None)
	if not bom_name and item.default_bom:
		default = frappe.db.get_value("BOM", item.default_bom,
			["item", "docstatus", "is_active"], as_dict=True)
		if default and default.item == item.name and default.docstatus == 1 and default.is_active:
			bom_name = item.default_bom
	if not bom_name:
		latest = frappe.get_all("BOM", filters={"item": item.name, "docstatus": 1, "is_active": 1},
			fields=["name"], order_by="modified desc", limit_page_length=1)
		bom_name = latest[0].name if latest else None
	if not bom_name:
		frappe.throw(_("No submitted active BOM is available for this Item"))
	if work_order and work_order.bom_no != bom_name:
		frappe.throw(_("Selected BOM does not match the Work Order BOM"))
	root = frappe.get_doc("BOM", bom_name)
	check_read(root)
	if root.item != item.name or root.docstatus not in (1, 2):
		frappe.throw(_("BOM must belong to the Item and be submitted or historical"))
	walker = BOMCostWalker(root)
	return columns(), walker.build()


def check_read(doc):
	if not frappe.has_permission(doc.doctype, "read", doc=doc):
		frappe.throw(_("Not permitted to read {0} {1}").format(doc.doctype, doc.name), frappe.PermissionError)


def columns():
	return [
		{"fieldname": "level", "label": _("Level"), "fieldtype": "Int", "width": 60},
		{"fieldname": "path", "label": _("BOM path"), "fieldtype": "Data", "width": 300},
		{"fieldname": "line_type", "label": _("Line type"), "fieldtype": "Data", "width": 165},
		{"fieldname": "category", "label": _("Cost category"), "fieldtype": "Data", "width": 135},
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 115},
		{"fieldname": "bom", "label": _("BOM"), "fieldtype": "Link", "options": "BOM", "width": 160},
		{"fieldname": "child_bom", "label": _("Child BOM"), "fieldtype": "Link", "options": "BOM", "width": 160},
		{"fieldname": "quantity", "label": _("Quantity / hours"), "fieldtype": "Float", "width": 120},
		{"fieldname": "uom", "label": _("UOM"), "fieldtype": "Data", "width": 75},
		{"fieldname": "usage_factor", "label": _("Root usage factor"), "fieldtype": "Float", "precision": 6, "width": 120},
		{"fieldname": "rate", "label": _("Base rate"), "fieldtype": "Currency", "options": "currency", "precision": 6, "width": 110},
		{"fieldname": "source_amount", "label": _("Stored base amount"), "fieldtype": "Currency", "options": "currency", "precision": 6, "width": 130},
		{"fieldname": "root_amount", "label": _("Root BOM contribution"), "fieldtype": "Currency", "options": "currency", "precision": 6, "width": 145},
		{"fieldname": "per_finished_unit", "label": _("Per finished unit"), "fieldtype": "Currency", "options": "currency", "precision": 6, "width": 135},
		{"fieldname": "bom_currency_total", "label": _("BOM total (its currency)"), "fieldtype": "Currency", "options": "bom_currency", "precision": 6, "width": 155},
		{"fieldname": "bom_currency", "label": _("BOM currency"), "fieldtype": "Data", "width": 105},
		{"fieldname": "currency", "label": _("Company currency"), "fieldtype": "Data", "width": 105},
		{"fieldname": "source_record", "label": _("Source record"), "fieldtype": "Data", "width": 175},
		{"fieldname": "method", "label": _("Calculation / reconciliation"), "fieldtype": "Data", "width": 460},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 175},
		{"fieldname": "included", "label": _("Included in rollup"), "fieldtype": "Data", "width": 105},
	]


class BOMCostWalker(object):
	def __init__(self, root, loader=None, currency=None, default_bom_lookup=None):
		self.root = root
		self.cache = {root.name: root}
		self.loader = loader or frappe.get_doc
		self.default_bom_lookup = default_bom_lookup or (
			lambda item_code: frappe.db.get_value("Item", item_code, "default_bom"))
		self.default_bom_cache = {}
		self.currency = currency if currency is not None else frappe.db.get_value(
			"Company", root.company, "default_currency")
		self.rows = []
		self.gaps = []
		self.rollup = Decimal("0")
		self.category_totals = defaultdict(lambda: Decimal("0"))
		self.category_gaps = set()
		self.root_quantity = money(root.quantity)

	def _append(self, level, path, line_type, category=None, item_code=None,
			bom=None, child_bom=None, quantity=None, uom=None, usage_factor=None, rate=None,
			source_amount=None, root_amount=None, bom_currency_total=None, bom_currency=None,
			source_record=None, method=None, status="Recorded", included=False):
		row = dict(level=level, path=" > ".join(path), line_type=line_type,
			category=category, item_code=item_code, bom=bom, child_bom=child_bom,
			quantity=display(quantity), uom=uom, usage_factor=display(usage_factor), rate=display(rate),
			source_amount=display(source_amount), root_amount=display(root_amount),
			per_finished_unit=display(root_amount / self.root_quantity)
				if root_amount is not None and self.root_quantity > 0 else None,
			bom_currency_total=display(bom_currency_total), bom_currency=bom_currency,
			currency=self.currency,
			source_record=source_record, method=method, status=status,
			included="Yes" if included else "No")
		self.rows.append(row)
		if included and root_amount is not None:
			self.rollup += root_amount
			if category:
				self.category_totals[category] += root_amount
		if status not in ("Recorded", "Expanded", "Reconciled", "Rounding difference",
				"Historical BOM", "Child valuation difference", "BOM header difference"):
			self.gaps.append(row)
			if included and category:
				self.category_gaps.add(category)
		return row

	def _load_child(self, name):
		if name not in self.cache:
			doc = self.loader("BOM", name)
			check_read(doc)
			self.cache[name] = doc
		return self.cache[name]

	def _unpriced(self, quantity, rate, amount):
		return amount is None or (money(quantity) > 0 and money(rate) <= 0 and money(amount) == 0)

	def _default_bom(self, item_code):
		if item_code not in self.default_bom_cache:
			self.default_bom_cache[item_code] = self.default_bom_lookup(item_code)
		return self.default_bom_cache[item_code]

	def build(self):
		self._walk(self.root, Decimal("1"), 0, [self.root.item], ())
		for category in ALL_CATEGORIES:
			if category not in self.category_totals and category not in CATEGORIES:
				continue
			amount = self.category_totals.get(category)
			unavailable = category in self.category_gaps or amount is None
			self._append(0, [self.root.item], "Category subtotal", category,
				self.root.item, self.root.name,
				root_amount=None if unavailable else amount,
				source_record=self.root.name,
				method=("Unavailable: underlying line unpriced or child unresolved; recorded partial {0} {1}".format(
					display(amount), self.currency) if amount is not None else
					"No priced BOM cost source for {0}".format(category)) if unavailable else
					"Sum of included recursive {0} contributions".format(category),
				status="Unavailable" if unavailable else "Recorded")
		rollup = self.rollup
		stored = money(self.root.base_total_cost)
		difference = stored - rollup
		status = "Reconciled" if abs(difference) <= Decimal("0.000001") else "Mismatch"
		if self.gaps and status == "Reconciled":
			status = "Reconciled with pricing/link gaps"
		self._append(0, [self.root.item], "Recursive rollup total", "Total", self.root.item,
			self.root.name, source_amount=None, root_amount=rollup,
			source_record=self.root.name, method="Sum of included leaf costs, operation costs, scrap credits, and recorded differences",
			status=status)
		self._append(0, [self.root.item], "Stored BOM total", "Total", self.root.item,
			self.root.name, quantity=self.root_quantity, uom=self.root.uom,
			source_amount=stored, root_amount=stored,
			bom_currency_total=money(self.root.total_cost),
			bom_currency=getattr(self.root, "currency", None) or self.currency,
			source_record=self.root.name,
			method="ERPNext BOM.base_total_cost; BOM.total_cost is shown in its own currency",
			status=status)
		self._append(0, [self.root.item], "Rollup difference", "Reconciliation", self.root.item,
			self.root.name, root_amount=difference, source_record=self.root.name,
			method="Stored base_total_cost − recursive rollup total",
			status="Reconciled" if status != "Mismatch" else "Mismatch")
		return self.rows

	def _walk(self, bom, multiplier, level, path, active):
		if bom.name in active:
			raise ValueError("BOM cycle: {0}".format(" > ".join(active + (bom.name,))))
		active = active + (bom.name,)
		self._append(level, path, "BOM header", "Header", bom.item, bom.name,
			quantity=money(bom.quantity), uom=bom.uom, usage_factor=multiplier,
			source_amount=money(bom.base_total_cost), bom_currency_total=money(bom.total_cost),
			bom_currency=getattr(bom, "currency", None) or self.currency,
			source_record=bom.name,
			method="Stored BOM base total; material + operation − scrap, for this BOM quantity",
			status="Recorded" if bom.docstatus == 1 else "Historical BOM")
		direct = Decimal("0")
		for item in bom.items:
			amount = money(item.base_amount)
			direct += amount
			item_path = path + [item.item_code]
			base = dict(level=level + 1, path=item_path, item_code=item.item_code,
				bom=bom.name, child_bom=item.bom_no or None, quantity=money(item.qty),
				uom=item.uom, usage_factor=multiplier,
				rate=money(item.base_rate) if item.base_rate is not None else None,
				source_amount=amount if item.base_amount is not None else None,
				source_record="{0} / {1}".format(bom.name, item.name))
			if not item.bom_no:
				candidate = self._default_bom(item.item_code)
				if candidate:
					base["child_bom"] = candidate
				self._append(line_type="Material", category="Materials",
					root_amount=amount * multiplier if item.base_amount is not None else None,
					method="Stored BOM Item.base_amount × parent usage; row.bom_no is empty" +
						(" although Item.default_bom is {0}; default BOM is not substituted".format(candidate) if candidate else ""),
					status="Stored amount unavailable" if item.base_amount is None else
						"Unlinked child BOM available" if candidate else
						"Unpriced stored zero" if self._unpriced(item.qty, item.base_rate, item.base_amount) else "Recorded",
					included=True, **base)
				continue
			reason = "Parent BOM Item amount unavailable" if item.base_amount is None else None
			child = None
			if item.bom_no in active:
				reason = "BOM cycle"
			else:
				try:
					child = self._load_child(item.bom_no)
				except frappe.DoesNotExistError:
					reason = "Child BOM missing"
			if child and child.item != item.item_code:
				reason = "Child BOM item mismatch"
			if child and child.company != bom.company:
				reason = "Child BOM company mismatch"
			if child and child.docstatus not in (1, 2):
				reason = "Child BOM is draft"
			if child and money(child.quantity) <= 0:
				reason = "Child BOM quantity unavailable"
			if money(item.stock_qty) <= 0:
				reason = "BOM Item stock_qty unavailable"
			if reason:
				self._append(line_type="Unresolved subassembly", category="Materials",
					root_amount=amount * multiplier if item.base_amount is not None else None,
					method="Stored parent BOM Item amount retained; child expansion is unreliable: " + reason,
					status=reason, included=True, **base)
				continue
			self._append(line_type="Subassembly booked amount", category="Materials",
				root_amount=None,
				method="Parent row booked value; child detail below replaces this row in the rollup",
				status="Expanded", included=False, **base)
			child_multiplier = multiplier * money(item.stock_qty) / money(child.quantity)
			self._walk(child, child_multiplier, level + 1, item_path, active)
			difference = amount * multiplier - money(child.base_total_cost) * child_multiplier
			if difference != 0:
				status = "Rounding difference" if abs(difference) <= Decimal("0.000001") else "Child valuation difference"
				rate_method = "child BOM rate" if getattr(bom, "set_rate_of_sub_assembly_item_based_on_bom", 0) else "independent material rate"
				self._append(level + 1, item_path, "Child valuation difference", "Reconciliation",
					item.item_code, bom.name, child_bom=child.name, usage_factor=multiplier,
					root_amount=difference, source_record="{0} / {1} vs {2}".format(bom.name, item.name, child.name),
					method="Parent booked base_amount × usage − child base_total_cost × stock_qty / child BOM quantity; parent used {0} and its booked rate is authoritative".format(rate_method),
					status=status, included=True)
		for operation in bom.operations:
			amount = money(operation.base_operating_cost)
			direct += amount
			hours = money(operation.time_in_mins) / Decimal("60")
			self._append(level + 1, path, "Operation", operation_category(operation.operation),
				bom.item, bom.name, quantity=hours, uom="hour", usage_factor=multiplier,
				rate=money(operation.base_hour_rate) if operation.base_hour_rate is not None else None,
				source_amount=amount if operation.base_operating_cost is not None else None,
				root_amount=amount * multiplier if operation.base_operating_cost is not None else None,
				source_record="{0} / {1}".format(bom.name, operation.name),
				method="Stored BOM Operation.base_operating_cost × parent usage; time and rate shown for audit",
				status="Stored amount unavailable" if operation.base_operating_cost is None else
					"Unpriced stored zero" if self._unpriced(hours, operation.base_hour_rate, amount) else "Recorded",
				included=True)
		for scrap in bom.scrap_items:
			amount = money(scrap.base_amount)
			direct -= amount
			self._append(level + 1, path + [scrap.item_code], "Scrap credit", "Scrap Credit",
				scrap.item_code, bom.name, quantity=money(scrap.stock_qty), uom=scrap.stock_uom, usage_factor=multiplier,
				rate=-money(scrap.base_rate) if scrap.base_rate is not None else None,
				source_amount=-amount if scrap.base_amount is not None else None,
				root_amount=-amount * multiplier if scrap.base_amount is not None else None,
				source_record="{0} / {1}".format(bom.name, scrap.name),
				method="Negative stored BOM Scrap Item.base_amount × parent usage",
				status="Stored amount unavailable" if scrap.base_amount is None else
					"Unpriced stored zero" if self._unpriced(scrap.stock_qty, scrap.base_rate, amount) else "Recorded",
				included=True)
		variance = money(bom.base_total_cost) - direct
		if variance != 0:
			status = "Rounding difference" if abs(variance * multiplier) <= Decimal("0.000001") else "BOM header difference"
			self._append(level, path, "BOM header difference", "Reconciliation", bom.item, bom.name,
				root_amount=variance * multiplier, usage_factor=multiplier, source_record=bom.name,
				method="Stored BOM.base_total_cost − sum(stored item base_amount + operation base_operating_cost − scrap base_amount)",
				status=status, included=True)


class RecursiveBOMCostIndex(object):
	"""Memoized category rollups from bulk-loaded BOM rows for reference averages."""
	def __init__(self, headers, items, operations, scrap_items):
		self.headers = {row.name: row for row in headers}
		self.items = defaultdict(list)
		self.operations = defaultdict(list)
		self.scrap_items = defaultdict(list)
		for row in items:
			self.items[row.parent].append(row)
		for row in operations:
			self.operations[row.parent].append(row)
		for row in scrap_items:
			self.scrap_items[row.parent].append(row)
		self.cache = {}

	def decompose(self, name, active=()):
		if name in self.cache:
			return self.cache[name]
		bom = self.headers[name]
		active = active + (name,)
		amounts = defaultdict(lambda: Decimal("0"))
		present, invalid = set(), set()
		direct = Decimal("0")
		cycle_seen = False
		for item in self.items[name]:
			amount = money(item.base_amount)
			direct += amount
			child = self.headers.get(item.bom_no) if item.bom_no else None
			valid_child = bool(child and item.base_amount is not None and child.item == item.item_code and child.company == bom.company
				and child.docstatus in (1, 2) and money(child.quantity) > 0
				and money(item.stock_qty) > 0 and child.name not in active)
			if valid_child:
				child_values = self.decompose(child.name, active)
				scale = money(item.stock_qty) / money(child.quantity)
				for category, value in child_values["amounts"].items():
					amounts[category] += value * scale
				present.update(child_values["present"])
				invalid.update(child_values["invalid"])
				cycle_seen = cycle_seen or child_values["cycle_seen"]
				difference = amount - money(child.base_total_cost) * scale
				if difference:
					amounts["Reconciliation"] += difference
					present.add("Reconciliation")
			else:
				amounts["Materials"] += amount
				present.add("Materials")
				if item.base_amount is None or (item.bom_no and not valid_child) or (
					money(item.qty) > 0 and money(item.base_rate) <= 0 and amount == 0):
					invalid.add("Materials")
				if item.bom_no in active:
					cycle_seen = True
		for op in self.operations[name]:
			category = operation_category(op.operation)
			amount = money(op.base_operating_cost)
			direct += amount
			amounts[category] += amount
			present.add(category)
			if op.base_operating_cost is None or (
					money(op.time_in_mins) > 0 and money(op.base_hour_rate) <= 0 and amount == 0):
				invalid.add(category)
		for scrap in self.scrap_items[name]:
			amount = money(scrap.base_amount)
			direct -= amount
			amounts["Scrap Credit"] -= amount
			present.add("Scrap Credit")
			if scrap.base_amount is None or (
					money(scrap.stock_qty) > 0 and money(scrap.base_rate) <= 0 and amount == 0):
				invalid.add("Scrap Credit")
		variance = money(bom.base_total_cost) - direct
		if variance:
			amounts["Reconciliation"] += variance
			present.add("Reconciliation")
		result = dict(amounts=dict(amounts), present=present, invalid=invalid,
			cycle_seen=cycle_seen)
		if not cycle_seen:
			self.cache[name] = result
		return result


def load_cost_index():
	"""Load submitted and historical child BOMs once, without N+1 document reads."""
	headers = frappe.db.sql("""
		SELECT name, item, company, quantity, base_total_cost, docstatus
		FROM `tabBOM` WHERE docstatus IN (1, 2)
	""", as_dict=True)
	items = frappe.db.sql("""
		SELECT bi.parent, bi.item_code, bi.bom_no, bi.qty, bi.stock_qty,
			bi.base_rate, bi.base_amount
		FROM `tabBOM Item` bi JOIN `tabBOM` b ON b.name = bi.parent
		WHERE b.docstatus IN (1, 2)
	""", as_dict=True)
	operations = frappe.db.sql("""
		SELECT bo.parent, bo.operation, bo.time_in_mins,
			bo.base_hour_rate, bo.base_operating_cost
		FROM `tabBOM Operation` bo JOIN `tabBOM` b ON b.name = bo.parent
		WHERE b.docstatus IN (1, 2)
	""", as_dict=True)
	scrap_items = frappe.db.sql("""
		SELECT si.parent, si.stock_qty, si.base_rate, si.base_amount
		FROM `tabBOM Scrap Item` si JOIN `tabBOM` b ON b.name = si.parent
		WHERE b.docstatus IN (1, 2)
	""", as_dict=True)
	return RecursiveBOMCostIndex(headers, items, operations, scrap_items)
