from __future__ import unicode_literals

from collections import defaultdict
import heapq

import frappe
from frappe import _, _dict
from frappe.utils import cint, flt, now_datetime
from erpnext.manufacturing.doctype.bom import bom
from amf.amf.utils.stock_entry import (
    _get_or_create_log,
    update_log_entry
)

@frappe.whitelist()
def get_wo_items(sales_order, for_raw_material_request=0):
    '''Returns items with BOM that already do not have a linked work order'''
    sales_order = frappe.get_doc('Sales Order', sales_order)
    items = []
    for table in [sales_order.items, sales_order.packed_items]:
        for i in table:
            bom = get_default_bom_item(i.item_code)
            request_type = get_request_type(i.item_code)
            print("Request type: {request_type}".format(request_type=request_type))
            stock_qty = i.qty if i.doctype == 'Packed Item' else i.stock_qty
            if not for_raw_material_request:
                total_work_order_qty = flt(frappe.db.sql('''select sum(qty) from `tabWork Order`
                    where production_item=%s and sales_order=%s and sales_order_item = %s and docstatus<2''', (i.item_code, sales_order.name, i.name))[0][0])
                pending_qty = stock_qty - total_work_order_qty
            else:
                pending_qty = stock_qty

            if pending_qty and request_type == 'Manufacture':
                items.append(dict(
                    name= i.name,
                    item_code= i.item_code,
                    description= i.description,
                    bom = bom,
                    warehouse = i.warehouse,
                    pending_qty = pending_qty,
                    required_qty = pending_qty if for_raw_material_request else 0,
                    sales_order_item = i.name
                ))
    return items

def get_default_bom_item(item_code):
	bom = frappe.get_all('BOM', dict(item=item_code, is_active=True),
			order_by='is_default desc')
	bom = bom[0].name if bom else None

	return bom

def get_request_type(item_code):
    item = frappe.get_doc('Item', item_code)
    request_type = item.default_material_request_type if item.default_material_request_type else None

    return request_type

@frappe.whitelist()
def get_stock_balance_for_all_warehouses(item_code):
    stock_balance = frappe.db.sql("""
        SELECT warehouse, actual_qty
        FROM `tabBin`
        WHERE item_code = %s AND warehouse not rlike 'OLD'
    """, (item_code), as_dict=1)

    return {row.warehouse: row.actual_qty for row in stock_balance}

BOM_VERSION_UPDATE_JOB = "amf-update-boms-with-latest-versions"
BOM_VERSION_UPDATE_LOCK = "amf:update_boms_with_latest_versions"


@frappe.whitelist()
def update_boms_with_latest_versions_enqueue(dry_run=0, verbose=1):
    """Queue the recursive BOM version update on the long worker."""
    dry_run = cint(dry_run)
    verbose = cint(verbose)
    job = frappe.enqueue(
        "amf.amf.utils.bom_creation.update_boms_with_latest_versions",
        queue="long",
        timeout=15000,
        job_name=BOM_VERSION_UPDATE_JOB,
        dry_run=dry_run,
        verbose=verbose,
    )
    return {
        "status": "queued",
        "job_id": getattr(job, "id", None) or getattr(job, "name", None),
        "dry_run": bool(dry_run),
    }


def update_boms_with_latest_versions(dry_run=0, verbose=0):
    """
    Recursively update every default BOM to the latest default sub-assembly BOM.

    The active, submitted default BOM is the source of truth for each enabled
    Item. The complete default-BOM graph is fetched in two queries and processed
    once in child-to-parent order. If a child link changes, a new submitted BOM
    version is created for the parent and becomes its Item's default. That new
    version is then used by every ancestor processed later in the same run.

    No submitted BOM is edited in place. A live run is committed only after the
    complete graph succeeds; failures roll the transaction back and are raised
    to the background worker instead of being silently swallowed.
    """
    dry_run = bool(cint(dry_run))
    verbose = bool(cint(verbose))
    lock_acquired = False

    try:
        lock_acquired = _acquire_bom_update_lock()
        default_rows, rows_by_bom = _get_default_bom_context()
        default_bom_by_item = _build_default_bom_map(default_rows)
        item_by_bom = {row.name: row.item for row in default_rows}
        processing_order = _get_bottom_up_bom_order(
            default_bom_by_item,
            rows_by_bom,
        )
        boms_to_version = _get_boms_requiring_new_versions(
            processing_order,
            default_bom_by_item,
            rows_by_bom,
        )

        item_default_repairs = [
            {
                "item_code": row.item,
                "from_bom": row.item_default_bom or "",
                "to_bom": row.name,
            }
            for row in default_rows
            if (row.item_default_bom or "") != row.name
        ]
        result = {
            "dry_run": dry_run,
            "default_bom_count": len(default_rows),
            "processed_bom_count": len(processing_order),
            "version_count": len(boms_to_version),
            "item_default_repairs": item_default_repairs,
            "versions": [],
        }

        _trace(
            verbose,
            "Loaded {0} default BOM(s); {1} require a new recursive version.".format(
                len(default_rows), len(boms_to_version)
            ),
        )

        if dry_run:
            result["versions"] = _build_dry_run_version_plan(
                processing_order,
                boms_to_version,
                default_bom_by_item,
                item_by_bom,
                rows_by_bom,
            )
            return result

        # Item.default_bom is also used by the BOM before-save hook. Repair it
        # before creating versions so that hook resolves exactly the same graph.
        for repair in item_default_repairs:
            set_default_bom(repair["item_code"], repair["to_bom"])

        resolved_bom_by_item = dict(default_bom_by_item)
        for bom_name in processing_order:
            if bom_name not in boms_to_version:
                continue

            version = _create_new_bom_version(
                bom_name,
                resolved_bom_by_item,
                verbose=verbose,
            )
            resolved_bom_by_item[version["item_code"]] = version["new_bom"]
            result["versions"].append(version)

        frappe.db.commit()
        _trace(
            verbose,
            "Committed {0} new default BOM version(s).".format(
                len(result["versions"])
            ),
        )
        return result
    except Exception:
        if not dry_run:
            frappe.db.rollback()
        frappe.log_error(
            frappe.get_traceback(),
            "Recursive Default BOM Version Update Failed",
        )
        raise
    finally:
        if lock_acquired:
            _release_bom_update_lock()


def _get_default_bom_context():
    """Bulk-load all usable defaults and their direct material rows."""
    default_rows = frappe.db.sql(
        """
        SELECT
            bom.name,
            bom.item,
            item.default_bom AS item_default_bom
        FROM `tabBOM` bom
        INNER JOIN `tabItem` item ON item.name = bom.item
        WHERE bom.is_active = 1
            AND bom.is_default = 1
            AND bom.docstatus = 1
            AND item.disabled = 0
        ORDER BY bom.item, bom.name
        """,
        as_dict=True,
    )
    material_rows = frappe.db.sql(
        """
        SELECT
            material.parent,
            material.name,
            material.idx,
            material.item_code,
            material.bom_no
        FROM `tabBOM Item` material
        INNER JOIN `tabBOM` bom ON bom.name = material.parent
        INNER JOIN `tabItem` item ON item.name = bom.item
        WHERE bom.is_active = 1
            AND bom.is_default = 1
            AND bom.docstatus = 1
            AND item.disabled = 0
            AND material.parenttype = 'BOM'
        ORDER BY material.parent, material.idx
        """,
        as_dict=True,
    )
    rows_by_bom = defaultdict(list)
    for row in material_rows:
        rows_by_bom[row.parent].append(row)
    return default_rows, rows_by_bom


def _build_default_bom_map(default_rows):
    """Return one unambiguous active submitted default BOM per Item."""
    default_bom_by_item = {}
    duplicates = defaultdict(list)
    for row in default_rows:
        previous = default_bom_by_item.get(row.item)
        if previous and previous != row.name:
            duplicates[row.item].extend([previous, row.name])
        else:
            default_bom_by_item[row.item] = row.name

    if duplicates:
        details = "; ".join(
            "{0}: {1}".format(item, ", ".join(sorted(set(bom_names))))
            for item, bom_names in sorted(duplicates.items())
        )
        frappe.throw(_("Multiple active submitted default BOMs found: {0}").format(details))
    return default_bom_by_item


def _get_bottom_up_bom_order(default_bom_by_item, rows_by_bom):
    """Topologically order the default-BOM forest from leaves to roots."""
    all_boms = set(default_bom_by_item.values())
    dependencies = {bom_name: set() for bom_name in all_boms}
    parents_by_child = defaultdict(set)

    for parent_bom in all_boms:
        for row in rows_by_bom.get(parent_bom, []):
            child_bom = default_bom_by_item.get(row.item_code)
            if child_bom:
                dependencies[parent_bom].add(child_bom)
                parents_by_child[child_bom].add(parent_bom)

    remaining_children = {
        bom_name: len(child_boms)
        for bom_name, child_boms in dependencies.items()
    }
    ready = [
        bom_name
        for bom_name, child_count in remaining_children.items()
        if child_count == 0
    ]
    heapq.heapify(ready)
    ordered = []

    while ready:
        child_bom = heapq.heappop(ready)
        ordered.append(child_bom)
        for parent_bom in sorted(parents_by_child.get(child_bom, set())):
            remaining_children[parent_bom] -= 1
            if remaining_children[parent_bom] == 0:
                heapq.heappush(ready, parent_bom)

    if len(ordered) != len(all_boms):
        cyclic_boms = sorted(all_boms.difference(ordered))
        frappe.throw(
            _("BOM recursion detected among default BOMs: {0}").format(
                ", ".join(cyclic_boms)
            )
        )
    return ordered


def _get_boms_requiring_new_versions(
    processing_order,
    default_bom_by_item,
    rows_by_bom,
):
    """Find direct mismatches and propagate them through every ancestor."""
    changed_boms = set()
    for bom_name in processing_order:
        for row in rows_by_bom.get(bom_name, []):
            child_bom = default_bom_by_item.get(row.item_code)
            direct_mismatch = (row.bom_no or None) != (child_bom or None)
            child_will_be_versioned = child_bom in changed_boms
            if direct_mismatch or child_will_be_versioned:
                changed_boms.add(bom_name)
                break
    return changed_boms


def _build_dry_run_version_plan(
    processing_order,
    boms_to_version,
    default_bom_by_item,
    item_by_bom,
    rows_by_bom,
):
    """Describe recursive changes without guessing future BOM names."""
    plan = []
    for bom_name in processing_order:
        if bom_name not in boms_to_version:
            continue
        changes = []
        for row in rows_by_bom.get(bom_name, []):
            child_bom = default_bom_by_item.get(row.item_code)
            child_is_versioned = child_bom in boms_to_version
            if (row.bom_no or None) == (child_bom or None) and not child_is_versioned:
                continue
            changes.append(
                {
                    "idx": row.idx,
                    "item_code": row.item_code,
                    "from_bom": row.bom_no or "",
                    "to_bom": (
                        "new default version of {0}".format(child_bom)
                        if child_is_versioned
                        else child_bom or ""
                    ),
                }
            )
        plan.append(
            {
                "item_code": item_by_bom[bom_name],
                "source_bom": bom_name,
                "new_bom": None,
                "row_changes": changes,
            }
        )
    return plan


def _create_new_bom_version(bom_name, resolved_bom_by_item, verbose=False):
    """Copy one BOM, assign resolved child defaults, recost, and submit it."""
    state = _get_bom_state(bom_name)
    if not state or not state.is_active or not state.is_default or state.docstatus != 1:
        frappe.throw(_("BOM {0} is no longer an active submitted default").format(bom_name))

    source_bom = frappe.get_doc("BOM", bom_name)
    new_bom = frappe.copy_doc(source_bom)
    new_bom.docstatus = 0
    new_bom.is_active = 1
    # Keeping the copy non-default avoids the custom before-save hook changing
    # existing parent BOMs in place. It is promoted only after successful submit.
    new_bom.is_default = 0
    new_bom.flags.ignore_permissions = True
    row_changes = []

    for row in new_bom.items:
        expected_bom = resolved_bom_by_item.get(row.item_code)
        if (row.bom_no or None) == (expected_bom or None):
            continue
        row_changes.append(
            {
                "idx": row.idx,
                "item_code": row.item_code,
                "from_bom": row.bom_no or "",
                "to_bom": expected_bom or "",
            }
        )
        row.bom_no = expected_bom or None
        # ERPNext V12 preserves a copied non-zero row rate during validation.
        # Clearing cost fields forces it to price the new child BOM link again.
        row.rate = 0
        row.base_rate = 0
        row.amount = 0
        row.base_amount = 0

    if not row_changes:
        frappe.throw(
            _("BOM {0} was scheduled for a new version but has no changed child links").format(
                bom_name
            )
        )

    _trace(
        verbose,
        "Creating a new version of {0} with {1} child BOM change(s).".format(
            bom_name, len(row_changes)
        ),
    )
    new_bom.insert(ignore_permissions=True)

    # The project before-save resolver may have populated links from Item again.
    # Reapply the already-resolved graph before submit; submit validation then
    # recalculates totals and exploded items using these exact links.
    for row in new_bom.items:
        row.bom_no = resolved_bom_by_item.get(row.item_code) or None
    new_bom.submit()
    set_default_bom(new_bom.item, new_bom.name)

    return {
        "item_code": new_bom.item,
        "source_bom": bom_name,
        "new_bom": new_bom.name,
        "row_changes": row_changes,
        "total_cost_before": flt(source_bom.total_cost),
        "total_cost_after": flt(new_bom.total_cost),
    }


def _get_bom_state(bom_name):
    return frappe.db.get_value(
        "BOM",
        bom_name,
        ["item", "is_active", "is_default", "docstatus"],
        as_dict=True,
    )


def create_new_bom_version(bom_name, latest_boms_by_item=None):
    """Backward-compatible single-BOM entry point; the batch method is preferred."""
    if latest_boms_by_item is None:
        default_rows, _unused_rows = _get_default_bom_context()
        latest_boms_by_item = _build_default_bom_map(default_rows)
    try:
        result = _create_new_bom_version(bom_name, latest_boms_by_item)
        frappe.db.commit()
        return result
    except Exception:
        frappe.db.rollback()
        raise


def get_latest_bom(item_code):
    """Return the active submitted default BOM for an Item."""
    return frappe.db.get_value(
        "BOM",
        filters={
            "item": item_code,
            "is_active": 1,
            "is_default": 1,
            "docstatus": 1,
        },
        fieldname="name",
    )


def set_default_bom(item_code, bom_name):
    """Atomically align BOM flags and the Item's core/custom BOM snapshot."""
    bom_values = frappe.db.get_value(
        "BOM",
        bom_name,
        ["item", "is_active", "docstatus", "total_cost"],
        as_dict=True,
    )
    if (
        not bom_values
        or bom_values.item != item_code
        or not bom_values.is_active
        or bom_values.docstatus != 1
    ):
        frappe.throw(
            _("BOM {0} is not an active submitted BOM for Item {1}").format(
                bom_name, item_code
            )
        )

    frappe.db.sql(
        """
        UPDATE `tabBOM`
        SET is_default = CASE WHEN name = %(bom_name)s THEN 1 ELSE 0 END
        WHERE item = %(item_code)s
            AND is_default != CASE WHEN name = %(bom_name)s THEN 1 ELSE 0 END
        """,
        {"item_code": item_code, "bom_name": bom_name},
    )

    item_values = {"default_bom": bom_name}
    item_meta = frappe.get_meta("Item")
    if item_meta.has_field("item_default_bom"):
        item_values["item_default_bom"] = bom_name
    if item_meta.has_field("bom_cost"):
        item_values["bom_cost"] = flt(bom_values.total_cost)
    frappe.db.set_value("Item", item_code, item_values, update_modified=False)
    frappe.clear_document_cache("BOM", bom_name)
    frappe.clear_document_cache("Item", item_code)

    # The AMF Item doctype keeps a denormalized BOM table for downstream
    # workflows. Refresh it without doc.save(), whose custom hook commits inside
    # the loop and would break the all-or-nothing transaction used here.
    if item_meta.has_field("bom_table"):
        from amf.amf.utils.bom_mgt import _populate_item_bom_snapshot

        item_doc = frappe.get_doc("Item", item_code)
        _populate_item_bom_snapshot(item_doc)
        item_doc.db_update()
        item_doc.update_child_table("bom_table")
        frappe.clear_document_cache("Item", item_code)


def _acquire_bom_update_lock():
    lock_result = frappe.db.sql(
        "SELECT GET_LOCK(%s, 0)",
        (BOM_VERSION_UPDATE_LOCK,),
    )
    if not lock_result or cint(lock_result[0][0]) != 1:
        frappe.throw(_("Another recursive BOM version update is already running"))
    return True


def _release_bom_update_lock():
    frappe.db.sql("SELECT RELEASE_LOCK(%s)", (BOM_VERSION_UPDATE_LOCK,))


def _trace(enabled, message):
    if enabled:
        print("[BOM Version Update {0}] {1}".format(now_datetime(), message))


def create_bom_for_assembly(assembly_code, materials, scraps = None, check_existence=False, log_id=None):
    """Creates a BOM in Draft state. Does not submit."""

    # 1. checking log_id
    if not log_id:
        # créer un log local si aucun log parent n’est fourni
        context = _dict(doctype="BOM", name=f"BOM Creation - {assembly_code}")
        log_id = _get_or_create_log(context)
    update_log_entry(log_id, f"[{now_datetime()}] Starting BOM creation for assembly {assembly_code}")

    # 2. validate parameter
    if not assembly_code:
        frappe.throw(_("assembly_code is required to create a BOM"))

    # 3. validate materials
    for material in materials:
        while not frappe.db.exists("Item", {"name": material.get("item_code")}):
            frappe.throw(_("Material item {0} does not exist. Cannot create BOM for {1}.").format(material.get("item_code"), assembly_code))
    
    # 4. validate scraps
    if scraps:
        for scrap in (scraps or []):
            while not frappe.db.exists("Item", {"name": scrap.get("item_code")}):
                frappe.throw(_("Scrap item {0} does not exist. Cannot create BOM for {1}.").format(scrap.get("item_code"), assembly_code))
    
    # 5. check if there is already an existing BOM for this item
    if frappe.db.exists("BOM", {"item": assembly_code}) and check_existence:
        update_log_entry(log_id, f"[{now_datetime()}] BOM already exists for assembly {assembly_code}. Skipping.")
        return

    
    try:
        # 6. creating new BOM
        bom_doc = frappe.new_doc("BOM")
        bom_doc.item = assembly_code
        bom_doc.is_active = 1
        bom_doc.is_default = 1
        bom_doc.quantity = 1
        bom_doc.company = frappe.get_cached_value('User', frappe.session.user, 'company')
        update_log_entry(log_id, f"[{now_datetime()}] Initialized BOM doc for {assembly_code}")

        # 7. add materials in BOM item table 
        for material in materials:
            material_code = material.get("item_code")
            #checking if material has a bom 
            filters = {"item": material_code, "is_active": 1, "is_default": 1}
            if frappe.db.exists("BOM", filters):
                material_bom = frappe.db.get_value("BOM", filters, "name")
            else:
                material_bom = None
            print(material_bom)
            if material.get('qty'): # Only add materials with a quantity > 0
                #print(material.get("item_code"))
                bom_doc.append("items", {
                    "item_code": material_code,
                    "qty": material.get("qty"),
                    "bom_no": material_bom
                })

        # 8. add scrap material in BOM scrap item table
        if scraps:
            for scrap in scraps:
                scrap_code = scrap.get("item_code")
                #checking if material has a bom 
                filters = {"item": scrap_code, "is_active": 1, "is_default": 1}
                if frappe.db.exists("BOM", filters):
                    scrap_bom = frappe.db.get_value("BOM", filters, "name")
                else:
                    scrap_bom = None
                #print(scrap.get("item_code"))
                if scrap.get('qty'): # Only add scraps with a quantity > 0
                    bom_doc.append("scrap_items", {
                        "item_code": scrap_code,
                        "stock_qty": scrap.get("qty"),
                        "bom_no": scrap_bom
                    })
        
        # 9 Insert, enrich scraps, save & submit
        bom_doc.insert(ignore_permissions=True)
        update_log_entry(log_id, f"[{now_datetime()}] Inserted BOM document (Draft)")

        fill_scrap_details(bom_doc)         # complète les champs des scraps (item_name, rate, etc.)
        bom_doc.save()
        bom_doc.submit()
        frappe.db.commit() # Commit the transaction after the final step.
        update_log_entry(log_id, f"[{now_datetime()}] Created and submitted BOM {bom_doc.name} for assembly {assembly_code}")

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"BOM Creation Failed for {assembly_code}")
        update_log_entry(log_id, f"[{now_datetime()}] Error creating BOM for {assembly_code}: {e}")
        frappe.throw(_("Error creating BOM for {0}: {1}").format(assembly_code, e))

    
def fill_scrap_details(bom_doc):
    """Complète automatiquement les champs des scrap_items en se basant sur get_bom_material_detail()."""
    for scrap in bom_doc.get("scrap_items") or []:
        if not scrap.item_code:
            continue

        # On utilise directement le bom_doc qu'on est en train de créer
        args = {
            "item_code": scrap.item_code,
            "item_name": scrap.item_name or "",
            "bom_no": "",
            "uom": scrap.stock_uom or "",
            "stock_qty": scrap.stock_qty or 1,
        }

        try:
            ret = bom_doc.get_bom_material_detail(args)
        except Exception as e:
            frappe.throw(f"Error in get_bom_material_detail for scrap {scrap.item_code} : {e}")
            frappe.log_error(frappe.get_traceback(), f"Error in get_bom_material_detail for scrap {scrap.item_code}")
            continue

        # On copie les champs pertinents
        for key in ["item_name", "stock_uom", "rate", "base_rate"]:
            if not scrap.get(key):
                scrap.set(key, ret.get(key))

        # Calcul du montant
        scrap.amount = (scrap.stock_qty or 0.0) * (scrap.rate or 0.0)
