# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.utils import cstr

from amf.amf.utils.inventory_planning_engine import (
	InventoryPlanningEngine,
	get_methodology,
)


ALLOWED_ROLES = {
	"Stock User",
	"Stock Manager",
	"Purchase User",
	"Purchase Manager",
	"Manufacturing User",
	"Manufacturing Manager",
	"System Manager",
}


@frappe.whitelist()
def get_dashboard(
	company=None,
	item_group=None,
	search=None,
	procurement_type=None,
	risk=None,
	service_level=95,
	lookback_days=365,
	horizon_days=90,
	review_period_days=30,
	page_start=0,
	page_length=100,
):
	"""Return the read-only inventory policy and time-phased shortage dashboard."""
	_assert_access()
	engine = InventoryPlanningEngine(
		company=company,
		item_group=item_group,
		search=search,
		procurement_type=procurement_type,
		risk=risk,
		service_level=service_level,
		lookback_days=lookback_days,
		horizon_days=horizon_days,
		review_period_days=review_period_days,
		page_start=page_start,
		page_length=page_length,
	)
	return engine.build()


@frappe.whitelist()
def get_item_detail(
	item_code=None,
	company=None,
	service_level=95,
	lookback_days=365,
	horizon_days=90,
	review_period_days=30,
):
	"""Return the auditable I/O, lead-time and projection detail for one Item."""
	_assert_access()
	item_code = cstr(item_code).strip()
	if not item_code:
		frappe.throw(_("Please select an Item."))
	item = frappe.get_doc("Item", item_code)
	frappe.has_permission("Item", ptype="read", doc=item, throw=True)

	engine = InventoryPlanningEngine(
		company=company,
		item_code=item_code,
		service_level=service_level,
		lookback_days=lookback_days,
		horizon_days=horizon_days,
		review_period_days=review_period_days,
		page_length=1,
	)
	engine.build(include_detail=True)
	detail = engine.get_item_detail(item_code)
	if not detail:
		frappe.throw(_("No inventory-planning data was found for Item {0}.").format(item_code))
	detail["methodology"] = get_methodology()
	return detail


def _assert_access():
	if frappe.session.user == "Guest":
		frappe.throw(_("Please sign in to use Inventory Planning."), frappe.PermissionError)
	if frappe.session.user == "Administrator":
		return
	if not ALLOWED_ROLES.intersection(set(frappe.get_roles())):
		frappe.throw(_("You do not have access to Inventory Planning."), frappe.PermissionError)
