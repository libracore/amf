"""Read-only screen of active submitted BOM cost sources.

Run through a connected Frappe site with ``write_audit(directory, company)``.
Findings distinguish broken stored relationships from differences against
today's purchase and inventory benchmarks. No BOM or Item is changed.
"""
from __future__ import unicode_literals

import csv
import re
from collections import Counter, defaultdict
from decimal import Decimal

import frappe
from amf.amf.utils import data_artifact as artifacts


PRICE_FLOOR = Decimal("0.01")
PRICE_FRACTION = Decimal("0.01")


def number(value):
	return Decimal(str(value or 0))


def significant(stored, benchmark):
	gap = abs(stored - benchmark)
	return gap >= PRICE_FLOOR and gap >= abs(benchmark) * PRICE_FRACTION


def _load(company):
	headers = {r.name: r for r in frappe.db.sql("""
		SELECT name, item, company, currency, quantity, uom, docstatus, is_active,
			is_default, rm_cost_as_per, set_rate_of_sub_assembly_item_based_on_bom,
			base_total_cost, creation, modified
		FROM `tabBOM`
	""", as_dict=True)}
	items = {r.name: r for r in frappe.db.sql("""
		SELECT name, stock_uom, default_bom, is_purchase_item, valuation_rate,
			last_purchase_rate
		FROM `tabItem`
	""", as_dict=True)}
	active = {name: bom for name, bom in headers.items()
		if bom.docstatus == 1 and bom.is_active and bom.company == company}
	rows = frappe.db.sql("""
		SELECT bi.name, bi.parent, bi.item_code, bi.bom_no, bi.idx, bi.qty,
			bi.uom, bi.stock_qty, bi.stock_uom, bi.conversion_factor,
			bi.base_rate, bi.base_amount
		FROM `tabBOM Item` bi JOIN `tabBOM` b ON b.name = bi.parent
		WHERE b.docstatus = 1 AND b.is_active = 1 AND b.company = %s
		ORDER BY bi.parent, bi.idx
	""", company, as_dict=True)
	operations = frappe.db.sql("""
		SELECT op.parent, op.base_operating_cost
		FROM `tabBOM Operation` op JOIN `tabBOM` b ON b.name = op.parent
		WHERE b.docstatus = 1 AND b.is_active = 1 AND b.company = %s
	""", company, as_dict=True)
	scrap = frappe.db.sql("""
		SELECT s.parent, s.base_amount
		FROM `tabBOM Scrap Item` s JOIN `tabBOM` b ON b.name = s.parent
		WHERE b.docstatus = 1 AND b.is_active = 1 AND b.company = %s
	""", company, as_dict=True)
	receipts = frappe.db.sql("""
		SELECT pri.name, pri.parent, pri.item_code, pri.stock_qty, pri.stock_uom,
			pri.base_net_amount, pr.posting_date, pr.posting_time
		FROM `tabPurchase Receipt Item` pri
		JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
		WHERE pr.company = %s AND pr.docstatus = 1
			AND IFNULL(pr.is_return, 0) = 0
			AND IFNULL(pri.is_free_item, 0) = 0
			AND pri.qty > 0 AND pri.stock_qty > 0 AND pri.base_net_amount > 0
		ORDER BY pri.item_code, pr.posting_date DESC, pr.posting_time DESC,
			pr.creation DESC, pr.name DESC, pri.idx DESC
	""", company, as_dict=True)
	latest_pr = {}
	for receipt in receipts:
		latest_pr.setdefault(receipt.item_code, receipt)
	bins = {r.item_code: r for r in frappe.db.sql("""
		SELECT item_code, SUM(actual_qty) AS qty, SUM(stock_value) AS stock_value
		FROM `tabBin` GROUP BY item_code
	""", as_dict=True)}
	completed = {r.production_item: r.n for r in frappe.db.sql("""
		SELECT production_item, COUNT(*) AS n FROM `tabWork Order`
		WHERE docstatus = 1 AND status = 'Completed' AND produced_qty > 0
			AND company = %s GROUP BY production_item
	""", company, as_dict=True)}
	planning = {r.production_item: r.n for r in frappe.db.sql("""
		SELECT wo.production_item, COUNT(DISTINCT wo.name) AS n
		FROM `tabPlanning` p JOIN `tabWork Order` wo ON wo.name = p.work_order
		WHERE p.docstatus = 1 AND wo.docstatus = 1 AND wo.status = 'Completed'
			AND wo.produced_qty > 0 AND wo.company = %s
			AND p.item_code = wo.production_item
			AND p.temps_de_cycle_min > 0
			AND (p.quantite_validee + p.quantite_scrap) > 0
		GROUP BY wo.production_item
	""", company, as_dict=True)}
	timers = {r.production_item: r.n for r in frappe.db.sql("""
		SELECT wo.production_item, COUNT(DISTINCT wo.name) AS n
		FROM `tabTimer Production` t JOIN `tabWork Order` wo ON wo.name = t.work_order
		WHERE t.status = 'FINISHED' AND t.total_duration > 0
			AND wo.docstatus = 1 AND wo.status = 'Completed'
			AND wo.produced_qty > 0 AND wo.company = %s
		GROUP BY wo.production_item
	""", company, as_dict=True)}
	return headers, items, active, rows, operations, scrap, latest_pr, bins, completed, planning, timers


def audit(company):
	(headers, items, active, rows, operations, scrap, latest_pr, bins,
		completed, planning, timers) = _load(company)
	defaults = {item.default_bom for item in items.values() if item.default_bom in active
		and active[item.default_bom].item == item.name}
	findings = []
	counts = Counter()
	metrics = Counter()
	relevant_items = {bom.item for bom in active.values()}
	relevant_items.update(row.item_code for row in rows)
	row_totals = defaultdict(lambda: Decimal("0"))
	op_totals = defaultdict(lambda: Decimal("0"))
	op_counts = Counter()
	scrap_totals = defaultdict(lambda: Decimal("0"))
	for op in operations:
		op_totals[op.parent] += number(op.base_operating_cost)
		op_counts[op.parent] += 1
	for part in scrap:
		scrap_totals[part.parent] += number(part.base_amount)

	def add(kind, severity, bom=None, row=None, stored_rate=None, benchmark_rate=None,
			stored_amount=None, benchmark_amount=None, source=None, source_date=None,
			detail=None, item_code=None):
		parent = active.get(bom) if bom else None
		unit_count = number(parent.quantity) if parent else Decimal("0")
		difference = stored_amount - benchmark_amount if (
			stored_amount is not None and benchmark_amount is not None) else None
		findings.append(dict(finding_type=kind, severity=severity,
			bom=bom, parent_item=parent.item if parent else None,
			current_default="Yes" if bom in defaults else "No" if bom else None,
			bom_item_row=row.name if row else None,
			component_item=item_code or (row.item_code if row else None),
			linked_bom=row.bom_no if row else None,
			bom_cost_basis=parent.rm_cost_as_per if parent else None,
			bom_created=str(parent.creation) if parent else None,
			bom_modified=str(parent.modified) if parent else None,
			quantity=number(row.stock_qty) if row else None,
			uom=row.stock_uom if row else None,
			stored_rate=stored_rate, benchmark_rate=benchmark_rate,
			stored_amount=stored_amount, benchmark_amount=benchmark_amount,
			difference=difference,
			difference_per_parent_unit=difference / unit_count if difference is not None and unit_count > 0 else None,
			source_record=source, source_date=str(source_date) if source_date else None,
			detail=detail))
		counts[kind] += 1
		if bom in defaults:
			counts[kind + "_current_default"] += 1

	for row in rows:
		bom = active[row.parent]
		item = items.get(row.item_code)
		stored = number(row.base_amount)
		qty = number(row.stock_qty)
		row_totals[bom.name] += stored
		metrics["bom_item_rows"] += 1
		if bom.name in defaults:
			metrics["default_bom_item_rows"] += 1
		if qty > 0 and number(row.qty) > 0 and number(row.conversion_factor) > 0:
			expected = number(row.qty) * number(row.conversion_factor)
			if abs(qty - expected) > max(Decimal("0.000001"), abs(expected) * Decimal("0.000001")):
				add("stock_quantity_conversion_mismatch", "structural", bom.name, row,
					stored_amount=qty, benchmark_amount=expected,
					source=row.name,
					detail="BOM Item.stock_qty differs from qty × conversion_factor; amounts may scale incorrectly")
		if item and row.stock_uom != item.stock_uom:
			add("stock_uom_mismatch", "structural", bom.name, row,
				source=item.name,
				detail="BOM Item.stock_uom differs from current Item.stock_uom ({0})".format(item.stock_uom))
		if qty < 0 and stored < 0:
			add("negative_material_credit", "method_review", bom.name, row,
				stored_amount=stored, source=row.name,
				detail="Negative stock quantity and amount behave as a material credit inside BOM.items; confirm intended scrap/byproduct treatment instead of BOM.scrap_items")
		elif qty < 0 or (number(row.qty) > 0 and qty == 0):
			add("unusable_bom_quantity", "structural", bom.name, row,
				source=row.name, detail="BOM Item quantity is unusable for normal component scaling")
		if row.bom_no:
			metrics["linked_bom_rows"] += 1
			child = headers.get(row.bom_no)
			problem = None
			if not child:
				problem = "Linked BOM does not exist"
			elif child.docstatus != 1:
				problem = "Linked BOM is {0}, not submitted".format(
					"draft" if child.docstatus == 0 else "canceled")
			elif not child.is_active:
				problem = "Linked BOM is submitted but inactive"
			elif child.item != row.item_code:
				problem = "Linked BOM produces {0}, not {1}".format(child.item, row.item_code)
			elif child.company != bom.company or child.currency != bom.currency:
				problem = "Linked BOM company or currency differs from parent"
			elif number(child.quantity) <= 0:
				problem = "Linked BOM quantity is nonpositive"
			elif row.stock_uom != child.uom:
				problem = "BOM Item.stock_uom differs from linked BOM.uom ({0})".format(child.uom)
			if problem:
				add("invalid_linked_bom", "structural", bom.name, row,
					source=row.bom_no, detail=problem)
			else:
				metrics["valid_linked_bom_rows"] += 1
				if bom.name in defaults:
					metrics["default_valid_linked_bom_rows"] += 1
				expected = number(child.base_total_cost) * qty / number(child.quantity)
				if bom.set_rate_of_sub_assembly_item_based_on_bom and significant(stored, expected):
					add("linked_child_cost_mismatch", "cost_inconsistency", bom.name, row,
						stored_rate=stored / qty if qty else None,
						benchmark_rate=number(child.base_total_cost) / number(child.quantity),
						stored_amount=stored, benchmark_amount=expected,
						source=child.name,
						detail="Parent booked child amount differs from linked child's currently stored BOM total; parent policy uses child BOM cost")
			if bom.name in defaults and item and item.default_bom in active and row.bom_no != item.default_bom:
				add("linked_bom_not_current_default", "recipe_review", bom.name, row,
					source=item.default_bom,
					detail="Current parent BOM links a different child revision than Item.default_bom; may be intentional historical recipe")
			if bom.name in defaults and row.item_code in latest_pr and item and item.is_purchase_item and qty > 0:
				receipt = latest_pr[row.item_code]
				if receipt.stock_uom == row.stock_uom:
					purchase_rate = number(receipt.base_net_amount) / number(receipt.stock_qty)
					purchase_amount = purchase_rate * qty
					if significant(stored, purchase_amount):
						add("buy_vs_make_route_gap", "route_review", bom.name, row,
							stored_rate=stored / qty, benchmark_rate=purchase_rate,
							stored_amount=stored, benchmark_amount=purchase_amount,
							source="{0} / {1}".format(receipt.parent, receipt.name),
							source_date=receipt.posting_date,
							detail="Purchased Item also has a linked child BOM; confirm whether this production uses the bought or made route")
			continue
		if qty <= 0:
			continue
		if stored <= 0:
			add("zero_or_negative_leaf_cost", "cost_inconsistency", bom.name, row,
				stored_rate=stored / qty, stored_amount=stored,
				source=row.name, detail="A positive-quantity direct component has no positive booked amount")
		if item and item.default_bom in active and bom.name in defaults:
			add("unlinked_manufactured_component", "recipe_review", bom.name, row,
				source=item.default_bom,
				detail="Direct cost is booked although this Item has an active default BOM; check whether it should be expanded")
		receipt = latest_pr.get(row.item_code)
		if not receipt:
			if item and item.is_purchase_item and bom.name in defaults:
				add("purchased_leaf_without_receipt", "unverifiable", bom.name, row,
					source=item.name,
					detail="No qualifying submitted same-company non-return, non-free Purchase Receipt")
		elif row.stock_uom == receipt.stock_uom:
			metrics["comparable_purchase_leaf_rows"] += 1
			if bom.name in defaults:
				metrics["default_comparable_purchase_leaf_rows"] += 1
			rate = number(receipt.base_net_amount) / number(receipt.stock_qty)
			expected = rate * qty
			if significant(stored, expected):
				add("leaf_vs_latest_purchase_gap", "price_review", bom.name, row,
					stored_rate=stored / qty, benchmark_rate=rate,
					stored_amount=stored, benchmark_amount=expected,
					source="{0} / {1}".format(receipt.parent, receipt.name),
					source_date=receipt.posting_date,
					detail="BOM booked direct component differs by at least CHF 0.01 and 1% from latest net Purchase Receipt; later purchases do not automatically refresh a BOM")
		else:
			add("receipt_stock_uom_mismatch", "unverifiable", bom.name, row,
				source="{0} / {1}".format(receipt.parent, receipt.name),
				source_date=receipt.posting_date,
				detail="BOM stock UOM {0} differs from latest receipt stock UOM {1}; price comparison omitted".format(
					row.stock_uom, receipt.stock_uom))
		bin_row = bins.get(row.item_code)
		if bin_row and number(bin_row.qty) > 0:
			metrics["comparable_stock_leaf_rows"] += 1
			if bom.name in defaults:
				metrics["default_comparable_stock_leaf_rows"] += 1
			rate = number(bin_row.stock_value) / number(bin_row.qty)
			expected = rate * qty
			if rate > 0 and significant(stored, expected):
				add("leaf_vs_current_stock_value_gap", "price_review", bom.name, row,
					stored_rate=stored / qty, benchmark_rate=rate,
					stored_amount=stored, benchmark_amount=expected,
					source="tabBin all warehouses",
					detail="BOM booked direct component differs from today's all-warehouse weighted Bin stock value; this stock value can change with inventory")

	for name, bom in active.items():
		metrics["active_boms"] += 1
		if name in defaults:
			metrics["current_default_boms"] += 1
		calculated = row_totals[name] + op_totals[name] - scrap_totals[name]
		stored = number(bom.base_total_cost)
		if abs(stored - calculated) > Decimal("0.0001"):
			add("bom_header_arithmetic_gap", "structural", name,
				stored_amount=stored, benchmark_amount=calculated,
				source=name,
				detail="BOM.base_total_cost differs from sum of stored Item amounts + Operation amounts − Scrap amounts")
		if name in defaults and not op_counts[name] and (planning.get(bom.item) or timers.get(bom.item)):
			add("observed_process_absent_from_bom_operations", "process_review", name,
				source="Completed Work Orders",
				detail="Default BOM has no operation rows; Item has {0} completed WOs, {1} with valid Planning and {2} with finished Timers. Stored BOM total omits those process hours".format(
					completed.get(bom.item, 0), planning.get(bom.item, 0), timers.get(bom.item, 0)))
	for code, item in items.items():
		if code not in relevant_items:
			continue
		receipt = latest_pr.get(code)
		if receipt and item.stock_uom == receipt.stock_uom and number(item.last_purchase_rate) > 0:
			latest_rate = number(receipt.base_net_amount) / number(receipt.stock_qty)
			if significant(number(item.last_purchase_rate), latest_rate):
				add("item_last_purchase_rate_vs_receipt_gap", "master_data_review",
					stored_rate=number(item.last_purchase_rate), benchmark_rate=latest_rate,
					item_code=code,
					source="{0} / {1}".format(receipt.parent, receipt.name),
					source_date=receipt.posting_date,
					detail="Item.last_purchase_rate differs from latest qualifying same-company Purchase Receipt net rate; ERPNext's 'Last Purchase Rate' BOM option reads the Item field")
		bin_row = bins.get(code)
		if not bin_row or number(bin_row.qty) <= 0:
			continue
		bin_rate = number(bin_row.stock_value) / number(bin_row.qty)
		master_rate = number(item.valuation_rate)
		if bin_rate > 0 and significant(master_rate, bin_rate):
			add("item_master_vs_current_stock_value_gap", "master_data_review",
				stored_rate=master_rate, benchmark_rate=bin_rate,
				source="tabBin all warehouses", item_code=code,
				detail="Item.valuation_rate differs from today's all-warehouse weighted Bin rate; this is Item context, not a BOM row")
	invoices = frappe.db.sql("""
		SELECT pii.name, pii.parent, pii.item_code, pii.rate, pii.base_rate,
			pi.company, pi.currency, pi.posting_date, pii.creation
		FROM `tabPurchase Invoice Item` pii
		JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
		WHERE pi.docstatus = 1 AND pi.company = %s
		ORDER BY pii.item_code, pii.creation DESC, pii.name DESC
	""", company, as_dict=True)
	latest_invoice = {}
	for invoice in invoices:
		latest_invoice.setdefault(invoice.item_code, invoice)
	for code, invoice in latest_invoice.items():
		if code not in relevant_items:
			continue
		item = items.get(code)
		if not item or (item.default_bom in active) or invoice.currency == "CHF":
			continue
		master_rate = number(item.valuation_rate)
		invoice_rate = number(invoice.rate)
		base_rate = number(invoice.base_rate)
		if abs(master_rate - invoice_rate) < Decimal("0.0001") and significant(invoice_rate, base_rate):
			add("foreign_invoice_rate_in_chf_item_master", "master_data_review",
				stored_rate=master_rate, benchmark_rate=base_rate,
				item_code=code,
				source="{0} / {1}".format(invoice.parent, invoice.name),
				source_date=invoice.posting_date,
				detail="Item.valuation_rate matches latest Purchase Invoice Item.rate in {0}, while its base_rate is CHF; weekly Item updater selects transaction rate".format(invoice.currency))
	findings.sort(key=lambda x: (
		0 if x["current_default"] == "Yes" else 1,
		{"structural": 0, "cost_inconsistency": 1, "route_review": 2,
			"price_review": 3, "process_review": 4}.get(x["severity"], 5),
		-abs(x["difference_per_parent_unit"] or Decimal("0")),
		x["bom"] or "", x["bom_item_row"] or ""))
	return findings, dict(metrics), dict(counts)


def write_audit(namespace, company):
	findings, metrics, counts = audit(company)
	artifacts.validate_name(namespace + ".csv")
	output = namespace + "_bom_cost_active_findings.csv"
	fields = ("finding_type", "severity", "bom", "parent_item", "current_default",
		"bom_item_row", "component_item", "linked_bom", "bom_cost_basis",
		"bom_created", "bom_modified", "quantity", "uom", "stored_rate",
		"benchmark_rate", "stored_amount", "benchmark_amount", "difference",
		"difference_per_parent_unit", "source_record", "source_date", "detail")
	with artifacts.csv_output(output, bom=True) as file:
		writer = csv.DictWriter(file, fieldnames=fields)
		writer.writeheader()
		writer.writerows(findings)
	root_output = write_4xxxxx_reachability(namespace, company, findings)
	return output, root_output, metrics, counts


def write_4xxxxx_reachability(namespace, company, findings):
	"""Map source-BOM findings onto today's default-BOM trees of 4XXXXX Items."""
	_, items, active, rows, _, _, _, _, completed, _, _ = _load(company)
	defaults = {code: item.default_bom for code, item in items.items()
		if item.default_bom in active and active[item.default_bom].item == code}
	children = defaultdict(list)
	for row in rows:
		if number(row.stock_qty) > 0:
			children[row.parent].append(row.item_code)
	findings_by_bom = defaultdict(list)
	for finding in findings:
		if finding["bom"]:
			findings_by_bom[finding["bom"]].append(finding)
	output = namespace + "_bom_cost_4xxxxx_root_screen.csv"
	fields = ["item_code", "default_bom", "stored_bom_cost_per_unit", "completed_work_orders",
		"selected_bom_count", "selected_boms", "total_findings_in_tree",
		"invalid_linked_bom", "linked_child_cost_mismatch", "linked_bom_not_current_default",
		"stock_uom_mismatch", "zero_or_negative_leaf_cost", "leaf_vs_latest_purchase_gap",
		"leaf_vs_current_stock_value_gap", "buy_vs_make_route_gap",
		"observed_process_absent_from_bom_operations", "negative_material_credit"]
	with artifacts.csv_output(output, bom=True) as file:
		writer = csv.DictWriter(file, fieldnames=fields)
		writer.writeheader()
		for code in sorted(defaults):
			if not re.match(r"^4[0-9]{5}$", code):
				continue
			root = defaults[code]
			visited = set()
			def visit(bom):
				if bom in visited:
					return
				visited.add(bom)
				for child_code in children[bom]:
					child = defaults.get(child_code)
					if child:
						visit(child)
			visit(root)
			root_findings = [finding for bom in visited for finding in findings_by_bom[bom]]
			frequency = Counter(finding["finding_type"] for finding in root_findings)
			result = dict(item_code=code, default_bom=root,
				stored_bom_cost_per_unit=number(active[root].base_total_cost) / number(active[root].quantity),
				completed_work_orders=completed.get(code, 0),
				selected_bom_count=len(visited), selected_boms="; ".join(sorted(visited)),
				total_findings_in_tree=len(root_findings))
			for field in fields[7:]:
				result[field] = frequency[field]
			writer.writerow(result)
	return output
