# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from collections import defaultdict
from datetime import date, datetime, time, timedelta
import math
import statistics

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, get_datetime, getdate, now_datetime, nowdate


SERVICE_LEVEL_Z = {
	90.0: 1.282,
	95.0: 1.645,
	97.5: 1.960,
	99.0: 2.326,
}
DEFAULT_SERVICE_LEVEL = 95.0
DEFAULT_LOOKBACK_DAYS = 365
DEFAULT_HORIZON_DAYS = 90
DEFAULT_REVIEW_PERIOD_DAYS = 30
DEFAULT_LEAD_TIME_DAYS = 15.0
LEAD_TIME_STD_RATIO = 0.25
MAX_LEAD_TIME_SAMPLES = 50
QUERY_CHUNK_SIZE = 250
MIN_OUTLIER_OBSERVATIONS = 8
RISK_ORDER = {"critical": 0, "action": 1, "watch": 2, "healthy": 3}
CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}

HISTORICAL_DEMAND_PURPOSES = (
	"Manufacture",
	"Material Consumption for Manufacture",
	"Material Issue",
	"Repack",
)
TRANSFER_PURPOSES = (
	"Material Transfer",
	"Material Transfer for Manufacture",
	"Send to Subcontractor",
)


class InventoryPlanningEngine(object):
	"""Time-phased inventory policy and shortage forecasting for ERPNext v12 data."""

	def __init__(
		self,
		company=None,
		item_group=None,
		item_code=None,
		search=None,
		procurement_type=None,
		risk=None,
		service_level=DEFAULT_SERVICE_LEVEL,
		lookback_days=DEFAULT_LOOKBACK_DAYS,
		horizon_days=DEFAULT_HORIZON_DAYS,
		review_period_days=DEFAULT_REVIEW_PERIOD_DAYS,
		page_start=0,
		page_length=100,
	):
		self.company = _get_company(company)
		self.item_group = cstr(item_group).strip() or None
		self.item_code = cstr(item_code).strip() or None
		self.search = cstr(search).strip().lower()
		self.procurement_type = cstr(procurement_type).strip().lower() or "all"
		self.risk = cstr(risk).strip().lower() or "all"
		self.service_level = normalize_service_level(service_level)
		self.z_score = SERVICE_LEVEL_Z[self.service_level]
		self.lookback_days = max(90, min(cint(lookback_days) or DEFAULT_LOOKBACK_DAYS, 1095))
		self.horizon_days = max(30, min(cint(horizon_days) or DEFAULT_HORIZON_DAYS, 365))
		self.review_period_days = max(
			7, min(cint(review_period_days) or DEFAULT_REVIEW_PERIOD_DAYS, 90)
		)
		self.page_start = max(cint(page_start), 0)
		self.page_length = max(1, min(cint(page_length) or 100, 500))
		self.today = getdate(nowdate())
		self.history_start = self.today - timedelta(days=self.lookback_days - 1)
		self.horizon_end = self.today + timedelta(days=self.horizon_days - 1)
		self.warehouses = []
		self.items = []
		self.item_map = {}
		self.history_rows = []
		self.history_by_item = defaultdict(lambda: defaultdict(float))
		self.history_sources = defaultdict(lambda: defaultdict(float))
		self.history_source_days = defaultdict(lambda: defaultdict(set))
		self.history_supply_sources = defaultdict(lambda: defaultdict(float))
		self.history_supply_source_days = defaultdict(lambda: defaultdict(set))
		self.stock_positions = {}
		self.lead_profiles = {}
		self.lead_observations = defaultdict(list)
		self.events = defaultdict(list)
		self.analysis_details = {}

	def build(self, include_detail=False):
		self.warehouses = get_usable_warehouses(self.company)
		self.items = self._get_items()
		self.item_map = {item.name: item for item in self.items}
		item_codes = list(self.item_map.keys())

		if not item_codes:
			return self._empty_result()

		self._load_historical_demand(item_codes)
		self._load_historical_supply(item_codes)
		self.stock_positions = self._get_stock_positions(item_codes)
		self._load_lead_profiles(item_codes)
		self._load_future_events(item_codes)

		rows = []
		global_risk_curve = [
			{"shortage_items": 0, "safety_breach_items": 0}
			for _index in range(self.horizon_days)
		]
		for item in self.items:
			row, detail = self._analyse_item(item)
			rows.append(row)
			for index, point in enumerate(detail["daily_projection"]):
				closing_qty = flt(point.get("closing_qty"))
				if closing_qty < 0:
					global_risk_curve[index]["shortage_items"] += 1
				if closing_qty < flt(row.get("safety_stock")):
					global_risk_curve[index]["safety_breach_items"] += 1
			if include_detail:
				self.analysis_details[item.name] = detail

		rows.sort(
			key=lambda row: (
				RISK_ORDER.get(row.get("risk"), 9),
				row.get("shortage_date") or "9999-12-31",
				-flt(row.get("recommended_qty")),
				cstr(row.get("item_code")).lower(),
			)
		)
		total_candidates = len(rows)
		if self.risk != "all":
			rows = [row for row in rows if row.get("risk") == self.risk]

		summary = build_summary(rows, total_candidates)
		total_rows = len(rows)
		page_rows = rows[self.page_start:self.page_start + self.page_length]

		return {
			"filters": self.get_filters(),
			"summary": summary,
			"items": page_rows,
			"total_rows": total_rows,
			"total_candidates": total_candidates,
			"page_start": self.page_start,
			"page_length": self.page_length,
			"generated_at": cstr(now_datetime()),
			"global_risk_curve": _weekly_global_risk_curve(
				global_risk_curve, self.today
			),
			"methodology": get_methodology(),
		}

	def get_filters(self):
		return {
			"company": self.company,
			"item_group": self.item_group,
			"item_code": self.item_code,
			"search": self.search,
			"procurement_type": self.procurement_type,
			"risk": self.risk,
			"service_level": self.service_level,
			"z_score": self.z_score,
			"lookback_days": self.lookback_days,
			"horizon_days": self.horizon_days,
			"review_period_days": self.review_period_days,
		}

	def get_item_detail(self, item_code):
		detail = self.analysis_details.get(item_code)
		if not detail:
			return None

		detail["recent_movements"] = self._get_recent_movements(item_code)
		detail["warehouse_stock"] = self._get_warehouse_stock(item_code)
		detail["weekly_projection"] = weekly_projection(
			detail.get("daily_projection") or []
		)
		return detail

	def _empty_result(self):
		return {
			"filters": self.get_filters(),
			"summary": build_summary([], 0),
			"items": [],
			"total_rows": 0,
			"total_candidates": 0,
			"page_start": self.page_start,
			"page_length": self.page_length,
			"generated_at": cstr(now_datetime()),
			"global_risk_curve": [],
			"methodology": get_methodology(),
		}

	def _get_items(self):
		fields = [
			"name",
			"item_name",
			"item_group",
			"stock_uom",
			"creation",
			"is_purchase_item",
			"default_bom",
			"min_order_qty",
			"safety_stock",
			"lead_time_days",
		]
		meta = frappe.get_meta("Item")
		for optional_field in (
			"reference_code",
			"reorder_level",
			"reorder",
			"average_monthly_outflow",
			"annual_outflow",
		):
			if meta.has_field(optional_field):
				fields.append(optional_field)

		filters = {
			"disabled": 0,
			"is_stock_item": 1,
		}
		if self.item_code:
			filters["name"] = self.item_code
		if self.item_group:
			filters["item_group"] = ["in", get_item_group_scope(self.item_group)]
		if self.procurement_type == "purchase":
			filters["is_purchase_item"] = 1
		elif self.procurement_type == "manufacture":
			filters["is_purchase_item"] = 0

		items = frappe.get_all(
			"Item",
			filters=filters,
			fields=fields,
			order_by="name asc",
			limit_page_length=0,
		)
		if not self.search:
			return items

		def matches(item):
			haystack = " ".join(
				cstr(item.get(fieldname))
				for fieldname in ("name", "item_name", "item_group", "reference_code")
			).lower()
			return self.search in haystack

		return [item for item in items if matches(item)]

	def _load_historical_demand(self, item_codes):
		if not self.warehouses:
			return

		warehouse_names = [warehouse.name for warehouse in self.warehouses]
		for item_chunk in chunks(item_codes, QUERY_CHUNK_SIZE):
			item_placeholders = sql_placeholders(item_chunk)
			warehouse_placeholders = sql_placeholders(warehouse_names)
			purpose_placeholders = sql_placeholders(HISTORICAL_DEMAND_PURPOSES)
			query = """
				SELECT
					sle.item_code,
					sle.posting_date,
					CASE
						WHEN sle.voucher_type IN ('Delivery Note', 'Sales Invoice')
							THEN 'Customer deliveries'
						WHEN sle.voucher_type = 'Stock Entry'
							AND se.purpose IN ('Manufacture', 'Material Consumption for Manufacture')
							THEN 'Manufacturing consumption'
						WHEN sle.voucher_type = 'Stock Entry' AND se.purpose = 'Material Issue'
							THEN 'Material issues'
						WHEN sle.voucher_type = 'Stock Entry' AND se.purpose = 'Repack'
							THEN 'Repack consumption'
						ELSE 'Other consumption'
					END AS demand_source,
					COALESCE(-SUM(sle.actual_qty), 0) AS qty
				FROM `tabStock Ledger Entry` sle
				LEFT JOIN `tabStock Entry` se
					ON se.name = sle.voucher_no
					AND sle.voucher_type = 'Stock Entry'
				WHERE sle.item_code IN ({items})
					AND sle.warehouse IN ({warehouses})
					AND sle.posting_date BETWEEN %s AND %s
					AND sle.actual_qty < 0
					AND IFNULL(sle.is_cancelled, 'No') = 'No'
					AND (
						sle.voucher_type IN ('Delivery Note', 'Sales Invoice')
						OR (
							sle.voucher_type = 'Stock Entry'
							AND se.docstatus = 1
							AND se.purpose IN ({purposes})
						)
					)
				GROUP BY sle.item_code, sle.posting_date, demand_source
			""".format(
				items=item_placeholders,
				warehouses=warehouse_placeholders,
				purposes=purpose_placeholders,
			)
			args = (
				list(item_chunk)
				+ warehouse_names
				+ [self.history_start, self.today]
				+ list(HISTORICAL_DEMAND_PURPOSES)
			)
			rows = frappe.db.sql(query, tuple(args), as_dict=True)
			self.history_rows.extend(rows)
			for row in rows:
				posting_date = getdate(row.posting_date)
				qty = flt(row.qty)
				self.history_by_item[row.item_code][posting_date] += qty
				self.history_sources[row.item_code][row.demand_source] += qty
				if qty:
					self.history_source_days[row.item_code][row.demand_source].add(posting_date)

	def _get_stock_positions(self, item_codes):
		positions = {
			item_code: {
				"actual_qty": 0.0,
				"reserved_sales_qty": 0.0,
				"reserved_production_qty": 0.0,
				"reserved_subcontract_qty": 0.0,
				"ordered_qty": 0.0,
				"planned_qty": 0.0,
				"requested_qty": 0.0,
				"erp_projected_qty": 0.0,
			}
			for item_code in item_codes
		}
		if not self.warehouses:
			return positions

		warehouse_names = [warehouse.name for warehouse in self.warehouses]
		for item_chunk in chunks(item_codes, QUERY_CHUNK_SIZE):
			rows = frappe.db.sql(
				"""
				SELECT
					item_code,
					COALESCE(SUM(actual_qty), 0) AS actual_qty,
					COALESCE(SUM(reserved_qty), 0) AS reserved_sales_qty,
					COALESCE(SUM(reserved_qty_for_production), 0) AS reserved_production_qty,
					COALESCE(SUM(reserved_qty_for_sub_contract), 0) AS reserved_subcontract_qty,
					COALESCE(SUM(ordered_qty), 0) AS ordered_qty,
					COALESCE(SUM(planned_qty), 0) AS planned_qty,
					COALESCE(SUM(indented_qty), 0) AS requested_qty,
					COALESCE(SUM(projected_qty), 0) AS erp_projected_qty
				FROM `tabBin`
				WHERE item_code IN ({items})
					AND warehouse IN ({warehouses})
				GROUP BY item_code
				""".format(
					items=sql_placeholders(item_chunk),
					warehouses=sql_placeholders(warehouse_names),
				),
				tuple(list(item_chunk) + warehouse_names),
				as_dict=True,
			)
			for row in rows:
				positions[row.item_code] = {
					fieldname: flt(row.get(fieldname))
					for fieldname in positions[row.item_code]
				}
		return positions

	def _load_historical_supply(self, item_codes):
		if not self.warehouses:
			return

		warehouse_names = [warehouse.name for warehouse in self.warehouses]
		for item_chunk in chunks(item_codes, QUERY_CHUNK_SIZE):
			rows = frappe.db.sql(
				"""
				SELECT
					sle.item_code,
					sle.posting_date,
					CASE
						WHEN sle.voucher_type = 'Purchase Receipt'
							THEN 'Purchase receipts'
						WHEN sle.voucher_type = 'Stock Entry' AND se.purpose = 'Manufacture'
							THEN 'Manufactured output'
						WHEN sle.voucher_type = 'Stock Entry' AND se.purpose = 'Material Receipt'
							THEN 'Material receipts'
						WHEN sle.voucher_type = 'Stock Entry' AND se.purpose = 'Repack'
							THEN 'Repack output'
						ELSE 'Other input'
					END AS supply_source,
					COALESCE(SUM(sle.actual_qty), 0) AS qty
				FROM `tabStock Ledger Entry` sle
				LEFT JOIN `tabStock Entry` se
					ON se.name = sle.voucher_no
					AND sle.voucher_type = 'Stock Entry'
				WHERE sle.item_code IN ({items})
					AND sle.warehouse IN ({warehouses})
					AND sle.posting_date BETWEEN %s AND %s
					AND sle.actual_qty > 0
					AND IFNULL(sle.is_cancelled, 'No') = 'No'
					AND (
						sle.voucher_type = 'Purchase Receipt'
						OR (
							sle.voucher_type = 'Stock Entry'
							AND se.docstatus = 1
							AND se.purpose IN ('Manufacture', 'Material Receipt', 'Repack')
						)
					)
				GROUP BY sle.item_code, sle.posting_date, supply_source
				""".format(
					items=sql_placeholders(item_chunk),
					warehouses=sql_placeholders(warehouse_names),
				),
				tuple(
					list(item_chunk)
					+ warehouse_names
					+ [self.history_start, self.today]
				),
				as_dict=True,
			)
			for row in rows:
				posting_date = getdate(row.posting_date)
				qty = flt(row.qty)
				self.history_supply_sources[row.item_code][row.supply_source] += qty
				if qty:
					self.history_supply_source_days[row.item_code][row.supply_source].add(
						posting_date
					)

	def _load_lead_profiles(self, item_codes):
		purchase_observations = self._get_purchase_lead_observations(item_codes)
		manufacturing_observations = self._get_manufacturing_lead_observations(item_codes)

		for item in self.items:
			observations = (
				purchase_observations.get(item.name, [])
				if cint(item.is_purchase_item)
				else manufacturing_observations.get(item.name, [])
			)
			observations = sorted(
				observations,
				key=lambda observation: observation.get("finish_date") or date.min,
				reverse=True,
			)[:MAX_LEAD_TIME_SAMPLES]
			self.lead_observations[item.name] = observations
			self.lead_profiles[item.name] = build_lead_profile(
				observations,
				fallback_days=flt(item.lead_time_days) or DEFAULT_LEAD_TIME_DAYS,
				source_type="purchase" if cint(item.is_purchase_item) else "manufacture",
				fallback_source=(
					"Item lead time"
					if flt(item.lead_time_days)
					else "Default lead time"
				),
			)

	def _get_purchase_lead_observations(self, item_codes):
		result = defaultdict(list)
		for item_chunk in chunks(item_codes, QUERY_CHUNK_SIZE):
			rows = frappe.db.sql(
				"""
				SELECT
					pri.item_code,
					DATEDIFF(pr.posting_date, po.transaction_date) AS lead_time_days,
					COALESCE(NULLIF(pri.stock_qty, 0), pri.qty, 1) AS weight,
					po.name AS start_document,
					pr.name AS finish_document,
					po.transaction_date AS start_date,
					pr.posting_date AS finish_date,
					po.supplier AS party
				FROM `tabPurchase Receipt Item` pri
				INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
				INNER JOIN `tabPurchase Order Item` poi
					ON poi.name = pri.purchase_order_item
				INNER JOIN `tabPurchase Order` po ON po.name = poi.parent
				WHERE pri.item_code IN ({items})
					AND pr.company = %s
					AND pri.docstatus = 1
					AND pr.docstatus = 1
					AND po.docstatus = 1
					AND IFNULL(pr.is_return, 0) = 0
					AND COALESCE(NULLIF(pri.stock_qty, 0), pri.qty, 0) > 0
					AND DATEDIFF(pr.posting_date, po.transaction_date) >= 0
				ORDER BY pr.posting_date DESC, pr.posting_time DESC
				""".format(items=sql_placeholders(item_chunk)),
				tuple(list(item_chunk) + [self.company]),
				as_dict=True,
			)
			for row in rows:
				result[row.item_code].append({
					"days": flt(row.lead_time_days),
					"weight": flt(row.weight) or 1,
					"source": "PO → PREC",
					"start_document": row.start_document,
					"finish_document": row.finish_document,
					"start_date": cstr(row.start_date),
					"finish_date": getdate(row.finish_date),
					"party": row.party,
				})
		return result

	def _get_manufacturing_lead_observations(self, item_codes):
		result = defaultdict(list)
		for item_chunk in chunks(item_codes, QUERY_CHUNK_SIZE):
			rows = frappe.db.sql(
				"""
				SELECT
					wo.production_item AS item_code,
					wo.name AS work_order,
					se.name AS stock_entry,
					se.posting_date,
					se.posting_time,
					COALESCE(NULLIF(se.fg_completed_qty, 0), wo.produced_qty, 1) AS weight,
					planning.planning_start,
					wo.actual_start_date,
					wo.planned_start_date,
					wo.creation AS work_order_creation
				FROM `tabStock Entry` se
				INNER JOIN `tabWork Order` wo ON wo.name = se.work_order
				LEFT JOIN (
					SELECT work_order, MIN(date_de_debut) AS planning_start
					FROM `tabPlanning`
					WHERE docstatus < 2
						AND IFNULL(work_order, '') != ''
					GROUP BY work_order
				) planning ON planning.work_order = wo.name
				WHERE wo.production_item IN ({items})
					AND wo.company = %s
					AND se.docstatus = 1
					AND se.purpose = 'Manufacture'
					AND IFNULL(se.work_order, '') != ''
					AND IFNULL(se.fg_completed_qty, 0) > 0
				ORDER BY se.posting_date DESC, se.posting_time DESC
				""".format(items=sql_placeholders(item_chunk)),
				tuple(list(item_chunk) + [self.company]),
				as_dict=True,
			)
			for row in rows:
				finish_at = combine_datetime(row.posting_date, row.posting_time)
				start_at = None
				source = None
				for candidate, candidate_source in (
					(row.planning_start, "Planning → Manufacture"),
					(row.actual_start_date, "WO actual → Manufacture"),
					(row.planned_start_date, "WO planned → Manufacture"),
					(row.work_order_creation, "WO creation → Manufacture"),
				):
					candidate = as_datetime(candidate)
					if candidate and finish_at and candidate <= finish_at:
						start_at = candidate
						source = candidate_source
						break
				if not start_at or not finish_at:
					continue
				lead_time_days = max(
					1.0, math.ceil((finish_at - start_at).total_seconds() / 86400.0)
				)
				result[row.item_code].append({
					"days": lead_time_days,
					"weight": flt(row.weight) or 1,
					"source": source,
					"start_document": row.work_order,
					"finish_document": row.stock_entry,
					"start_date": cstr(start_at.date()),
					"finish_date": finish_at.date(),
					"party": None,
				})
		return result

	def _load_future_events(self, item_codes):
		self._load_purchase_order_supply(item_codes)
		self._load_work_order_events(item_codes)
		self._load_sales_order_demand(item_codes)
		self._load_material_request_supply(item_codes)
		self._load_unlinked_planning_supply(item_codes)

	def _add_event(
		self,
		item_code,
		event_date,
		qty,
		direction,
		source,
		document_type,
		document_name,
		confidence="firm",
		warehouse=None,
		party=None,
	):
		qty = flt(qty)
		if item_code not in self.item_map or qty <= 0:
			return
		event_date = getdate(event_date or self.today)
		if event_date < self.today:
			event_date = self.today
		if event_date > self.horizon_end:
			return
		self.events[item_code].append({
			"date": event_date,
			"qty": qty,
			"direction": direction,
			"source": source,
			"document_type": document_type,
			"document_name": document_name,
			"confidence": confidence,
			"warehouse": warehouse,
			"party": party,
		})

	def _load_purchase_order_supply(self, item_codes):
		for item_chunk in chunks(item_codes, QUERY_CHUNK_SIZE):
			rows = frappe.db.sql(
				"""
				SELECT
					poi.item_code,
					COALESCE(poi.schedule_date, po.transaction_date) AS due_date,
					(poi.qty - poi.received_qty) * IFNULL(poi.conversion_factor, 1) AS qty,
					po.name,
					po.supplier,
					poi.warehouse
				FROM `tabPurchase Order Item` poi
				INNER JOIN `tabPurchase Order` po ON po.name = poi.parent
				WHERE poi.item_code IN ({items})
					AND po.company = %s
					AND po.docstatus = 1
					AND po.status NOT IN ('Closed', 'Delivered', 'Cancelled')
					AND poi.qty > poi.received_qty
					AND IFNULL(poi.delivered_by_supplier, 0) = 0
				""".format(items=sql_placeholders(item_chunk)),
				tuple(list(item_chunk) + [self.company]),
				as_dict=True,
			)
			for row in rows:
				self._add_event(
					row.item_code,
					row.due_date,
					row.qty,
					"supply",
					"Purchase Order",
					"Purchase Order",
					row.name,
					warehouse=row.warehouse,
					party=row.supplier,
				)

	def _load_work_order_events(self, item_codes):
		for item_chunk in chunks(item_codes, QUERY_CHUNK_SIZE):
			supply_rows = frappe.db.sql(
				"""
				SELECT
					wo.production_item AS item_code,
					COALESCE(planning.planning_end, wo.planned_end_date, CURDATE()) AS due_date,
					wo.qty - wo.produced_qty AS qty,
					wo.name,
					wo.fg_warehouse
				FROM `tabWork Order` wo
				LEFT JOIN (
					SELECT work_order, MAX(date_de_fin) AS planning_end
					FROM `tabPlanning`
					WHERE docstatus < 2
						AND IFNULL(work_order, '') != ''
					GROUP BY work_order
				) planning ON planning.work_order = wo.name
				WHERE wo.production_item IN ({items})
					AND wo.company = %s
					AND wo.docstatus = 1
					AND wo.status NOT IN ('Stopped', 'Completed', 'Cancelled')
					AND wo.qty > wo.produced_qty
				""".format(items=sql_placeholders(item_chunk)),
				tuple(list(item_chunk) + [self.company]),
				as_dict=True,
			)
			for row in supply_rows:
				self._add_event(
					row.item_code,
					row.due_date,
					row.qty,
					"supply",
					"Work Order output",
					"Work Order",
					row.name,
					warehouse=row.fg_warehouse,
				)

			demand_rows = frappe.db.sql(
				"""
				SELECT
					woi.item_code,
					COALESCE(planning.planning_start, wo.planned_start_date, CURDATE()) AS due_date,
					GREATEST(woi.required_qty - IFNULL(woi.consumed_qty, 0), 0) AS qty,
					wo.name,
					woi.source_warehouse
				FROM `tabWork Order Item` woi
				INNER JOIN `tabWork Order` wo ON wo.name = woi.parent
				LEFT JOIN (
					SELECT work_order, MIN(date_de_debut) AS planning_start
					FROM `tabPlanning`
					WHERE docstatus < 2
						AND IFNULL(work_order, '') != ''
					GROUP BY work_order
				) planning ON planning.work_order = wo.name
				WHERE woi.item_code IN ({items})
					AND wo.company = %s
					AND wo.docstatus = 1
					AND wo.status NOT IN ('Stopped', 'Completed', 'Cancelled')
					AND woi.required_qty > IFNULL(woi.consumed_qty, 0)
				""".format(items=sql_placeholders(item_chunk)),
				tuple(list(item_chunk) + [self.company]),
				as_dict=True,
			)
			for row in demand_rows:
				self._add_event(
					row.item_code,
					row.due_date,
					row.qty,
					"demand",
					"Work Order material",
					"Work Order",
					row.name,
					warehouse=row.source_warehouse,
				)

	def _load_sales_order_demand(self, item_codes):
		for item_chunk in chunks(item_codes, QUERY_CHUNK_SIZE):
			standard_rows = frappe.db.sql(
				"""
				SELECT
					soi.item_code,
					COALESCE(soi.delivery_date, so.delivery_date, CURDATE()) AS due_date,
					(soi.qty - soi.delivered_qty) * IFNULL(soi.conversion_factor, 1) AS qty,
					so.name,
					so.customer_name AS party,
					soi.warehouse
				FROM `tabSales Order Item` soi
				INNER JOIN `tabSales Order` so ON so.name = soi.parent
				WHERE soi.item_code IN ({items})
					AND so.company = %s
					AND so.docstatus = 1
					AND so.status NOT IN ('Closed', 'Completed', 'Cancelled')
					AND soi.qty > soi.delivered_qty
					AND IFNULL(soi.delivered_by_supplier, 0) = 0
					AND NOT EXISTS (
						SELECT 1
						FROM `tabPacked Item` packed
						WHERE packed.parent_detail_docname = soi.name
							AND packed.parenttype = 'Sales Order'
							AND packed.docstatus = 1
					)
				""".format(items=sql_placeholders(item_chunk)),
				tuple(list(item_chunk) + [self.company]),
				as_dict=True,
			)
			for row in standard_rows:
				self._add_event(
					row.item_code,
					row.due_date,
					row.qty,
					"demand",
					"Sales Order",
					"Sales Order",
					row.name,
					warehouse=row.warehouse,
					party=row.party,
				)

			packed_rows = frappe.db.sql(
				"""
				SELECT
					packed.item_code,
					COALESCE(soi.delivery_date, so.delivery_date, CURDATE()) AS due_date,
					packed.qty * ((soi.qty - soi.delivered_qty) / NULLIF(soi.qty, 0)) AS qty,
					so.name,
					so.customer_name AS party,
					packed.warehouse
				FROM `tabPacked Item` packed
				INNER JOIN `tabSales Order Item` soi
					ON soi.name = packed.parent_detail_docname
				INNER JOIN `tabSales Order` so ON so.name = soi.parent
				WHERE packed.item_code IN ({items})
					AND packed.parenttype = 'Sales Order'
					AND packed.docstatus = 1
					AND so.company = %s
					AND so.docstatus = 1
					AND so.status NOT IN ('Closed', 'Completed', 'Cancelled')
					AND soi.qty > soi.delivered_qty
					AND IFNULL(soi.delivered_by_supplier, 0) = 0
				""".format(items=sql_placeholders(item_chunk)),
				tuple(list(item_chunk) + [self.company]),
				as_dict=True,
			)
			for row in packed_rows:
				self._add_event(
					row.item_code,
					row.due_date,
					row.qty,
					"demand",
					"Sales Order bundle",
					"Sales Order",
					row.name,
					warehouse=row.warehouse,
					party=row.party,
				)

	def _load_material_request_supply(self, item_codes):
		for item_chunk in chunks(item_codes, QUERY_CHUNK_SIZE):
			rows = frappe.db.sql(
				"""
				SELECT
					mri.item_code,
					COALESCE(mri.schedule_date, mr.transaction_date, CURDATE()) AS due_date,
					(mri.qty - mri.ordered_qty) * IFNULL(mri.conversion_factor, 1) AS qty,
					mr.name,
					mr.material_request_type,
					mri.warehouse
				FROM `tabMaterial Request Item` mri
				INNER JOIN `tabMaterial Request` mr ON mr.name = mri.parent
				WHERE mri.item_code IN ({items})
					AND mr.company = %s
					AND mr.docstatus = 1
					AND mr.status NOT IN ('Stopped', 'Cancelled')
					AND mr.material_request_type IN ('Purchase', 'Manufacture')
					AND mri.qty > mri.ordered_qty
				""".format(items=sql_placeholders(item_chunk)),
				tuple(list(item_chunk) + [self.company]),
				as_dict=True,
			)
			for row in rows:
				self._add_event(
					row.item_code,
					row.due_date,
					row.qty,
					"supply",
					"Material Request ({0})".format(row.material_request_type),
					"Material Request",
					row.name,
					confidence="soft",
					warehouse=row.warehouse,
				)

	def _load_unlinked_planning_supply(self, item_codes):
		for item_chunk in chunks(item_codes, QUERY_CHUNK_SIZE):
			rows = frappe.db.sql(
				"""
				SELECT
					item_code,
					COALESCE(date_de_fin, CURDATE()) AS due_date,
					quantite_validee AS qty,
					name
				FROM `tabPlanning`
				WHERE item_code IN ({items})
					AND entreprise = %s
					AND docstatus < 2
					AND IFNULL(work_order, '') = ''
					AND IFNULL(stock_entry, '') = ''
					AND IFNULL(quantite_validee, 0) > 0
					AND COALESCE(date_de_fin, CURDATE()) >= CURDATE()
				""".format(items=sql_placeholders(item_chunk)),
				tuple(list(item_chunk) + [self.company]),
				as_dict=True,
			)
			for row in rows:
				self._add_event(
					row.item_code,
					row.due_date,
					row.qty,
					"supply",
					"Unlinked Planning",
					"Planning",
					row.name,
					confidence="soft",
				)

	def _analyse_item(self, item):
		item_start = max(self.history_start, getdate(item.creation))
		profile = build_demand_profile(
			self.history_by_item.get(item.name, {}),
			item_start,
			self.today,
		)
		lead = self.lead_profiles[item.name]
		policy = calculate_inventory_policy(
			profile,
			lead,
			self.z_score,
			self.review_period_days,
		)
		stock = self.stock_positions.get(item.name) or {}
		item_events = sorted(
			self.events.get(item.name, []),
			key=lambda event: (
				event.get("date"),
				0 if event.get("direction") == "supply" else 1,
				event.get("source"),
			),
		)
		projection = project_inventory(
			opening_qty=flt(stock.get("actual_qty")),
			safety_stock=policy["safety_stock"],
			forecast_daily=profile["forecast_daily"],
			start_date=self.today,
			horizon_days=self.horizon_days,
			events=item_events,
		)
		recommendation = build_recommendation(
			projection=projection,
			lead_time_days=lead["average_days"],
			review_period_days=self.review_period_days,
			safety_stock=policy["safety_stock"],
			min_order_qty=flt(item.min_order_qty),
			procurement_type="Purchase" if cint(item.is_purchase_item) else "Manufacture",
			today=self.today,
		)
		confidence = combine_confidence(profile["confidence"], lead["confidence"])
		risk = classify_risk(projection, recommendation, confidence, profile)
		free_qty = (
			flt(stock.get("actual_qty"))
			- flt(stock.get("reserved_sales_qty"))
			- flt(stock.get("reserved_production_qty"))
			- flt(stock.get("reserved_subcontract_qty"))
		)

		row = {
			"item_code": item.name,
			"item_name": item.item_name or item.name,
			"reference_code": item.get("reference_code") or "",
			"item_group": item.item_group,
			"stock_uom": item.stock_uom,
			"procurement_type": recommendation["procurement_type"],
			"risk": risk,
			"confidence": confidence,
			"actual_qty": flt(stock.get("actual_qty")),
			"free_qty": free_qty,
			"erp_projected_qty": flt(stock.get("erp_projected_qty")),
			"firm_supply_qty": projection["firm_supply_qty"],
			"soft_supply_qty": projection["soft_supply_qty"],
			"firm_demand_qty": projection["firm_demand_qty"],
			"forecast_daily": profile["forecast_daily"],
			"average_monthly_demand": profile["forecast_daily"] * 30.0,
			"demand_days": profile["demand_days"],
			"history_days": profile["history_days"],
			"demand_pattern": profile["pattern"],
			"trend": profile["trend"],
			"lead_time_days": lead["average_days"],
			"lead_time_std_days": lead["std_days"],
			"lead_time_samples": lead["sample_count"],
			"lead_time_source": lead["source"],
			"lead_time_confidence": lead["confidence"],
			"safety_stock": policy["safety_stock"],
			"current_safety_stock": flt(item.safety_stock),
			"reorder_level": policy["reorder_level"],
			"current_reorder_level": flt(item.get("reorder_level")),
			"order_up_to_level": policy["order_up_to_level"],
			"minimum_projected_qty": projection["minimum_projected_qty"],
			"ending_projected_qty": projection["ending_projected_qty"],
			"safety_breach_date": projection["safety_breach_date"],
			"shortage_date": projection["shortage_date"],
			"shortage_qty": projection["shortage_qty"],
			"recommended_qty": recommendation["recommended_qty"],
			"recommended_order_date": recommendation["recommended_order_date"],
			"expedite": recommendation["expedite"],
			"action": recommendation["action"],
		}
		detail = {
			"item": row,
			"demand_profile": profile,
			"lead_time": lead,
			"policy": policy,
			"projection": {
				key: value
				for key, value in projection.items()
				if key != "daily_projection"
			},
			"daily_projection": projection["daily_projection"],
			"future_events": [
				serialize_event(event) for event in item_events
			],
			"historical_demand_sources": [
				{
					"source": source,
					"qty": qty,
					"active_days": len(self.history_source_days[item.name][source]),
				}
				for source, qty in sorted(
					self.history_sources.get(item.name, {}).items(),
					key=lambda pair: -pair[1],
				)
			],
			"historical_supply_sources": [
				{
					"source": source,
					"qty": qty,
					"active_days": len(
						self.history_supply_source_days[item.name][source]
					),
				}
				for source, qty in sorted(
					self.history_supply_sources.get(item.name, {}).items(),
					key=lambda pair: -pair[1],
				)
			],
			"lead_samples": [
				serialize_lead_observation(observation)
				for observation in self.lead_observations.get(item.name, [])
			],
		}
		return row, detail

	def _get_recent_movements(self, item_code):
		if not self.warehouses:
			return []
		warehouse_names = [warehouse.name for warehouse in self.warehouses]
		rows = frappe.db.sql(
			"""
			SELECT
				sle.posting_date,
				sle.posting_time,
				sle.actual_qty,
				sle.qty_after_transaction,
				sle.warehouse,
				sle.voucher_type,
				sle.voucher_no,
				IFNULL(se.purpose, '') AS purpose
			FROM `tabStock Ledger Entry` sle
			LEFT JOIN `tabStock Entry` se
				ON se.name = sle.voucher_no
				AND sle.voucher_type = 'Stock Entry'
			WHERE sle.item_code = %s
				AND sle.warehouse IN ({warehouses})
				AND IFNULL(sle.is_cancelled, 'No') = 'No'
			ORDER BY sle.posting_date DESC, sle.posting_time DESC, sle.creation DESC
			LIMIT 60
			""".format(warehouses=sql_placeholders(warehouse_names)),
			tuple([item_code] + warehouse_names),
			as_dict=True,
		)
		return [
			{
				"posting_date": cstr(row.posting_date),
				"posting_time": cstr(row.posting_time),
				"qty": flt(row.actual_qty),
				"balance_qty": flt(row.qty_after_transaction),
				"warehouse": row.warehouse,
				"voucher_type": row.voucher_type,
				"voucher_no": row.voucher_no,
				"purpose": row.purpose,
				"flow_class": classify_stock_movement(row),
			}
			for row in rows
		]

	def _get_warehouse_stock(self, item_code):
		warehouse_map = {warehouse.name: warehouse for warehouse in self.warehouses}
		rows = frappe.get_all(
			"Bin",
			filters={
				"item_code": item_code,
				"warehouse": ["in", list(warehouse_map.keys())],
			},
			fields=[
				"warehouse",
				"actual_qty",
				"reserved_qty",
				"reserved_qty_for_production",
				"reserved_qty_for_sub_contract",
				"ordered_qty",
				"planned_qty",
				"indented_qty",
				"projected_qty",
			],
			limit_page_length=0,
		)
		result = []
		for row in rows:
			warehouse = warehouse_map.get(row.warehouse)
			result.append({
				"warehouse": row.warehouse,
				"warehouse_name": warehouse.warehouse_name if warehouse else row.warehouse,
				"actual_qty": flt(row.actual_qty),
				"reserved_sales_qty": flt(row.reserved_qty),
				"reserved_production_qty": flt(row.reserved_qty_for_production),
				"reserved_subcontract_qty": flt(row.reserved_qty_for_sub_contract),
				"ordered_qty": flt(row.ordered_qty),
				"planned_qty": flt(row.planned_qty),
				"requested_qty": flt(row.indented_qty),
				"erp_projected_qty": flt(row.projected_qty),
			})
		return sorted(result, key=lambda row: cstr(row["warehouse_name"]).lower())


def normalize_service_level(value):
	try:
		value = float(value)
	except (TypeError, ValueError):
		value = DEFAULT_SERVICE_LEVEL
	return min(SERVICE_LEVEL_Z, key=lambda service_level: abs(service_level - value))


def build_demand_profile(demand_by_day, start_date, end_date):
	"""Build a zero-filled, recency-weighted physical-consumption profile."""
	start_date = getdate(start_date)
	end_date = getdate(end_date)
	if start_date > end_date:
		start_date = end_date
	history_days = (end_date - start_date).days + 1
	raw = [
		flt(demand_by_day.get(start_date + timedelta(days=offset)))
		for offset in range(history_days)
	]
	adjusted, outlier_cap, capped_days = winsorize_demand(raw)
	weights = [
		math.pow(0.5, float(history_days - index - 1) / 90.0)
		for index in range(history_days)
	]
	weighted_mean = weighted_average(adjusted, weights)
	weighted_variance = weighted_population_variance(adjusted, weights, weighted_mean)
	daily_std = math.sqrt(max(weighted_variance, 0.0))
	raw_mean = statistics.mean(raw) if raw else 0.0
	if raw_mean > 0:
		weighted_mean = min(max(weighted_mean, raw_mean * 0.5), raw_mean * 2.0)

	recent = raw[-min(90, len(raw)):]
	previous = raw[-min(180, len(raw)):-min(90, len(raw))] if len(raw) > 90 else []
	recent_mean = statistics.mean(recent) if recent else 0.0
	previous_mean = statistics.mean(previous) if previous else 0.0
	trend_ratio = (
		recent_mean / previous_mean
		if previous_mean > 0
		else (2.0 if recent_mean > 0 else 1.0)
	)
	trend = "rising" if trend_ratio > 1.25 else ("falling" if trend_ratio < 0.8 else "stable")
	demand_days = sum(1 for qty in raw if qty > 0)
	non_zero_frequency = float(demand_days) / history_days if history_days else 0.0
	coefficient_of_variation = daily_std / weighted_mean if weighted_mean > 0 else 0.0

	if not demand_days:
		pattern = "no_history"
	elif history_days < 120:
		pattern = "new"
	elif non_zero_frequency < 0.08:
		pattern = "intermittent"
	elif coefficient_of_variation > 1.5:
		pattern = "variable"
	else:
		pattern = "stable"

	if history_days >= 270 and demand_days >= 12:
		confidence = "high"
	elif history_days >= 120 and demand_days >= 4:
		confidence = "medium"
	else:
		confidence = "low"

	return {
		"history_days": history_days,
		"demand_days": demand_days,
		"raw_total": sum(raw),
		"raw_daily_mean": raw_mean,
		"forecast_daily": weighted_mean,
		"daily_std": daily_std,
		"recent_90_day_mean": recent_mean,
		"previous_90_day_mean": previous_mean,
		"trend_ratio": trend_ratio,
		"trend": trend,
		"pattern": pattern,
		"non_zero_frequency": non_zero_frequency,
		"coefficient_of_variation": coefficient_of_variation,
		"outlier_cap": outlier_cap,
		"capped_days": capped_days,
		"confidence": confidence,
	}


def winsorize_demand(values):
	non_zero = [flt(value) for value in values if flt(value) > 0]
	if len(non_zero) < MIN_OUTLIER_OBSERVATIONS:
		return list(values), None, 0
	q1 = percentile(non_zero, 25)
	q3 = percentile(non_zero, 75)
	iqr = q3 - q1
	if iqr <= 0:
		if q3 <= 0 or not any(value > q3 for value in non_zero):
			return list(values), None, 0
		cap = q3
		adjusted = [min(flt(value), cap) if flt(value) > 0 else 0.0 for value in values]
		return adjusted, cap, sum(1 for value in values if flt(value) > cap)
	cap = q3 + 1.5 * iqr
	adjusted = [min(flt(value), cap) if flt(value) > 0 else 0.0 for value in values]
	return adjusted, cap, sum(1 for value in values if flt(value) > cap)


def build_lead_profile(
	observations, fallback_days, source_type, fallback_source="Item lead time"
):
	fallback_days = max(flt(fallback_days), 1.0)
	fallback_std = max(1.0, fallback_days * LEAD_TIME_STD_RATIO)
	if not observations:
		return {
			"average_days": fallback_days,
			"std_days": fallback_std,
			"sample_count": 0,
			"source": fallback_source,
			"confidence": "low",
			"source_type": source_type,
		}

	values = [flt(observation.get("days")) for observation in observations]
	weights = [flt(observation.get("weight")) or 1.0 for observation in observations]
	filtered_values, filtered_weights = iqr_filter(values, weights)
	average_days = weighted_average(filtered_values, filtered_weights)
	std_days = math.sqrt(
		weighted_population_variance(filtered_values, filtered_weights, average_days)
	)
	sample_count = len(filtered_values)
	if sample_count < 3:
		std_days = max(std_days, fallback_std)
	confidence = "high" if sample_count >= 8 else ("medium" if sample_count >= 3 else "low")
	sources = sorted(set(observation.get("source") for observation in observations if observation.get("source")))
	return {
		"average_days": max(average_days, 1.0),
		"std_days": max(std_days, 0.0),
		"sample_count": sample_count,
		"source": " / ".join(sources) if sources else "Observed history",
		"confidence": confidence,
		"source_type": source_type,
	}


def calculate_inventory_policy(demand_profile, lead_profile, z_score, review_period_days):
	daily_mean = max(flt(demand_profile.get("forecast_daily")), 0.0)
	daily_std = max(flt(demand_profile.get("daily_std")), 0.0)
	lead_mean = max(flt(lead_profile.get("average_days")), 0.0)
	lead_std = max(flt(lead_profile.get("std_days")), 0.0)
	variance = lead_mean * (daily_std ** 2) + (daily_mean ** 2) * (lead_std ** 2)
	safety_stock = math.ceil(max(flt(z_score), 0.0) * math.sqrt(max(variance, 0.0)))
	lead_time_demand = daily_mean * lead_mean
	reorder_level = math.ceil(lead_time_demand + safety_stock)
	order_up_to_level = math.ceil(
		daily_mean * (lead_mean + max(cint(review_period_days), 0)) + safety_stock
	)
	return {
		"daily_mean": daily_mean,
		"daily_std": daily_std,
		"lead_time_demand": lead_time_demand,
		"safety_stock": safety_stock,
		"reorder_level": reorder_level,
		"order_up_to_level": order_up_to_level,
		"variance_during_lead_time": variance,
		"z_score": flt(z_score),
	}


def project_inventory(opening_qty, safety_stock, forecast_daily, start_date, horizon_days, events):
	"""
	Project physical stock by day.

	Firm SO/WO demand is part of the historical consumption signal, so it replaces
	the same amount of baseline demand over the horizon instead of being added twice.
	Soft supply is shown as a scenario but never protects the firm projection.
	"""
	start_date = getdate(start_date)
	horizon_days = max(cint(horizon_days), 1)
	end_date = start_date + timedelta(days=horizon_days - 1)
	firm_supply = defaultdict(float)
	soft_supply = defaultdict(float)
	firm_demand = defaultdict(float)
	for event in events or []:
		event_date = getdate(event.get("date"))
		if event_date < start_date or event_date > end_date:
			continue
		qty = max(flt(event.get("qty")), 0.0)
		if event.get("direction") == "supply":
			if event.get("confidence") == "soft":
				soft_supply[event_date] += qty
			else:
				firm_supply[event_date] += qty
		elif event.get("direction") == "demand":
			firm_demand[event_date] += qty

	total_baseline = max(flt(forecast_daily), 0.0) * horizon_days
	total_firm_demand = sum(firm_demand.values())
	residual_daily = max(total_baseline - total_firm_demand, 0.0) / horizon_days
	balance = flt(opening_qty)
	soft_balance = flt(opening_qty)
	minimum = balance
	shortage_date = None
	safety_breach_date = None
	daily_projection = []
	for offset in range(horizon_days):
		current_date = start_date + timedelta(days=offset)
		opening = balance
		supply = firm_supply[current_date]
		planned_supply = soft_supply[current_date]
		known_demand = firm_demand[current_date]
		expected_demand = known_demand + residual_daily
		balance = opening + supply - expected_demand
		soft_balance = soft_balance + supply + planned_supply - expected_demand
		minimum = min(minimum, balance)
		if safety_breach_date is None and balance < flt(safety_stock):
			safety_breach_date = current_date
		if shortage_date is None and balance < 0:
			shortage_date = current_date
		daily_projection.append({
			"date": cstr(current_date),
			"opening_qty": opening,
			"firm_supply_qty": supply,
			"soft_supply_qty": planned_supply,
			"firm_demand_qty": known_demand,
			"forecast_residual_qty": residual_daily,
			"expected_demand_qty": expected_demand,
			"closing_qty": balance,
			"closing_with_soft_qty": soft_balance,
		})

	return {
		"opening_qty": flt(opening_qty),
		"firm_supply_qty": sum(firm_supply.values()),
		"soft_supply_qty": sum(soft_supply.values()),
		"firm_demand_qty": total_firm_demand,
		"forecast_residual_qty": residual_daily * horizon_days,
		"minimum_projected_qty": minimum,
		"ending_projected_qty": balance,
		"ending_with_soft_qty": soft_balance,
		"safety_breach_date": cstr(safety_breach_date) if safety_breach_date else None,
		"shortage_date": cstr(shortage_date) if shortage_date else None,
		"shortage_qty": max(-minimum, 0.0),
		"daily_projection": daily_projection,
	}


def build_recommendation(
	projection,
	lead_time_days,
	review_period_days,
	safety_stock,
	min_order_qty,
	procurement_type,
	today,
):
	daily = projection.get("daily_projection") or []
	if not daily:
		return {
			"recommended_qty": 0,
			"recommended_order_date": None,
			"expedite": False,
			"procurement_type": procurement_type,
			"action": _("No action"),
		}

	today = getdate(today)
	arrival_offset = max(int(math.ceil(flt(lead_time_days))), 1)
	breach_date = projection.get("safety_breach_date")
	shortage_date = projection.get("shortage_date")
	risk_dates = [
		getdate(value) for value in (breach_date, shortage_date) if value
	]
	first_risk_date = min(risk_dates) if risk_dates else None
	recommended_order_date = (
		first_risk_date - timedelta(days=arrival_offset)
		if first_risk_date
		else None
	)
	expedite = bool(recommended_order_date and recommended_order_date <= today)
	if not first_risk_date:
		recommended_qty = 0
	else:
		feasible_order_date = max(recommended_order_date, today)
		arrival_date = feasible_order_date + timedelta(days=arrival_offset)
		arrival_index = min(
			max((arrival_date - today).days, 0),
			len(daily) - 1,
		)
		review_end = min(
			arrival_index + max(cint(review_period_days), 1),
			len(daily),
		)
		review_points = daily[arrival_index:review_end] or [daily[arrival_index]]
		min_after_arrival = min(
			flt(point.get("closing_qty")) for point in review_points
		)
		recommended_qty = max(flt(safety_stock) - min_after_arrival, 0.0)
		if recommended_qty > 0:
			recommended_qty = math.ceil(
				max(recommended_qty, flt(min_order_qty))
			)

	if not recommended_qty:
		action = _("No replenishment")
	elif expedite:
		action = _("Expedite {0}").format(procurement_type.lower())
	else:
		action = _("Create {0}").format(
			_("Purchase Order") if procurement_type == "Purchase" else _("Work Order")
		)

	return {
		"recommended_qty": recommended_qty,
		"recommended_order_date": cstr(recommended_order_date) if recommended_order_date else None,
		"expedite": expedite,
		"procurement_type": procurement_type,
		"action": action,
	}


def classify_risk(projection, recommendation, confidence, demand_profile):
	if projection.get("shortage_date"):
		return "critical"
	if (
		flt(recommendation.get("recommended_qty")) > 0
		and recommendation.get("expedite")
	):
		return "action"
	if (
		flt(recommendation.get("recommended_qty")) > 0
		or projection.get("safety_breach_date")
	):
		return "watch"
	if confidence == "low" and flt(demand_profile.get("forecast_daily")) > 0:
		return "watch"
	return "healthy"


def remaining_work_order_demand(required_qty, consumed_qty):
	"""Global WO commitment: transferred-to-WIP material remains committed until consumed."""
	return max(flt(required_qty) - flt(consumed_qty), 0.0)


def build_summary(rows, total_candidates):
	return {
		"analysed_items": len(rows),
		"total_candidates": total_candidates,
		"critical_items": sum(1 for row in rows if row.get("risk") == "critical"),
		"action_items": sum(1 for row in rows if row.get("risk") == "action"),
		"watch_items": sum(1 for row in rows if row.get("risk") == "watch"),
		"healthy_items": sum(1 for row in rows if row.get("risk") == "healthy"),
		"high_confidence_items": sum(1 for row in rows if row.get("confidence") == "high"),
		"items_with_recommendation": sum(
			1 for row in rows if flt(row.get("recommended_qty")) > 0
		),
	}


def weekly_projection(daily_projection):
	weeks = []
	for start in range(0, len(daily_projection), 7):
		points = daily_projection[start:start + 7]
		if not points:
			continue
		weeks.append({
			"from_date": points[0]["date"],
			"to_date": points[-1]["date"],
			"opening_qty": points[0]["opening_qty"],
			"firm_supply_qty": sum(flt(point["firm_supply_qty"]) for point in points),
			"soft_supply_qty": sum(flt(point["soft_supply_qty"]) for point in points),
			"firm_demand_qty": sum(flt(point["firm_demand_qty"]) for point in points),
			"forecast_residual_qty": sum(
				flt(point["forecast_residual_qty"]) for point in points
			),
			"minimum_qty": min(flt(point["closing_qty"]) for point in points),
			"closing_qty": points[-1]["closing_qty"],
			"closing_with_soft_qty": points[-1]["closing_with_soft_qty"],
		})
	return weeks


def _weekly_global_risk_curve(values, start_date):
	result = []
	for start in range(0, len(values), 7):
		bucket = values[start:start + 7]
		if not bucket:
			continue
		result.append({
			"from_date": cstr(start_date + timedelta(days=start)),
			"to_date": cstr(start_date + timedelta(days=start + len(bucket) - 1)),
			"maximum_shortage_items": max(
				point["shortage_items"] for point in bucket
			),
			"maximum_safety_breach_items": max(
				point["safety_breach_items"] for point in bucket
			),
			"closing_shortage_items": bucket[-1]["shortage_items"],
			"closing_safety_breach_items": bucket[-1]["safety_breach_items"],
		})
	return result


def get_methodology():
	return {
		"physical_history": _(
			"Demand uses negative Stock Ledger Entries from customer deliveries, "
			"manufacturing consumption, material issues and repacks. Transfers, "
			"reconciliations, returns and subcontract dispatches are excluded."
		),
		"lead_time": _(
			"Purchase lead time is PO transaction date to submitted Purchase Receipt "
			"posting date. Manufacturing lead time is the best Planning/Work Order "
			"start evidence to the submitted Manufacture Stock Entry."
		),
		"safety_stock": _(
			"SS = Z × √(LTmean × Demandσ² + Demandmean² × LTσ²). "
			"Reorder level = expected lead-time demand + safety stock."
		),
		"future_demand": _(
			"Firm demand contains outstanding Sales Orders and all unconsumed Work "
			"Order material, including material already transferred to WIP."
		),
		"future_supply": _(
			"Firm supply contains outstanding Purchase Orders and Work Order output. "
			"Material Requests and unlinked Plannings are soft supply and never hide "
			"a shortage in the firm projection."
		),
		"forecast_netting": _(
			"Firm future demand replaces the same amount of the statistical baseline "
			"over the horizon, so known orders are not counted twice."
		),
		"warehouse_scope": _(
			"Only enabled leaf warehouses for the selected company are used. Scrap "
			"warehouses and their descendants are excluded."
		),
		"write_policy": _(
			"This page is analytical and does not update Item masters or create orders."
		),
	}


def get_usable_warehouses(company):
	warehouses = frappe.get_all(
		"Warehouse",
		filters={"company": company, "disabled": 0},
		fields=[
			"name",
			"warehouse_name",
			"parent_warehouse",
			"company",
			"is_group",
			"lft",
		],
		limit_page_length=0,
	)
	warehouse_map = {warehouse.name: warehouse for warehouse in warehouses}

	def is_scrap(warehouse):
		current = warehouse
		visited = set()
		while current and current.name not in visited:
			visited.add(current.name)
			name = cstr(current.name).lower()
			label = cstr(current.warehouse_name).lower()
			if label == "scrap" or name == "scrap" or name.startswith("scrap - "):
				return True
			current = warehouse_map.get(current.parent_warehouse)
		return False

	return sorted(
		[
			warehouse
			for warehouse in warehouses
			if not cint(warehouse.is_group) and not is_scrap(warehouse)
		],
		key=lambda warehouse: (cint(warehouse.lft), cstr(warehouse.name).lower()),
	)


def get_item_group_scope(item_group):
	bounds = frappe.db.get_value(
		"Item Group", item_group, ["lft", "rgt"], as_dict=True
	)
	if not bounds:
		return [item_group]
	return [
		row.name
		for row in frappe.get_all(
			"Item Group",
			filters={
				"lft": [">=", bounds.lft],
				"rgt": ["<=", bounds.rgt],
			},
			fields=["name"],
			limit_page_length=0,
		)
	]


def _get_company(company):
	company = cstr(company).strip() or (
		frappe.defaults.get_user_default("Company")
		or frappe.db.get_single_value("Global Defaults", "default_company")
	)
	if not company or not frappe.db.exists("Company", company):
		frappe.throw(_("Please select a valid Company."))
	return company


def classify_stock_movement(row):
	purpose = cstr(row.get("purpose"))
	voucher_type = cstr(row.get("voucher_type"))
	qty = flt(row.get("actual_qty"))
	if voucher_type == "Stock Entry" and purpose in TRANSFER_PURPOSES:
		return "transfer"
	if qty < 0 and (
		voucher_type in ("Delivery Note", "Sales Invoice")
		or (voucher_type == "Stock Entry" and purpose in HISTORICAL_DEMAND_PURPOSES)
	):
		return "consumption"
	if qty > 0 and (
		voucher_type == "Purchase Receipt"
		or (
			voucher_type == "Stock Entry"
			and purpose in ("Manufacture", "Material Receipt", "Repack")
		)
	):
		return "supply"
	if voucher_type == "Stock Reconciliation":
		return "adjustment"
	return "other"


def serialize_event(event):
	result = dict(event)
	result["date"] = cstr(result.get("date"))
	return result


def serialize_lead_observation(observation):
	result = dict(observation)
	result["finish_date"] = cstr(result.get("finish_date"))
	return result


def combine_confidence(*values):
	values = [value for value in values if value in CONFIDENCE_ORDER]
	if not values:
		return "low"
	return min(values, key=lambda value: CONFIDENCE_ORDER[value])


def percentile(values, percentile_value):
	values = sorted(flt(value) for value in values)
	if not values:
		return 0.0
	if len(values) == 1:
		return values[0]
	position = (len(values) - 1) * flt(percentile_value) / 100.0
	lower = int(math.floor(position))
	upper = int(math.ceil(position))
	if lower == upper:
		return values[lower]
	fraction = position - lower
	return values[lower] + (values[upper] - values[lower]) * fraction


def iqr_filter(values, weights):
	if not values:
		return [], []
	q1 = percentile(values, 25)
	q3 = percentile(values, 75)
	iqr = q3 - q1
	if iqr <= 0:
		return list(values), list(weights)
	lower = q1 - 1.5 * iqr
	upper = q3 + 1.5 * iqr
	filtered = [
		(value, weight)
		for value, weight in zip(values, weights)
		if lower <= value <= upper
	]
	if not filtered:
		return list(values), list(weights)
	return [pair[0] for pair in filtered], [pair[1] for pair in filtered]


def weighted_average(values, weights):
	if not values:
		return 0.0
	total_weight = sum(flt(weight) for weight in weights)
	if total_weight <= 0:
		return statistics.mean(values)
	return sum(flt(value) * flt(weight) for value, weight in zip(values, weights)) / total_weight


def weighted_population_variance(values, weights, average):
	if not values:
		return 0.0
	total_weight = sum(flt(weight) for weight in weights)
	if total_weight <= 0:
		return statistics.pvariance(values) if len(values) > 1 else 0.0
	return sum(
		flt(weight) * ((flt(value) - flt(average)) ** 2)
		for value, weight in zip(values, weights)
	) / total_weight


def as_datetime(value):
	if not value:
		return None
	if isinstance(value, datetime):
		return value
	if isinstance(value, date):
		return datetime.combine(value, time.min)
	try:
		return get_datetime(value)
	except Exception:
		return None


def combine_datetime(date_value, time_value=None):
	date_part = as_datetime(date_value)
	if not date_part:
		return None
	if isinstance(time_value, timedelta):
		time_part = (datetime.min + time_value).time()
	elif isinstance(time_value, time):
		time_part = time_value
	elif time_value:
		try:
			time_part = get_datetime("1900-01-01 {0}".format(cstr(time_value))).time()
		except Exception:
			time_part = time.min
	else:
		time_part = time.min
	return datetime.combine(date_part.date(), time_part)


def sql_placeholders(values):
	return ", ".join(["%s"] * len(values))


def chunks(values, size):
	for index in range(0, len(values), size):
		yield values[index:index + size]
