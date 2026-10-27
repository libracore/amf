"""Reprice the current default-BOM tree from submitted Purchase Receipts.

Every selected child Item uses its current active default BOM (or the latest
active submitted BOM when no usable default exists). A leaf uses its latest
paid, non-return Purchase Receipt net amount per accepted stock unit.
"""
from __future__ import unicode_literals

from collections import defaultdict
from decimal import Decimal

import frappe
from frappe import _

from amf.amf.report.bom_cost_breakdown.bom_cost_breakdown import CATEGORIES, operation_category
from amf.amf.report.bom_cost_breakdown.recursive_bom import check_read, display, money


REPORT_CATEGORIES = CATEGORIES + ("Other Operations", "Scrap Credit")


def execute_latest_purchase(filters, include_process=False):
	item_code = filters.get("item_code")
	if not item_code:
		frappe.throw(_("Select a finished Item for Latest Purchase BOM"))
	check_read(frappe.get_doc("Item", item_code))
	if not frappe.has_permission("Purchase Receipt", "read"):
		frappe.throw(_("Purchase Receipt read permission is required to see purchase rates"),
			frappe.PermissionError)
	selector = CurrentBOMSelector()
	root, selection = selector.get(item_code)
	if not root:
		frappe.throw(_("No active submitted BOM is available for this Item"))
	selector.company = root.company
	selector.cache = {item_code: (root, selection)}
	leaves = collect_leaf_items(root, selector.get)
	receipts = latest_purchase_receipts(leaves, root.company)
	stock_uoms = {row.name: row.stock_uom for row in frappe.get_all(
		"Item", filters={"name": ["in", sorted(leaves)]},
		fields=["name", "stock_uom"], limit_page_length=0)} if leaves else {}
	for receipt_name in set(row.parent for row in receipts.values()):
		check_read(frappe.get_doc("Purchase Receipt", receipt_name))
	currency = frappe.db.get_value("Company", root.company, "default_currency")
	process_costs = None
	if include_process:
		for doctype in ("Work Order", "Planning", "Timer Production"):
			if not frappe.has_permission(doctype, "read"):
				frappe.throw(_("{0} read permission is required to see process sources").format(doctype),
					frappe.PermissionError)
		from amf.amf.report.bom_cost_breakdown.process_costing import load_process_costs
		process_costs = load_process_costs(
			[item for item, value in selector.cache.items() if value[0]], root.company, currency)
		check_process_sources(process_costs)
	calculator = LatestPurchaseBOMCalculator(root, selector.get, receipts, currency,
		stock_uoms=stock_uoms, process_costs=process_costs)
	return columns(include_process), calculator.build()


def check_process_sources(process_costs):
	"""Apply document-level permissions to the historical process evidence."""
	checked = set()
	for categories in process_costs.values():
		for group in categories.values():
			for sample in group.get("samples", []):
				key = ("Work Order", sample["source"])
				if key not in checked:
					check_read(frappe.get_doc(*key))
					checked.add(key)
				for source in sample["source_rows"]:
					if source["source_type"] not in ("Planning", "Timer Production"):
						continue
					key = (source["source_type"], source["source_record"])
					if key not in checked:
						check_read(frappe.get_doc(*key))
						checked.add(key)


class CurrentBOMSelector(object):
	def __init__(self, company=None):
		self.company = company
		self.cache = {}

	def get(self, item_code):
		if item_code in self.cache:
			return self.cache[item_code]
		default = frappe.db.get_value("Item", item_code, "default_bom")
		if default:
			candidate = frappe.db.get_value("BOM", default,
				["item", "company", "docstatus", "is_active", "quantity"], as_dict=True)
			if self._valid(candidate, item_code):
				result = (frappe.get_doc("BOM", default), "Item.default_bom")
				check_read(result[0])
				self.cache[item_code] = result
				return result
		filters = {"item": item_code, "docstatus": 1, "is_active": 1, "quantity": [">", 0]}
		if self.company:
			filters["company"] = self.company
		matches = frappe.get_all("BOM", filters=filters, fields=["name"],
			order_by="modified desc, name desc", limit_page_length=1)
		if matches:
			result = (frappe.get_doc("BOM", matches[0].name), "Latest active fallback")
			check_read(result[0])
		else:
			result = (None, "No active BOM")
		self.cache[item_code] = result
		return result

	def _valid(self, candidate, item_code):
		return bool(candidate and candidate.item == item_code and candidate.docstatus == 1
			and candidate.is_active and money(candidate.quantity) > 0
			and (not self.company or candidate.company == self.company))


def collect_leaf_items(bom, choose_bom, active=()):
	"""Collect only purchase leaves; repeated BOM paths are still costed separately."""
	if bom.name in active:
		return set()
	active = active + (bom.name,)
	leaves = set()
	for row in bom.items:
		child, _ = choose_bom(row.item_code)
		if child:
			leaves.update(collect_leaf_items(child, choose_bom, active))
		else:
			leaves.add(row.item_code)
	return leaves


def latest_purchase_receipts(item_codes, company):
	if not item_codes:
		return {}
	item_codes = sorted(item_codes)
	rows = frappe.db.sql("""
		SELECT pri.name, pri.parent, pri.idx, pri.item_code, pri.qty, pri.stock_qty,
			pri.uom, pri.stock_uom, pri.conversion_factor, pri.base_rate,
			pri.base_net_rate, pri.base_net_amount, pr.posting_date,
			pr.posting_time, pr.currency, pr.conversion_rate
		FROM `tabPurchase Receipt Item` pri
		JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
		WHERE pri.item_code IN ({items}) AND pr.company = %s AND pr.docstatus = 1
			AND IFNULL(pr.is_return, 0) = 0 AND IFNULL(pri.is_free_item, 0) = 0
			AND pri.qty > 0 AND pri.stock_qty > 0
		ORDER BY pri.item_code, pr.posting_date DESC, pr.posting_time DESC,
			pr.creation DESC, pr.name DESC, pri.idx DESC
	""".format(items=", ".join(["%s"] * len(item_codes))),
		tuple(item_codes) + (company,), as_dict=True)
	latest = {}
	for row in rows:
		latest.setdefault(row.item_code, row)
	return latest


def columns(include_process=False):
	result = [
		{"fieldname": "level", "label": _("Level"), "fieldtype": "Int", "width": 60},
		{"fieldname": "path", "label": _("Current default BOM path"), "fieldtype": "Data", "width": 300},
		{"fieldname": "line_type", "label": _("Line type"), "fieldtype": "Data", "width": 175},
		{"fieldname": "category", "label": _("Cost category"), "fieldtype": "Data", "width": 130},
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 115},
		{"fieldname": "bom", "label": _("Parent BOM"), "fieldtype": "Link", "options": "BOM", "width": 170},
		{"fieldname": "child_bom", "label": _("Chosen child BOM"), "fieldtype": "Link", "options": "BOM", "width": 170},
		{"fieldname": "quantity", "label": _("Root quantity / time"), "fieldtype": "Float", "precision": 6, "width": 125},
		{"fieldname": "uom", "label": _("UOM"), "fieldtype": "Data", "width": 95},
		{"fieldname": "rate", "label": _("Base rate / shown UOM"), "fieldtype": "Currency", "options": "currency", "precision": 8, "width": 155},
		{"fieldname": "root_amount", "label": _("Cost for root BOM quantity"), "fieldtype": "Currency", "options": "currency", "precision": 6, "width": 175},
		{"fieldname": "per_finished_unit", "label": _("Cost / finished unit"), "fieldtype": "Currency", "options": "currency", "precision": 6, "width": 155},
		{"fieldname": "booked_bom_amount", "label": _("Stored BOM row contribution"), "fieldtype": "Currency", "options": "currency", "precision": 6, "width": 165},
		{"fieldname": "receipt_qty", "label": _("Receipt stock qty"), "fieldtype": "Float", "precision": 6, "width": 115},
		{"fieldname": "receipt_base_net_amount", "label": _("Receipt base net amount"), "fieldtype": "Currency", "options": "currency", "precision": 6, "width": 165},
		{"fieldname": "receipt_posted", "label": _("Receipt posting date/time"), "fieldtype": "Data", "width": 170},
		{"fieldname": "currency", "label": _("Company currency"), "fieldtype": "Data", "width": 105},
		{"fieldname": "source_record", "label": _("Source record"), "fieldtype": "Data", "width": 200},
		{"fieldname": "method", "label": _("Calculation / selection"), "fieldtype": "Data", "width": 480},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 175},
		{"fieldname": "included", "label": _("Included in rollup"), "fieldtype": "Data", "width": 105},
	]
	if include_process:
		result.extend([
			{"fieldname": "basis", "label": _("Cost basis"), "fieldtype": "Data", "width": 110},
			{"fieldname": "item_unit_cost", "label": _("Cost / BOM Item unit"), "fieldtype": "Currency", "options": "currency", "precision": 6, "width": 155},
			{"fieldname": "observed_qty", "label": _("Observed good units"), "fieldtype": "Float", "precision": 6, "width": 125},
			{"fieldname": "observed_amount", "label": _("Observed source cost"), "fieldtype": "Currency", "options": "currency", "precision": 6, "width": 150},
			{"fieldname": "observed_per_unit", "label": _("Observed cost / unit"), "fieldtype": "Currency", "options": "currency", "precision": 6, "width": 145},
			{"fieldname": "coverage", "label": _("Retained / priced / WOs"), "fieldtype": "Data", "width": 120},
			{"fieldname": "sample_decision", "label": _("IQR decision"), "fieldtype": "Data", "width": 120},
		])
	return result


class LatestPurchaseBOMCalculator(object):
	def __init__(self, root, choose_bom, receipts, currency, stock_uoms=None,
			process_costs=None):
		self.root = root
		self.choose_bom = choose_bom
		self.receipts = receipts
		self.currency = currency
		self.stock_uoms = stock_uoms or {}
		self.process_costs = process_costs
		self.root_quantity = money(root.quantity)
		self.rows = []
		self.totals = defaultdict(lambda: Decimal("0"))
		self.present = set()
		self.gaps = set()
		self.known_total = Decimal("0")
		self.component_total = Decimal("0")
		self.component_gaps = set()
		self.gap_events = []
		self.process_coverage_gaps = []
		self.category_counts = defaultdict(int)

	def add(self, level, path, line_type, category=None, item_code=None, bom=None,
			child_bom=None, quantity=None, uom=None, rate=None, root_amount=None,
			booked_bom_amount=None, receipt_qty=None, receipt_base_net_amount=None,
			receipt_posted=None, source_record=None, method=None, status="Recorded",
			included=False, basis=None, item_unit_cost=None, observed_qty=None,
			observed_amount=None, observed_per_unit=None, coverage=None,
			sample_decision=None):
		row = dict(level=level, path=" > ".join(path), line_type=line_type,
			category=category, item_code=item_code, bom=bom, child_bom=child_bom,
			quantity=display(quantity), uom=uom,
			rate=round(float(rate), 8) if rate is not None else None,
			root_amount=display(root_amount),
			per_finished_unit=display(root_amount / self.root_quantity)
				if root_amount is not None and self.root_quantity > 0 else None,
			booked_bom_amount=display(booked_bom_amount), receipt_qty=display(receipt_qty),
			receipt_base_net_amount=display(receipt_base_net_amount),
			receipt_posted=str(receipt_posted) if receipt_posted else None,
			currency=self.currency, source_record=source_record, method=method,
			status=status, included="Yes" if included else "No",
			basis=basis, item_unit_cost=display(item_unit_cost),
			observed_qty=display(observed_qty), observed_amount=display(observed_amount),
			observed_per_unit=display(observed_per_unit), coverage=coverage,
			sample_decision=sample_decision)
		self.rows.append(row)
		if included and category:
			self.present.add(category)
			self.category_counts[category] += 1
			if root_amount is None:
				self.gaps.add(category)
				self.gap_events.append((category, row["path"]))
				if line_type in ("Purchased material", "Recorded BOM operation", "Stored BOM scrap credit",
						"Unusable BOM quantity", "BOM cycle", "Unusable child BOM UOM"):
					self.component_gaps.add(category)
			else:
				self.totals[category] += root_amount
				self.known_total += root_amount
				if line_type in ("Purchased material", "Recorded BOM operation", "Stored BOM scrap credit"):
					self.component_total += root_amount
		return row

	def build(self):
		if self.root_quantity <= 0:
			raise ValueError("Root BOM quantity must be positive")
		self.walk(self.root, Decimal("1"), 0, [self.root.item], ())
		for category in REPORT_CATEGORIES:
			available = category in self.present and category not in self.gaps
			coverage_gap = self.process_costs is not None and any(
				gap[0] == category for gap in self.process_coverage_gaps)
			amount = self.totals[category] if available else None
			self.add(0, [self.root.item], "Category subtotal", category,
				self.root.item, self.root.name, root_amount=amount,
				source_record=self.root.name,
				method="Sum of included {0} contributions from current defaults; incomplete process coverage".format(category) if available and coverage_gap else
					"Sum of included {0} contributions from current defaults".format(category) if available else
					"Unavailable: no priced source or at least one source cannot be valued",
				status="Partial coverage" if available and coverage_gap else "Recorded" if available else "Unavailable")
		if self.gaps:
			self.add(0, [self.root.item], "Known priced subtotal", "Total",
				self.root.item, self.root.name, root_amount=self.known_total,
				source_record=self.root.name,
				method="Sum of known amounts only; incomplete because one or more selected BOM or receipt lines cannot be costed",
				status="Partial")
		repriced = None if self.component_gaps else self.component_total
		self.add(0, [self.root.item], "Purchase-repriced BOM value", "Total",
			self.root.item, self.root.name, quantity=self.root_quantity, uom=self.root.uom,
			root_amount=repriced, source_record=self.root.name,
			method="Purchased leaves at latest submitted non-return PR base_net_amount / stock_qty; plus recorded BOM operations, minus stored BOM scrap credit; no unrecorded labor",
			status="Unavailable" if self.component_gaps else "Recorded BOM components only")
		if self.process_costs is not None:
			self.add(0, [self.root.item], "Known purchased material + process subtotal", "Total",
				self.root.item, self.root.name, quantity=self.root_quantity, uom=self.root.uom,
				root_amount=self.known_total, source_record=self.root.name,
				method="Latest Purchase Receipt materials + retained IQR actual process averages (or recorded BOM operation fallback) + stored scrap credit; sum of available values only",
				status="Partial")
			self.add(0, [self.root.item], "Full manufacturing cost", "Total",
				self.root.item, self.root.name, quantity=self.root_quantity, uom=self.root.uom,
				source_record=self.root.name,
				method="Unavailable until all required processes, quality control, final testing, and shared costs have reliable sources",
				status="Unavailable")
		stored = money(self.root.base_total_cost) if self.root.base_total_cost is not None else None
		self.add(0, [self.root.item], "Stored default BOM total", "Comparison",
			self.root.item, self.root.name, quantity=self.root_quantity, uom=self.root.uom,
			root_amount=stored, source_record=self.root.name,
			method="BOM.base_total_cost from the selected current default BOM; historical booked rates",
			status="Recorded" if stored is not None else "Unavailable")
		self.add(0, [self.root.item], "Change from stored BOM", "Comparison",
			self.root.item, self.root.name,
			root_amount=repriced - stored if repriced is not None and stored is not None else None,
			source_record=self.root.name,
			method="Purchase-repriced BOM value − stored default BOM total",
			status="Recorded" if repriced is not None and stored is not None else "Unavailable")
		return self.rows

	def walk(self, bom, factor, level, path, active):
		start_totals = dict(self.totals)
		start_category_counts = dict(self.category_counts)
		start_gap_count = len(self.gap_events)
		start_coverage_count = len(self.process_coverage_gaps)
		direct_material = Decimal("0")
		direct_material_missing = False
		active = active + (bom.name,)
		_, selection = self.choose_bom(bom.item)
		self.add(level, path, "Current BOM", "Header", bom.item, bom.name,
			quantity=money(bom.quantity) * factor, uom=bom.uom,
			source_record=bom.name,
			method="Selected {0}; BOM quantity × root usage".format(selection))
		if self.process_costs is not None:
			self.emit_process(bom, factor, level, path)
		for item in bom.items:
			quantity = money(item.stock_qty) * factor
			row_path = path + [item.item_code]
			booked = money(item.base_amount) * factor if item.base_amount is not None else None
			child, selection = self.choose_bom(item.item_code)
			base = dict(level=level + 1, path=row_path, item_code=item.item_code,
				bom=bom.name, child_bom=child.name if child else None,
				quantity=quantity, uom=item.stock_uom,
				booked_bom_amount=booked,
				source_record="{0} / {1}".format(bom.name, item.name))
			if money(item.stock_qty) < 0 or (money(item.qty) > 0 and money(item.stock_qty) <= 0):
				direct_material_missing = True
				self.add(line_type="Unusable BOM quantity", category="Materials",
					method="BOM Item.stock_qty must be positive when qty is positive",
					status="Quantity unavailable", included=True, **base)
				continue
			if child:
				if child.name in active:
					self.add(line_type="BOM cycle", category="Materials",
						method="Current-default BOM selection forms a cycle; price cannot be inferred",
						status="Cycle", included=True, **base)
					continue
				if item.stock_uom != child.uom:
					self.add(line_type="Unusable child BOM UOM", category="Materials",
						method="BOM Item.stock_uom {0} differs from selected child BOM.uom {1}; scaling is unavailable".format(
							item.stock_uom, child.uom),
						status="Child BOM UOM mismatch", included=True, **base)
					continue
				self.add(line_type="Selected subassembly", category="Header",
					method="Chosen {0}; purchased receipt for this Item is not used because a current BOM exists".format(selection),
					status="Expanded", **base)
				self.walk(child, quantity / money(child.quantity), level + 1, row_path, active)
				continue
			receipt = self.receipts.get(item.item_code)
			if quantity == 0 and money(item.qty) == 0:
				self.add(line_type="Purchased material", category="Materials",
					root_amount=Decimal("0"), rate=Decimal("0"),
					method="BOM Item requires zero stock quantity", status="Zero BOM quantity",
					included=True, **base)
				continue
			if not receipt:
				direct_material_missing = True
				self.add(line_type="Purchased material", category="Materials",
					method="No submitted non-return, non-free Purchase Receipt with positive accepted stock quantity in this company",
					status="Purchase rate unavailable", included=True, **base)
				continue
			posted = "{0} {1}".format(receipt.posting_date, receipt.posting_time)
			base.update(source_record="{0} / {1}; {2} / {3}".format(
				bom.name, item.name, receipt.parent, receipt.name),
				receipt_qty=money(receipt.stock_qty),
				receipt_base_net_amount=money(receipt.base_net_amount)
					if receipt.base_net_amount is not None else None,
				receipt_posted=posted)
			corrected_uom = bool(item.stock_uom != receipt.stock_uom
				and item.uom == receipt.stock_uom
				and self.stock_uoms.get(item.item_code) == receipt.stock_uom
				and money(item.qty) == money(item.stock_qty))
			if item.stock_uom != receipt.stock_uom and not corrected_uom:
				direct_material_missing = True
				self.add(line_type="Purchased material", category="Materials",
					method="BOM stock UOM {0} differs from receipt stock UOM {1}; Item and BOM row UOM do not prove a conversion".format(
						item.stock_uom, receipt.stock_uom),
					status="Stock UOM mismatch", included=True, **base)
				continue
			if receipt.base_net_amount is None or money(receipt.base_net_amount) <= 0:
				direct_material_missing = True
				self.add(line_type="Purchased material", category="Materials",
					method="Latest qualifying receipt has no positive base net amount; older prices are not substituted",
					status="Purchase rate unavailable", included=True, **base)
				continue
			rate = money(receipt.base_net_amount) / money(receipt.stock_qty)
			direct_material += quantity * rate
			if corrected_uom:
				base["uom"] = receipt.stock_uom
			self.add(line_type="Purchased material", category="Materials",
				rate=rate, root_amount=quantity * rate,
				method=("BOM stock_uom {0} is stale; BOM row.uom and Item.stock_uom both equal receipt stock_uom, and BOM qty = stock_qty; ".format(
					item.stock_uom) if corrected_uom else "") +
					"PR Item.base_net_amount / PR Item.stock_qty × required BOM stock_qty; net of line discount, company currency; receipt UOM {0}, base_net_rate {1}".format(
						receipt.uom, receipt.base_net_rate),
				status="Priced; BOM stock UOM corrected" if corrected_uom else
					"Priced from latest receipt", included=True, **base)
		for op in bom.operations:
			hours = money(op.time_in_mins) / Decimal("60") * factor
			amount = money(op.base_operating_cost) * factor if op.base_operating_cost is not None else None
			priced = amount is not None and (hours == 0 or
				(money(op.base_hour_rate) > 0 and amount > 0))
			category = operation_category(op.operation)
			observed = self.process_costs is not None and category in ("Machining", "Assembly") and (
				self.process_costs.get(bom.item, {}).get(category, {}).get("average") is not None)
			self.add(level + 1, path, "Recorded BOM operation", category,
				bom.item, bom.name, quantity=hours, uom="hour",
				rate=money(op.base_hour_rate) if op.base_hour_rate is not None else None,
				root_amount=amount if priced else None,
				booked_bom_amount=amount,
				source_record="{0} / {1}".format(bom.name, op.name),
				method="Stored BOM Operation.base_operating_cost × root usage; operation: {0}".format(op.operation),
				status="Planned comparison; actual used" if observed else "Recorded" if priced else
					"Operation rate unavailable", included=not observed,
				basis="Planned" if self.process_costs is not None else None)
			if observed:
				if priced:
					self.component_total += amount
				else:
					self.component_gaps.add(category)
		for scrap in bom.scrap_items:
			quantity = money(scrap.stock_qty) * factor
			amount = -money(scrap.base_amount) * factor if scrap.base_amount is not None else None
			priced = amount is not None and (quantity == 0 or
				(money(scrap.base_rate) > 0 and amount < 0))
			self.add(level + 1, path + [scrap.item_code], "Stored BOM scrap credit",
				"Scrap Credit", scrap.item_code, bom.name, quantity=quantity,
				uom=scrap.stock_uom,
				rate=-money(scrap.base_rate) if scrap.base_rate is not None else None,
				root_amount=amount if priced else None,
				booked_bom_amount=amount,
				source_record="{0} / {1}".format(bom.name, scrap.name),
				method="Negative stored BOM Scrap Item.base_amount × root usage; scrap is not repriced from a purchase receipt",
				status="Recorded" if priced else "Scrap valuation unavailable", included=True)
		if self.process_costs is not None:
			self.emit_item_summary(bom, factor, level, path, start_totals,
				start_category_counts,
				start_gap_count, start_coverage_count, direct_material,
				direct_material_missing)

	def emit_process(self, bom, factor, level, path):
		unit_count = money(bom.quantity) * factor
		for category in ("Machining", "Assembly"):
			group = self.process_costs.get(bom.item, {}).get(category, {})
			coverage = "{0}/{1}/{2}".format(group.get("retained", 0),
				group.get("eligible", 0), group.get("total_work_orders", 0))
			average = group.get("average")
			if average is None:
				self.process_coverage_gaps.append((category, " > ".join(path)))
				self.add(level + 1, path, "Process availability", category, bom.item,
					bom.name, source_record=bom.name, coverage=coverage, basis="Actual",
					method="No reconciled completed Work Order process cost for this Item; any recorded BOM operation is shown separately as a planned fallback",
					status="Unavailable")
			else:
				partial = group["eligible"] < group["total_work_orders"]
				if partial:
					self.process_coverage_gaps.append((category, " > ".join(path)))
				self.add(level + 1, path, "Item process cost", category, bom.item,
					bom.name, quantity=unit_count, uom=bom.uom, rate=average,
					root_amount=average * unit_count, item_unit_cost=average,
					observed_qty=group["retained_quantity"],
					observed_amount=group["retained_amount"],
					observed_per_unit=average, coverage=coverage, basis="Actual IQR",
					source_record="Completed Work Orders for {0}".format(bom.item),
					method="Retained source amounts / retained good units × required BOM Item units; IQR fences on WO cost per good unit",
					status="Partial coverage" if partial else "Observed", included=True)
		for category in ("Machining", "Assembly"):
			group = self.process_costs.get(bom.item, {}).get(category, {})
			coverage = "{0}/{1}/{2}".format(group.get("retained", 0),
				group.get("eligible", 0), group.get("total_work_orders", 0))
			for sample in group.get("samples", []):
				decision = "Excluded by IQR" if sample["excluded"] else "Retained"
				self.add(level + 2, path, "Work Order observation", category,
					bom.item, bom.name, source_record=sample["source"],
					observed_qty=sample["quantity"], observed_amount=sample["amount"],
					observed_per_unit=sample["per_unit"], basis="Actual",
					coverage=coverage, sample_decision=decision,
					method="Historical WO amount / accepted good quantity; IQR fences {0} to {1} CHF/unit; source reconciliation {2}".format(
						group.get("lower"), group.get("upper"),
						"passed" if sample["sources_match"] else "failed"),
					status=decision if sample["sources_match"] else "Source mismatch")
				for source in sample["source_rows"]:
					self.add(level + 3, path, "Process source detail", category,
						bom.item, bom.name, quantity=money(source["hours"]),
						uom="hour", rate=money(source["rate"]),
						observed_amount=money(source["amount"]),
						basis="Actual", source_record=source["source_record"],
						coverage=coverage, sample_decision=decision,
						method=source["method"], status=source["source_type"])

	def emit_item_summary(self, bom, factor, level, path, start_totals,
			start_category_counts,
			start_gap_count, start_coverage_count, direct_material,
			direct_material_missing):
		unit_count = money(bom.quantity) * factor
		new_gaps = self.gap_events[start_gap_count:]
		new_coverage = self.process_coverage_gaps[start_coverage_count:]
		self.add(level, path, "Item direct purchased material", "Materials",
			bom.item, bom.name, root_amount=None if direct_material_missing else direct_material,
			item_unit_cost=None if direct_material_missing else direct_material / unit_count,
			basis="Actual purchase", source_record=bom.name,
			method="Purchased leaves directly on this BOM only, at latest Purchase Receipt net rates; excludes expanded child BOMs",
			status="Unavailable" if direct_material_missing else "Recorded")
		known = Decimal("0")
		for category in REPORT_CATEGORIES:
			amount = self.totals[category] - start_totals.get(category, Decimal("0"))
			missing = any(gap[0] == category for gap in new_gaps)
			coverage_gap = any(gap[0] == category for gap in new_coverage)
			has_source = self.category_counts[category] > start_category_counts.get(category, 0)
			known += amount
			self.add(level, path, "Item recursive subtotal", category,
				bom.item, bom.name, quantity=unit_count, uom=bom.uom,
				root_amount=None if missing or not has_source else amount,
				item_unit_cost=None if missing or not has_source else amount / unit_count,
				basis="Planned" if category in ("Quality Control", "Final Testing", "Other Operations") else
					"Actual IQR" if category in ("Machining", "Assembly") else "Latest purchase" if category == "Materials" else "Stored BOM",
				source_record=bom.name,
				method="Recursive sum under this Item, including all selected child BOMs; component rows are counted once",
				status="Unavailable" if missing or not has_source else "Partial coverage" if coverage_gap else "Recorded")
		self.add(level, path, "Item known subtotal", "Total", bom.item, bom.name,
			quantity=unit_count, uom=bom.uom, root_amount=known,
			item_unit_cost=known / unit_count, source_record=bom.name,
			method="Sum of known recursive material, process, other-operation and scrap amounts; incomplete when any source or process coverage is missing",
			status="Partial")
