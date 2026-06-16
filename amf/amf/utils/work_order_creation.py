from __future__ import unicode_literals
import math
from collections import defaultdict

from amf.amf.utils.stock_summary import get_stock
from amf.amf.utils.utilities import *
import frappe
import json
import frappe.utils
from frappe import _
from erpnext.stock.doctype.stock_entry.stock_entry import get_additional_costs
from frappe.utils.data import add_days, cint, date_diff, flt, getdate, get_datetime, nowdate


@frappe.whitelist()
def make_work_orders(items, sales_order, company, project=None):
    '''Make Work Orders against the given Sales Order for the given `items`'''
    items = json.loads(items).get('items')
    out = []

    for i in items:
        if not i.get("bom"):
            frappe.throw(_("Please select BOM against item {0}").format(i.get("item_code")))
        if not i.get("pending_qty"):
            frappe.throw(_("Please select Qty against item {0}").format(i.get("item_code")))
        if not i.get("simple_description"):
            i["simple_description"] = ''

        sales_order_item = frappe.get_doc('Sales Order Item', i['sales_order_item'])
        if not sales_order_item.delivery_date:
            frappe.throw(_("Please set delivery date against item {0} in the Sales Order {1}").format(i['item_code'], sales_order))
        delivery_date = sales_order_item.delivery_date

        # Check if the quantity in items is greater than the sales order quantity
        if i['pending_qty'] > sales_order_item.qty:
            remaining_qty = i['pending_qty'] - sales_order_item.qty

            # Create a work order with sales order quantity
            work_order = frappe.get_doc(dict(
                doctype='Work Order',
                production_item=i['item_code'],
                bom_no=i.get('bom'),
                qty=sales_order_item.qty,
                company=company,
                sales_order=sales_order,
                sales_order_item=i['sales_order_item'],
                project=project,
                fg_warehouse=i['warehouse'],
                description=i['description'],
                destination=i['destination'],
                simple_description=i['simple_description'],
                p_e_d=delivery_date
            )).insert()
            work_order.set_work_order_operations()
            work_order.save()
            work_order.submit()
            out.append(work_order)

            # Create another work order with the remaining quantity
            work_order_remaining = frappe.get_doc(dict(
                doctype='Work Order',
                production_item=i['item_code'],
                bom_no=i.get('bom'),
                qty=remaining_qty,
                company=company,
                sales_order_item=i['sales_order_item'],
                project=project,
                fg_warehouse=i['warehouse'],
                description=i['description'],
                destination=i['destination'],
                simple_description=i['simple_description'],
                p_e_d=delivery_date
            )).insert()
            work_order_remaining.set_work_order_operations()
            work_order_remaining.save()
            work_order_remaining.submit()
            out.append(work_order_remaining)

        else:
            # If pending_qty is less than or equal to sales order quantity, create a single work order
            work_order = frappe.get_doc(dict(
                doctype='Work Order',
                production_item=i['item_code'],
                bom_no=i.get('bom'),
                qty=i['pending_qty'],
                company=company,
                sales_order=sales_order,
                sales_order_item=i['sales_order_item'],
                project=project,
                fg_warehouse=i['warehouse'],
                description=i['description'],
                destination=i['destination'],
                simple_description=i['simple_description'],
                p_e_d=delivery_date
            )).insert()
            work_order.set_work_order_operations()
            work_order.save()
            work_order.submit()
            out.append(work_order)

    return [p.name for p in out]

@frappe.whitelist()
def check_and_create_work_orders(work_order, method=None):
    work_order_doc = frappe.get_doc('Work Order', work_order.name)
    print(work_order_doc)
    if work_order_doc.sales_order:
        sales_order = work_order_doc.sales_order
    else:
        sales_order = None
    required_qty_dict = {rqd_item.item_code: rqd_item.required_qty for rqd_item in work_order_doc.required_items}
    bom_items = frappe.get_all('BOM Item', filters={'parent': work_order_doc.bom_no}, fields=['item_code', 'qty'])
    missing_items = []

    for item in bom_items:
        print(item)
        stock_qty = get_stock(item['item_code'])
        total_qty = sum(stock['actual_qty'] for stock in stock_qty)
        print(stock_qty, total_qty)
         # Use the required_qty from the required_items
        required_qty = required_qty_dict.get(item['item_code'], 0)
        if total_qty < required_qty*item['qty']:
            qty_rqd = required_qty*item['qty']-total_qty
            if frappe.db.exists('BOM', {'item': item['item_code'], 'is_active': 1, 'is_default': 1}):
                missing_items.append({'item_code': item['item_code'], 'qty': qty_rqd})
    
    print("missing items:", missing_items)
    if missing_items:
        create_work_orders_for_missing_items(missing_items, sales_order)

    return {'missing_items': missing_items}

@frappe.whitelist()
def create_work_orders_for_missing_items(missing_items, sales_order=None):
    work_orders = []
    for item in missing_items:
        item_code = item['item_code']
        qty = item['qty']
        
        bom = frappe.get_value('BOM', {'item': item_code, 'is_active': 1, 'is_default': 1}, 'name')
        
        if bom:
            wo = make_work_order(item_code, sales_order, qty, bom)
            wo.submit()
            work_orders.append(wo.name)
            commit_database()
    print(work_orders)
    return work_orders

def make_work_order(item_code, sales_order=None, qty=1, bom_no=None):
    '''Make a single Work Order for the given item'''
    if not bom_no:
        frappe.throw(_("Please select BOM for item {0}").format(item_code))
    if not qty:
        frappe.throw(_("Please select Qty for item {0}").format(item_code))

    work_order = frappe.get_doc(dict(
        doctype='Work Order',
        production_item=item_code,
        bom_no=bom_no,
        qty=qty,
        company='Advanced Microfluidics SA',
        sales_order=sales_order,
        fg_warehouse='Main Stock - AMF21',  # Replace with the appropriate warehouse
        simple_description='Auto-generated Work Order from non-available stock'
    )).insert()
   
    work_order.set_work_order_operations()
    work_order.save()

    return work_order

def check_sub_assembly_items(work_order):
    # List to hold all sub-assembly items
    sub_assembly_items = []

    def get_sub_assemblies(bom_no):
        # Fetch all items in the BOM
        bom_items = frappe.get_all('BOM Item', filters={'parent': bom_no}, fields=['item_code'])

        for item in bom_items:
            # Fetch the item_type from the Item doctype
            item_type = frappe.db.get_value('Item', item['item_code'], 'item_type')
            
            # Check if the item type is 'Sub-Assembly'
            if item_type == 'Sub-Assembly' or item_type == 'Actuator':
                # Append to the list
                sub_assembly_items.append(item['item_code'])
                
                # Fetch the default BOM for this item
                default_bom = frappe.db.get_value('BOM', {'item': item['item_code'], 'is_default': 1, 'is_active': 1}, 'name')
                
                # If there is a default BOM, recurse into it
                if default_bom:
                    get_sub_assemblies(default_bom)

    # Get the BOM linked to the work order
    work_order_doc = frappe.get_doc('Work Order', work_order)
    bom_no = work_order_doc.bom_no
    
    # Start the recursion from the main BOM
    get_sub_assemblies(bom_no)

    # Optional: Return the list of sub-assembly items
    return sub_assembly_items

@frappe.whitelist()
def on_submit_work_order(doc_name, method=None):
    sub_assembly_items = check_sub_assembly_items(doc_name) # PUT doc.name when using hooks.py
    print("Sub-Assembly:", sub_assembly_items)
    return sub_assembly_items

@frappe.whitelist()
def create_work_orders(items, qty, parent_work_order, customer=None):
    # Convert the items string to a list
    if isinstance(items, str):
        items = json.loads(items)
    work_order_links = []
    for item in items:
        work_order = frappe.get_doc(dict(
                doctype='Work Order',
                production_item=item,
                bom_no=frappe.db.get_value('BOM', {'item': item, 'is_default': 1, 'is_active': 1}, 'name'),
                qty=int(qty),
                parent_work_order=parent_work_order,
                custo_name = customer,
            )).insert()
        work_order.set_work_order_operations()
        work_order.save()
        work_order.submit()
        work_order_links.append(work_order.name)
    
    commit_database()
    return work_order_links

def should_generate_work_order_for_item(item_code):
    # Logic to determine if a Work Order should be generated for the item
    # This could involve checking stock levels, existing Work Orders, etc.
    return True  # For simplicity, always return True

def get_default_bom(item_code):
    # Logic to fetch the default BOM for the given item
    bom = frappe.db.get_value('BOM', {'item': item_code, 'is_default': 1}, 'name')
    if not bom:
        frappe.throw(f"No default BOM found for item {item_code}")
    return bom

@frappe.whitelist()
def make_stock_entry(work_order_id, purpose, qty=None):
    work_order = frappe.get_doc("Work Order", work_order_id)
    if not frappe.db.get_value("Warehouse", work_order.wip_warehouse, "is_group") \
            and not work_order.skip_transfer:
        wip_warehouse = work_order.wip_warehouse
    else:
        wip_warehouse = None

    stock_entry = frappe.new_doc("Stock Entry")
    stock_entry.purpose = purpose
    stock_entry.work_order = work_order_id
    stock_entry.company = work_order.company
    stock_entry.from_bom = 1
    stock_entry.bom_no = work_order.bom_no
    stock_entry.use_multi_level_bom = work_order.use_multi_level_bom
    stock_entry.fg_completed_qty = qty or (flt(work_order.qty) - flt(work_order.produced_qty))

    if purpose == "Material Transfer for Manufacture":
        stock_entry.to_warehouse = wip_warehouse
        stock_entry.project = work_order.project
    else:
        stock_entry.from_warehouse = wip_warehouse
        stock_entry.to_warehouse = work_order.fg_warehouse
        stock_entry.project = work_order.project
        if purpose == "Manufacture":
            additional_costs = get_additional_costs(work_order, fg_qty=stock_entry.fg_completed_qty)
            stock_entry.set("additional_costs", additional_costs)

    stock_entry.set_stock_entry_type()
    stock_entry.get_items()

    # Save the Stock Entry
    stock_entry.insert()
    stock_entry.submit()

    # Commit the transaction to ensure the Stock Entry is saved
    frappe.db.commit()

    return stock_entry.as_dict()

#####################################
### AUTOMATIC WORK ORDER CREATION ###
#####################################
MACHINING_ITEM_PREFIXES = ("10", "20")
MACHINING_ITEM_CODE_LENGTH = 6
MACHINING_STOCK_WAREHOUSES = ("Main Stock - AMF21", "Assemblies - AMF21")
MACHINING_WIP_WAREHOUSE = "Work In Progress - AMF21"
MACHINING_FG_WAREHOUSE = "Quality Control - AMF21"
MACHINING_LEAD_TIME_DAYS = 7
MACHINING_QTY_BUFFER_FACTOR = 1.2
AMF_DESK_BASE_URL = "https://amf.libracore.ch"

TEST_MODE = False


@frappe.whitelist()
def plan_machining_work_orders_from_sales_orders(
    company=None,
    from_delivery_date=None,
    to_delivery_date=None,
    dry_run=0,
    commit=1,
):
    """
    Create draft Work Orders for machined BOM components required by open,
    submitted Sales Orders.

    The method:
      1. Reads submitted Sales Order Items that still have an undelivered qty.
      2. Traverses their BOMs and stops at six-digit item codes starting with
         10 or 20, because those are the machining planning items.
      3. Groups the demand by item and shipping date.
      4. Allocates existing stock and open Work Orders before creating anything.
      5. Inserts one draft Work Order per item/date shortage with an expected
         date 7 days before the Sales Order shipping date.

    Work Orders are intentionally not submitted.
    """
    dry_run = cint(dry_run)
    commit = cint(commit)
    sources = _get_sales_order_bom_sources(
        company=company,
        from_delivery_date=from_delivery_date,
        to_delivery_date=to_delivery_date,
    )
    demand_map, skipped_sources = _build_machining_demand_from_sources(sources)
    demand_rows = _get_sorted_demand_rows(demand_map)
    item_codes = sorted({row["item_code"] for row in demand_rows})

    stock_by_item = _get_stock_balance_for_items(item_codes)
    open_work_orders_by_item = _get_open_work_orders_by_item(item_codes)
    bom_by_item = _get_default_boms_for_items(item_codes)

    created = []
    planned = []
    skipped = list(skipped_sources)
    available_by_item = defaultdict(float)
    work_order_supply_by_item = defaultdict(list)

    for item_code in item_codes:
        available_by_item[item_code] = flt(stock_by_item.get(item_code))
        work_order_supply_by_item[item_code] = list(open_work_orders_by_item.get(item_code) or [])

    for row in demand_rows:
        item_code = row["item_code"]
        required_qty = flt(row["qty"])
        expected_date = row["expected_date"]

        available_by_item[item_code] += _consume_due_work_order_supply(
            work_order_supply_by_item[item_code],
            expected_date,
        )

        shortage_qty = required_qty - available_by_item[item_code]
        if shortage_qty <= 0:
            available_by_item[item_code] -= required_qty
            row.update({
                "covered_qty": required_qty,
                "shortage_qty": 0,
            })
            planned.append(_serialize_planning_row(row, None))
            continue

        available_by_item[item_code] = 0
        row.update({
            "covered_qty": required_qty - shortage_qty,
            "shortage_qty": shortage_qty,
            "work_order_qty": _get_buffered_work_order_qty(item_code, shortage_qty),
            "priority": _get_priority_for_expected_date(expected_date),
        })

        bom_no = bom_by_item.get(item_code)
        if not bom_no:
            skipped.append({
                "item_code": item_code,
                "shipping_date": _date_to_string(row["shipping_date"]),
                "expected_date": _date_to_string(expected_date),
                "qty": shortage_qty,
                "reason": _("No active submitted default BOM found for machining item"),
            })
            planned.append(_serialize_planning_row(row, None))
            continue

        if dry_run:
            planned.append(_serialize_planning_row(row, None))
            continue

        try:
            work_order = _create_draft_machining_work_order(
                item_code=item_code,
                qty=row["work_order_qty"],
                bom_no=bom_no,
                company=row["company"],
                expected_date=expected_date,
                shipping_date=row["shipping_date"],
                sources=row["sources"],
            )
            created.append(_serialize_planning_row(row, work_order.name))
            planned.append(_serialize_planning_row(row, work_order.name))
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                _("Machining Sales Order planning failed for {0}").format(item_code),
            )
            skipped.append({
                "item_code": item_code,
                "shipping_date": _date_to_string(row["shipping_date"]),
                "expected_date": _date_to_string(expected_date),
                "qty": shortage_qty,
                "reason": frappe.get_traceback(),
            })

    if created and commit:
        frappe.db.commit()

    return {
        "dry_run": dry_run,
        "source_count": len(sources),
        "demand_count": len(demand_rows),
        "created_count": len(created),
        "skipped_count": len(skipped),
        "created": created,
        "planned": planned,
        "skipped": skipped,
    }


def _get_sales_order_bom_sources(company=None, from_delivery_date=None, to_delivery_date=None):
    conditions = [
        "so.docstatus = 1",
        "so.status NOT IN ('Closed', 'On Hold', 'Cancelled', 'Completed')",
        "IFNULL(soi.qty, 0) > IFNULL(soi.delivered_qty, 0)",
        "(so._user_tags NOT LIKE '%%template%%' OR so._user_tags IS NULL)",
    ]
    params = {}

    if company:
        conditions.append("so.company = %(company)s")
        params["company"] = company
    if from_delivery_date:
        conditions.append("COALESCE(soi.delivery_date, so.delivery_date) >= %(from_delivery_date)s")
        params["from_delivery_date"] = getdate(from_delivery_date)
    if to_delivery_date:
        conditions.append("COALESCE(soi.delivery_date, so.delivery_date) <= %(to_delivery_date)s")
        params["to_delivery_date"] = getdate(to_delivery_date)

    where_clause = " AND ".join(conditions)
    sales_order_items = frappe.db.sql(
        """
        SELECT
            so.name AS sales_order,
            so.company AS company,
            so.customer AS customer,
            so.customer_name AS customer_name,
            soi.name AS sales_order_item,
            soi.item_code AS source_item_code,
            soi.item_name AS source_item_name,
            GREATEST(
                (IFNULL(soi.qty, 0) - IFNULL(soi.delivered_qty, 0))
                * IFNULL(soi.conversion_factor, 1),
                0
            ) AS source_qty,
            COALESCE(soi.delivery_date, so.delivery_date) AS shipping_date,
            0 AS is_packed_item
        FROM `tabSales Order Item` soi
        INNER JOIN `tabSales Order` so ON so.name = soi.parent
        WHERE {where_clause}
        """.format(where_clause=where_clause),
        params,
        as_dict=True,
    )

    packed_items = frappe.db.sql(
        """
        SELECT
            so.name AS sales_order,
            so.company AS company,
            so.customer AS customer,
            so.customer_name AS customer_name,
            soi.name AS sales_order_item,
            pi.item_code AS source_item_code,
            pi.item_name AS source_item_name,
            GREATEST(
                (IFNULL(soi.qty, 0) - IFNULL(soi.delivered_qty, 0))
                * (IFNULL(pi.qty, 0) / NULLIF(IFNULL(soi.qty, 0), 0)),
                0
            ) AS source_qty,
            COALESCE(soi.delivery_date, so.delivery_date) AS shipping_date,
            1 AS is_packed_item
        FROM `tabPacked Item` pi
        INNER JOIN `tabSales Order Item` soi ON soi.name = pi.parent_detail_docname
        INNER JOIN `tabSales Order` so ON so.name = soi.parent
        WHERE {where_clause}
        """.format(where_clause=where_clause),
        params,
        as_dict=True,
    )

    return [
        source for source in list(sales_order_items) + list(packed_items)
        if flt(source.get("source_qty")) > 0 and source.get("shipping_date")
    ]


def _build_machining_demand_from_sources(sources):
    demand_map = {}
    skipped = []
    bom_cache = {}

    for source in sources:
        source_item_code = source.get("source_item_code")
        source_qty = flt(source.get("source_qty"))
        shipping_date = getdate(source.get("shipping_date"))
        if _is_machining_item_code(source_item_code):
            _add_machining_demand(demand_map, source_item_code, source_qty, source)
            continue

        bom_no = _get_default_active_bom(source_item_code, bom_cache)
        if not bom_no:
            skipped.append({
                "sales_order": source.get("sales_order"),
                "sales_order_item": source.get("sales_order_item"),
                "source_item_code": source_item_code,
                "shipping_date": _date_to_string(shipping_date),
                "reason": _("No active submitted default BOM found for Sales Order item"),
            })
            continue

        components = _collect_machining_components_from_bom(
            bom_no,
            source_qty,
            bom_cache=bom_cache,
        )
        if not components:
            skipped.append({
                "sales_order": source.get("sales_order"),
                "sales_order_item": source.get("sales_order_item"),
                "source_item_code": source_item_code,
                "shipping_date": _date_to_string(shipping_date),
                "reason": _("No 10/20 six-digit machining item found in BOM"),
            })
            continue

        for item_code, qty in components.items():
            component_source = dict(source)
            component_source["component_qty"] = qty
            component_source["source_bom"] = bom_no
            _add_machining_demand(demand_map, item_code, qty, component_source)

    return demand_map, skipped


def _collect_machining_components_from_bom(bom_no, qty, bom_cache=None, visited=None):
    bom_cache = bom_cache if bom_cache is not None else {}
    visited = set(visited or [])
    components = defaultdict(float)

    if not bom_no or bom_no in visited:
        return components

    visited.add(bom_no)
    bom_doc = frappe.get_cached_doc("BOM", bom_no)
    bom_qty = flt(bom_doc.quantity) or 1

    for row in bom_doc.items:
        item_code = row.item_code
        row_qty = flt(row.stock_qty or row.qty) / bom_qty * flt(qty)
        if row_qty <= 0:
            continue

        if _is_machining_item_code(item_code):
            components[item_code] += row_qty
            continue

        child_bom = _get_valid_child_bom(row, bom_cache)
        if not child_bom:
            continue

        child_components = _collect_machining_components_from_bom(
            child_bom,
            row_qty,
            bom_cache=bom_cache,
            visited=visited,
        )
        for child_item_code, child_qty in child_components.items():
            components[child_item_code] += child_qty

    visited.remove(bom_no)
    return components


def _add_machining_demand(demand_map, item_code, qty, source):
    shipping_date = getdate(source.get("shipping_date"))
    key = (item_code, shipping_date, source.get("company"))
    if key not in demand_map:
        demand_map[key] = {
            "item_code": item_code,
            "shipping_date": shipping_date,
            "expected_date": getdate(add_days(shipping_date, -MACHINING_LEAD_TIME_DAYS)),
            "company": source.get("company"),
            "qty": 0,
            "sources": [],
        }

    demand_map[key]["qty"] += flt(qty)
    demand_map[key]["sources"].append({
        "sales_order": source.get("sales_order"),
        "sales_order_item": source.get("sales_order_item"),
        "customer": source.get("customer"),
        "customer_name": source.get("customer_name"),
        "source_item_code": source.get("source_item_code"),
        "source_item_name": source.get("source_item_name"),
        "source_qty": flt(source.get("source_qty")),
        "component_qty": flt(qty),
        "shipping_date": _date_to_string(shipping_date),
        "is_packed_item": cint(source.get("is_packed_item")),
        "source_bom": source.get("source_bom"),
    })


def _get_sorted_demand_rows(demand_map):
    return sorted(
        demand_map.values(),
        key=lambda row: (row["item_code"], row["expected_date"], row["shipping_date"]),
    )


def _get_stock_balance_for_items(item_codes, warehouses=None):
    if not item_codes:
        return {}

    warehouses = tuple(warehouses or MACHINING_STOCK_WAREHOUSES)
    rows = frappe.db.sql(
        """
        SELECT item_code, SUM(actual_qty) AS actual_qty
        FROM `tabBin`
        WHERE item_code IN %(item_codes)s
            AND warehouse IN %(warehouses)s
        GROUP BY item_code
        """,
        {
            "item_codes": tuple(item_codes),
            "warehouses": warehouses,
        },
        as_dict=True,
    )
    return {row.item_code: flt(row.actual_qty) for row in rows}


def _get_open_work_orders_by_item(item_codes):
    if not item_codes:
        return {}

    rows = frappe.db.sql(
        """
        SELECT
            name,
            production_item,
            GREATEST(IFNULL(qty, 0) - IFNULL(produced_qty, 0), 0) AS remaining_qty,
            expected_delivery_date_ AS custom_expected_delivery_date,
            expected_delivery_date,
            DATE(planned_start_date) AS planned_start_date
        FROM `tabWork Order`
        WHERE production_item IN %(item_codes)s
            AND docstatus < 2
            AND IFNULL(status, '') NOT IN ('Completed', 'Cancelled', 'Stopped')
            AND GREATEST(IFNULL(qty, 0) - IFNULL(produced_qty, 0), 0) > 0
        ORDER BY
            production_item,
            COALESCE(expected_delivery_date_, expected_delivery_date, DATE(planned_start_date), '1900-01-01'),
            creation
        """,
        {"item_codes": tuple(item_codes)},
        as_dict=True,
    )

    grouped = defaultdict(list)
    for row in rows:
        due_date = row.custom_expected_delivery_date or row.expected_delivery_date or row.planned_start_date
        grouped[row.production_item].append({
            "work_order": row.name,
            "remaining_qty": flt(row.remaining_qty),
            "due_date": getdate(due_date) if due_date else None,
        })

    return grouped


def _consume_due_work_order_supply(work_orders, expected_date):
    supply_qty = 0
    remaining = []

    for work_order in work_orders:
        due_date = work_order.get("due_date")
        if due_date and due_date > expected_date:
            remaining.append(work_order)
            continue

        supply_qty += flt(work_order.get("remaining_qty"))

    work_orders[:] = remaining
    return supply_qty


def _get_default_boms_for_items(item_codes):
    bom_cache = {}
    return {
        item_code: _get_default_active_bom(item_code, bom_cache)
        for item_code in item_codes
    }


def _get_default_active_bom(item_code, bom_cache=None):
    if not item_code:
        return None

    if bom_cache is not None and item_code in bom_cache:
        return bom_cache[item_code]

    bom_no = frappe.db.get_value(
        "BOM",
        {
            "item": item_code,
            "is_active": 1,
            "is_default": 1,
            "docstatus": 1,
        },
        "name",
        order_by="modified desc",
    )

    if bom_cache is not None:
        bom_cache[item_code] = bom_no
    return bom_no


def _get_valid_child_bom(row, bom_cache=None):
    if row.bom_no:
        bom_status = frappe.db.get_value(
            "BOM",
            row.bom_no,
            ["is_active", "docstatus"],
            as_dict=True,
        )
        if bom_status and cint(bom_status.is_active) and cint(bom_status.docstatus) == 1:
            return row.bom_no

    return _get_default_active_bom(row.item_code, bom_cache)


def _create_draft_machining_work_order(
    item_code,
    qty,
    bom_no,
    company,
    expected_date,
    shipping_date,
    sources,
):
    work_order = frappe.new_doc("Work Order")
    work_order.company = company or frappe.defaults.get_user_default("Company") \
        or frappe.db.get_single_value("Global Defaults", "default_company")
    work_order.production_item = item_code
    work_order.bom_no = bom_no
    work_order.qty = _get_integer_work_order_qty(qty)
    work_order.expected_delivery_date = expected_date
    _set_if_field(work_order, "expected_delivery_date_", expected_date)
    work_order.planned_start_date = get_datetime("{0} 00:00:00".format(_date_to_string(expected_date)))
    work_order.wip_warehouse = MACHINING_WIP_WAREHOUSE
    work_order.fg_warehouse = MACHINING_FG_WAREHOUSE
    work_order.skip_transfer = 1
    work_order.set_work_order_operations()

    _set_if_field(work_order, "auto_gen", 1)
    _set_if_field(work_order, "priority", _get_priority_for_expected_date(expected_date))
    _set_if_field(work_order, "progress", "En Attente")
    _set_if_field(work_order, "machine", _get_machine_for_machining_item(item_code))
    _set_if_field(work_order, "assembly_specialist_start", "MBA")
    _set_if_field(work_order, "wip_step", 1)
    _set_if_field(work_order, "p_s_d", expected_date)
    _set_if_field(work_order, "p_e_d", expected_date)
    _set_if_field(work_order, "drawing", _get_default_drawing(item_code))
    _set_if_field(work_order, "custo_name", _get_customer_names_from_sources(sources))
    _set_if_field(
        work_order,
        "description",
        _get_machining_work_order_description(item_code, sources, shipping_date, expected_date),
    )
    _set_if_field(
        work_order,
        "simple_description",
        _get_machining_work_order_note(sources, shipping_date, expected_date),
    )

    work_order.insert(ignore_permissions=True)
    return work_order


def _get_buffered_work_order_qty(item_code, shortage_qty):
    buffered_qty = flt(shortage_qty) * MACHINING_QTY_BUFFER_FACTOR
    return _get_integer_work_order_qty(buffered_qty)


def _get_integer_work_order_qty(qty):
    qty = flt(qty)
    if qty <= 0:
        return 0
    return int(math.ceil(qty))


def _get_priority_for_expected_date(expected_date):
    days_until_expected = date_diff(getdate(expected_date), getdate(nowdate()))
    if days_until_expected <= 0:
        return 1
    if days_until_expected <= 7:
        return 2
    if days_until_expected <= 14:
        return 3
    if days_until_expected <= 30:
        return 4
    return 5


def _get_machine_for_machining_item(item_code):
    if item_code.startswith("20"):
        return "CMZ"
    if item_code.startswith("10"):
        return "EMCO"
    return None


def _get_default_drawing(item_code):
    return frappe.db.get_value(
        "Drawing Item",
        {
            "parent": item_code,
            "is_default": 1,
            "is_active": 1,
        },
        "drawing",
    )


def _get_machining_work_order_note(sources, shipping_date, expected_date):
    return _("Auto machining planning from submitted SOs: {0}. Customer: {1}. Shipping date: {2}. Expected machining date: {3}.").format(
        " / ".join(_get_sales_order_links_from_sources(sources)),
        _get_customer_names_from_sources(sources),
        _date_to_string(shipping_date),
        _date_to_string(expected_date),
    )


def _get_machining_work_order_description(item_code, sources, shipping_date, expected_date):
    item_description = frappe.db.get_value("Item", item_code, "description") or ""
    planning_note = _get_machining_work_order_note(sources, shipping_date, expected_date)
    return "\n".join([value for value in (item_description, planning_note) if value])


def _get_sales_order_links_from_sources(sources):
    return sorted({
        source.get("sales_order")
        for source in sources
        if source.get("sales_order")
    })


def _get_customer_names_from_sources(sources):
    return " / ".join(sorted({
        source.get("customer_name") or source.get("customer")
        for source in sources
        if source.get("customer_name") or source.get("customer")
    }))


def _set_if_field(doc, fieldname, value):
    if value is not None and doc.meta.has_field(fieldname):
        doc.set(fieldname, value)


def _is_machining_item_code(item_code):
    item_code = str(item_code or "")
    return (
        len(item_code) == MACHINING_ITEM_CODE_LENGTH
        and item_code.isdigit()
        and item_code.startswith(MACHINING_ITEM_PREFIXES)
    )


def _serialize_planning_row(row, work_order):
    sales_orders = sorted({
        source.get("sales_order")
        for source in row.get("sources", [])
        if source.get("sales_order")
    })
    return {
        "work_order": work_order,
        "item_code": row.get("item_code"),
        "qty": _get_integer_work_order_qty(row.get("work_order_qty", row.get("shortage_qty"))),
        "shortage_qty": flt(row.get("shortage_qty")),
        "gross_required_qty": flt(row.get("qty")),
        "covered_qty": flt(row.get("covered_qty")),
        "shipping_date": _date_to_string(row.get("shipping_date")),
        "expected_date": _date_to_string(row.get("expected_date")),
        "priority": row.get("priority"),
        "company": row.get("company"),
        "customer_names": _get_customer_names_from_sources(row.get("sources", [])),
        "sales_orders": sales_orders,
        "sources": row.get("sources", []),
    }


def _date_to_string(value):
    return getdate(value).strftime("%Y-%m-%d") if value else None


def create_work_orders_based_on_reorder_levels():
    # Fetch all items with BOMs
    items_with_bom = frappe.db.sql("""
        SELECT name, item_name, reorder_level, default_bom, item_code
        FROM `tabItem`
        WHERE default_bom IS NOT NULL
        AND default_bom != ''
        AND include_item_in_manufacturing = 1
        AND item_code NOT LIKE '4%'
        AND item_code NOT LIKE '5%'
    """, as_dict=True)

    if TEST_MODE:
        items_with_bom = frappe.get_all(
            "Item",
            filters={
                "default_bom": ["is", "set"],
                "include_item_in_manufacturing": 1,
                "item_code": "320100"
            },
            fields=["name", "item_name", "reorder_level"]
        )

    for item in items_with_bom:
        if TEST_MODE: print("item:",item)
        current_stock = get_stock_balance(item["name"])
        reorder_level = flt(item["reorder_level"])
        if TEST_MODE: print("current_stock:",current_stock," / reorder_level:",reorder_level)
        if current_stock < reorder_level:
            required_qty = reorder_level - current_stock
            if TEST_MODE: print("required_qty:",required_qty)
            process_bom_and_create_work_orders(item["name"], required_qty)
        else:
            delete_draft_wo(item["name"])

def get_stock_balance(item_code, warehouse=("Main Stock - AMF21", "Assemblies - AMF21")):
    """Get current stock balance for an item in a specific warehouse."""
    stock_ledger_entry = frappe.db.sql("""
        SELECT SUM(actual_qty) as actual_qty 
        FROM `tabBin`
        WHERE item_code = %s AND warehouse IN %s
    """, (item_code, warehouse), as_dict=True)
    return flt(stock_ledger_entry[0].get("actual_qty", 0)) if stock_ledger_entry else 0

def process_bom_and_create_work_orders(item_code, required_qty, parent_work_order=None):
    """Process BOM and create work orders for items and sub-assemblies."""
    # Fetch the default BOM for the item
    bom = frappe.get_value("BOM", {"item": item_code, "is_active": 1, "is_default": 1}, "name")
    if TEST_MODE: print("bom:",bom)
    if not bom:
        frappe.log_error(f"No default BOM found for item {item_code}", "Work Order Creation Error")
        return

    # Fetch BOM items
    #bom_items = get_exploded_items(bom)
    
    # Check for existing draft or ongoing work orders
    existing_work_order = frappe.db.exists(
        "Work Order",
        {
            "production_item": item_code,
            "bom_no": bom,
            "docstatus": ["<", 2],  # 0 for draft, 1 for submitted but not completed/cancelled
            "status": ["in", ["Draft", "In Process", "Not Started"]]
        }
    )

    if not existing_work_order:
        #print("Creating WO for item:",item_code)
        # Create work order for the current item
        # Determine priority based on required_qty
        if required_qty <= 1:
            priority = 10
        elif required_qty <= 5:
            priority = 9
        elif required_qty <= 10:
            priority = 8
        elif required_qty <= 20:
            priority = 7
        elif required_qty <= 50:
            priority = 6
        else:
            priority = 5
            
        # Fetch the drawing value from the drawing_item child table
        drawing = frappe.db.get_value(
            "Drawing Item",
            {
                "parent": item_code,  # Link to the Item doctype
                "is_default": 1,
                "is_active": 1
            },
            "drawing"
        )
        
        work_order = frappe.get_doc({
            "doctype": "Work Order",
            "production_item": item_code,
            "qty": int(required_qty * 1.2),
            "bom_no": bom,
            "parent_work_order": parent_work_order,
            "priority": priority,
            "progress": "En Attente",
            "machine": "CMZ" if item_code.startswith("20") else "CMZ" if item_code.startswith("10") else None,
            "drawing": drawing
        })
        work_order.insert()
        frappe.db.commit()  # Commit the transaction if you're running this in a script
        # work_order.submit()
    else:
        print("existing_work_order found:",existing_work_order,"for item:",item_code)

    # # Recursively process sub-assemblies
    # for bom_item in bom_items:
    #     sub_item_code = bom_item["item_code"]
    #     sub_item_qty = flt(bom_item["qty"]) * required_qty

    #     # Check if sub-item has a BOM
    #     has_bom = frappe.get_value("Item", sub_item_code, "has_bom")
    #     if has_bom:
    #         process_bom_and_create_work_orders(sub_item_code, sub_item_qty, work_order.name)
    return None

def delete_draft_wo(item_code):
    """
    Find and delete all 'Draft' Work Orders whose production_item matches the given item_code.
    """
    # Retrieve all draft Work Orders for the item_code
    draft_wos = frappe.get_all(
        "Work Order",
        filters={
            "production_item": item_code,
            "docstatus": 0,  # draft,
            "owner": "Administrator"
        },
        fields=["name"]
    )

    # Delete each draft Work Order
    for wo in draft_wos:
        print("deleting",wo.name,"for item",item_code)
        frappe.delete_doc("Work Order", wo.name, force=1)
        frappe.db.commit()  # Commit after each deletion if needed

    return None

def get_exploded_items(bom_name):
    """Fetch exploded items from the BOM doctype."""
    bom_doc = frappe.get_doc("BOM", bom_name)
    exploded_items = bom_doc.get("items")
    
    items_with_stock = []
    
    for item in exploded_items:
        stock_balance = frappe.db.get_value(
            "Bin", 
            {"item_code": item.item_code, "warehouse": 'Main Stock - AMF21'}, 
            "actual_qty"
        ) or 0

        #print(f"Item Code: {item.item_code}, Qty: {item.stock_qty}, UOM: {item.stock_uom}, Stock Balance: {stock_balance}")
        
        items_with_stock.append({
            "item_code": item.item_code,
            "required_qty": item.stock_qty,
            "uom": item.stock_uom,
            "stock_balance": stock_balance
        })
    
    return items_with_stock
