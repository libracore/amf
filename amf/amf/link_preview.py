from __future__ import unicode_literals

from collections import OrderedDict

import frappe
from frappe.desk.link_preview import get_preview_data as frappe_get_preview_data
from frappe.utils import flt
from frappe.utils.data import escape_html, get_link_to_form


MAIN_STOCK_WAREHOUSE = "Main Stock - AMF21"
WORK_IN_PROGRESS_WAREHOUSE = "Work In Progress - AMF21"
QUALITY_CONTROL_WAREHOUSE = "Quality Control - AMF21"
LINK_PREVIEW_CACHE_TTL_SEC = 30
LINK_PREVIEW_CACHE_KEY = "amf:item_link_preview:v2:{0}"
WAREHOUSE_STAGE_FIELDS = OrderedDict(
    [
        ("main_qty", "Main"),
        ("wip_qty", "WIP"),
        ("qc_qty", "QC"),
    ]
)


@frappe.whitelist()
def get_preview_data(doctype, docname):
    if doctype != "Item":
        return frappe_get_preview_data(doctype, docname)

    return _get_cached_item_preview_data(docname)


def _get_cached_item_preview_data(docname):
    cache_key = LINK_PREVIEW_CACHE_KEY.format(docname)
    cached_preview_data = frappe.cache().get_value(cache_key, expires=True)
    if cached_preview_data is not None:
        return cached_preview_data

    preview_data = _get_item_preview_data(docname)
    if preview_data is not None:
        frappe.cache().set_value(
            cache_key,
            preview_data,
            expires_in_sec=LINK_PREVIEW_CACHE_TTL_SEC,
        )

    return preview_data


def _get_item_preview_data(docname):
    meta = frappe.get_meta("Item")
    if not meta.show_preview_popup:
        return

    title_field = meta.get_title_field()

    fields = ["name", "stock_uom", "last_purchase_rate", "default_bom"]
    if title_field:
        fields.append(title_field)
    if meta.has_field("reorder_level"):
        fields.append("reorder_level")

    item_rows = frappe.get_list(
        "Item",
        filters={"name": docname},
        fields=list(dict.fromkeys(fields)),
        limit=1,
    )
    if not item_rows:
        return

    item = item_rows[0]
    item_code = item.get("name")
    stock_uom = item.get("stock_uom")
    aggregates = _get_item_preview_aggregates(item_code)
    last_purchase_rate = flt(item.get("last_purchase_rate")) or flt(
        aggregates.get("fallback_last_purchase_rate")
    )
    reorder_level = flt(item.get("reorder_level")) or flt(
        aggregates.get("fallback_reorder_level")
    )
    preview_title = item.get(title_field) or item_code

    preview_data = OrderedDict(
        [
            ("preview_title", preview_title),
            ("name", preview_title),
            ("Stock by Warehouse", _format_stock_by_stage(aggregates, stock_uom)),
            ("Sales Orders", _format_sales_order_summary(aggregates, stock_uom)),
            ("Work Orders", _format_work_order_summary(aggregates, stock_uom)),
        ]
    )

    if item.get("default_bom"):
        preview_data["Default BOM"] = get_link_to_form(
            "BOM",
            item.get("default_bom"),
            escape_html(item.get("default_bom")),
        )

    preview_data["Last Purchase Rate"] = _format_number(
        last_purchase_rate,
        meta.get_field("last_purchase_rate"),
    )
    preview_data["Reorder Level"] = _format_quantity(reorder_level, stock_uom)

    return preview_data


def _get_item_preview_aggregates(item_code):
    aggregate_rows = frappe.db.sql(
        """
        SELECT
            IFNULL(stock.main_qty, 0) AS main_qty,
            IFNULL(stock.wip_qty, 0) AS wip_qty,
            IFNULL(stock.qc_qty, 0) AS qc_qty,
            IFNULL(sales_orders.order_count, 0) AS sales_order_count,
            IFNULL(sales_orders.pending_qty, 0) AS sales_order_pending_qty,
            IFNULL(work_orders.work_order_count, 0) AS work_order_count,
            IFNULL(work_orders.remaining_qty, 0) AS work_order_remaining_qty,
            IFNULL(reorder_level.warehouse_reorder_level, 0) AS fallback_reorder_level,
            IFNULL(last_purchase.rate, 0) AS fallback_last_purchase_rate
        FROM (SELECT %(item_code)s AS item_code) AS base
        LEFT JOIN (
            SELECT
                item_code,
                SUM(
                    CASE
                        WHEN warehouse = %(main_stock_warehouse)s
                        THEN actual_qty
                        ELSE 0
                    END
                ) AS main_qty,
                SUM(
                    CASE
                        WHEN warehouse = %(wip_warehouse)s
                        THEN actual_qty
                        ELSE 0
                    END
                ) AS wip_qty,
                SUM(
                    CASE
                        WHEN warehouse = %(qc_warehouse)s
                        THEN actual_qty
                        ELSE 0
                    END
                ) AS qc_qty
            FROM `tabBin`
            WHERE item_code = %(item_code)s
                AND warehouse IN (
                    %(main_stock_warehouse)s,
                    %(wip_warehouse)s,
                    %(qc_warehouse)s
                )
            GROUP BY item_code
        ) AS stock
            ON stock.item_code = base.item_code
        LEFT JOIN (
            SELECT
                soi.item_code,
                COUNT(DISTINCT so.name) AS order_count,
                SUM(
                    CASE
                        WHEN IFNULL(soi.qty, 0) > IFNULL(soi.delivered_qty, 0)
                        THEN soi.qty - IFNULL(soi.delivered_qty, 0)
                        ELSE 0
                    END
                ) AS pending_qty
            FROM `tabSales Order Item` AS soi
            INNER JOIN `tabSales Order` AS so
                ON so.name = soi.parent
            WHERE soi.item_code = %(item_code)s
                AND so.docstatus = 1
                AND so.status NOT IN ('Closed', 'Completed', 'Cancelled')
                AND IFNULL(soi.qty, 0) > IFNULL(soi.delivered_qty, 0)
            GROUP BY soi.item_code
        ) AS sales_orders
            ON sales_orders.item_code = base.item_code
        LEFT JOIN (
            SELECT
                production_item,
                COUNT(name) AS work_order_count,
                SUM(
                    CASE
                        WHEN IFNULL(qty, 0) > IFNULL(produced_qty, 0)
                        THEN qty - IFNULL(produced_qty, 0)
                        ELSE 0
                    END
                ) AS remaining_qty
            FROM `tabWork Order`
            WHERE production_item = %(item_code)s
                AND docstatus < 2
                AND status NOT IN ('Completed', 'Cancelled')
            GROUP BY production_item
        ) AS work_orders
            ON work_orders.production_item = base.item_code
        LEFT JOIN (
            SELECT
                parent AS item_code,
                warehouse_reorder_level
            FROM `tabItem Reorder`
            WHERE parent = %(item_code)s
                AND warehouse = %(main_stock_warehouse)s
            ORDER BY idx ASC
            LIMIT 1
        ) AS reorder_level
            ON reorder_level.item_code = base.item_code
        LEFT JOIN (
            SELECT
                pii.item_code,
                pii.rate
            FROM `tabPurchase Invoice Item` AS pii
            INNER JOIN `tabPurchase Invoice` AS pi
                ON pi.name = pii.parent
            WHERE pii.item_code = %(item_code)s
                AND pi.docstatus = 1
            ORDER BY
                pi.posting_date DESC,
                pi.posting_time DESC,
                pii.creation DESC
            LIMIT 1
        ) AS last_purchase
            ON last_purchase.item_code = base.item_code
        """,
        {
            "item_code": item_code,
            "main_stock_warehouse": MAIN_STOCK_WAREHOUSE,
            "wip_warehouse": WORK_IN_PROGRESS_WAREHOUSE,
            "qc_warehouse": QUALITY_CONTROL_WAREHOUSE,
        },
        as_dict=True,
    )
    return aggregate_rows[0] if aggregate_rows else {}


def _format_stock_by_stage(aggregates, uom=None):
    parts = [
        "{0}: {1}".format(
            label,
            _format_number(aggregates.get(fieldname), {"fieldtype": "Float"}),
        )
        for fieldname, label in WAREHOUSE_STAGE_FIELDS.items()
    ]
    stock_summary = " // ".join(parts)
    if uom:
        return "{0} {1}".format(stock_summary, uom)
    return stock_summary


def _format_sales_order_summary(aggregates, uom=None):
    order_count = int(aggregates.get("sales_order_count") or 0)
    pending_qty = flt(aggregates.get("sales_order_pending_qty") or 0)

    if not order_count:
        return "No open sales orders"

    return "{0} open >> {1} pending".format(
        order_count,
        _format_quantity(pending_qty, uom),
    )


def _format_work_order_summary(aggregates, uom=None):
    work_order_count = int(aggregates.get("work_order_count") or 0)
    remaining_qty = flt(aggregates.get("work_order_remaining_qty") or 0)

    if not work_order_count:
        return "No open work orders"

    return "{0} open >> {1} remaining".format(
        work_order_count,
        _format_quantity(remaining_qty, uom),
    )


def _format_quantity(value, uom=None):
    formatted_value = _format_number(value, {"fieldtype": "Float"})
    if uom:
        return "{0} {1}".format(formatted_value, uom)
    return formatted_value


def _format_number(value, df=None):
    return frappe.format(flt(value), df or {"fieldtype": "Float"})
