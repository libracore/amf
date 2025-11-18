import frappe
from frappe import _
from frappe.utils import flt
from erpnext.manufacturing.doctype.bom.bom import get_children as get_bom_items

@frappe.whitelist()
def enqueue_work_orders_for_sales_order(doc, method):
    """
    doc_events handler for 'on_submit', 'on_update_after_submit', etc. of the Sales Order.
    Enqueues the creation of Work Orders for the given Sales Order.
    """
    # doc is the Sales Order document passed in memory by doc_events
    # Using frappe.enqueue to move the heavy lifting to a background worker
    frappe.enqueue(
        method="amf.amf.utils.sales_order_utils.create_work_orders_for_sales_order",
        queue="long",
        timeout=4000,
        enqueue_after_commit=True,
        docname=doc.name
    )

@frappe.whitelist()
def create_work_orders_for_sales_order(docname):
    """
    Asynchronously called to create Work Orders for a given Sales Order document.
    1. Fetch the Sales Order from DB to ensure it's the latest version.
    2. Loop through each item in the Sales Order.
    3. If the item is manufactured and has a shortfall in stock, create a Work Order.
    4. Create sub-assembly Work Orders if needed.
    """
    # 1. Fetch the Sales Order doc
    doc = frappe.get_doc("Sales Order", docname)
    if doc.docstatus != 1:
        frappe.throw(_(f"La commande client {docname} doit être soumise pour créer des ordres de fabrication."))

    # 2. Loop through items in the Sales Order
    for so_item in doc.items:
        item_code = so_item.item_code
        qty_required = flt(so_item.qty)
        warehouse = "Main Stock - AMF21"  # use SO item warehouse if available, else fallback

        # 3. Check if the item is manufactured
        if is_manufactured_item(item_code):
            current_stock = get_current_stock(item_code, warehouse)
            shortfall_qty = max(qty_required - current_stock, 0)

            if shortfall_qty > 0:
                # Create the main Work Order
                wo_name, existing = create_work_order(
                    item_code     = item_code,
                    qty           = shortfall_qty,
                    warehouse     = warehouse,
                    sales_order   = doc.name,
                )

                frappe.msgprint(
                    _(
                        """<div style="font-size: 14px; line-height: 1.5; margin: 6px 0;">
                            <strong>Ordre de fabrication créé :</strong> <a href="https://amf.libracore.ch/desk#Form/Work%20Order/{0}" target="_blank">{0}</a><br>
                            <strong>Article :</strong> {1}<br>
                            <strong>Quantité :</strong> {2} pièce(s)
                        </div>"""
                    ).format(wo_name, item_code, shortfall_qty),
                    title=_("Création des ordres de fabrication"),
                    indicator="blue"
                )


                # 4. Create sub-assembly Work Orders, if any
                recursively_create_subassembly_work_orders(
                    parent_item_code = item_code,
                    parent_qty       = shortfall_qty,
                    warehouse        = warehouse
                )
            else:
                frappe.msgprint(
                    _(
                        """<div style="font-size: 14px; line-height: 1.5; margin: 6px 0;">
                            <strong>Aucun ordre de fabrication n'est nécessaire pour l'article :</strong> {0}<br>
                            <span style="color: #2b47d9;">Le stock est suffisant</span><br>
                            <strong>Requis :</strong> {1}, <strong>En stock :</strong> {2}
                        </div>"""
                    ).format(item_code, qty_required, current_stock),
                    title=_("Création des ordres de fabrication"),
                    indicator="blue"
                )

def is_manufactured_item(item_code):
    """
    Checks if this item is a manufactured item by looking at a relevant field,
    e.g. 'include_item_in_manufacturing' on the Item doctype or the presence of a default BOM.
    Adjust based on your data model.
    """
    return frappe.db.get_value("Item", item_code, "include_item_in_manufacturing") == 1

def get_current_stock(item_code, warehouse):
    """
    Returns the current stock quantity of `item_code` in `warehouse`.
    Looks up the Bin doctype for actual_qty.
    """
    bin_qty = frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty") or 0
    return flt(bin_qty)

def get_default_bom(item_code):
    """
    Return the name of the default BOM for the given item_code, or None if not found.
    This uses BOM's is_default=1 field.
    """
    return frappe.db.get_value("BOM", {"item": item_code, "is_default": 1}, "name")

def create_work_order(item_code, qty, warehouse, sales_order=None):
    """
    Creates and returns a Work Order name for the given item_code and qty.
    Links the Work Order to a particular Sales Order and Customer.
    """
    if not item_code:
        frappe.throw(_("Cannot create Work Order: Item Code is missing."))

    # customer = None
    # if sales_order:
    #     so_doc = frappe.get_doc("Sales Order", sales_order)
    #     customer = so_doc.customer_name  # or any other field you need
    
    # 1. Attempt to find an existing DRAFT Work Order for the same item and (optionally) same Sales Order
    filters = {
        "production_item": item_code,
        "docstatus": 0,  # draft
    }
    if sales_order:
        filters["sales_order"] = sales_order
        
    existing_wo_name = frappe.db.exists("Work Order", filters)
    if existing_wo_name:
        
        # 2. If we found one, update its quantity
        existing_wo = frappe.get_doc("Work Order", existing_wo_name)
        existing_wo.qty = flt(existing_wo.qty) + flt(qty)
        existing_wo.save(ignore_permissions=True)
        frappe.db.commit()

        # Return the existing WO name (we've just updated it)
        return existing_wo.name, True if existing_wo.name else False
    
    # Get default BOM
    default_bom = get_default_bom(item_code)
    if not default_bom:
        frappe.throw(_("No default BOM found for Item '{0}'. Please set 'is_default=1' on at least one BOM.").format(item_code))

    # Create the Work Order doc
    wo_doc = frappe.new_doc("Work Order")
    wo_doc.company          = frappe.defaults.get_user_default("Company")
    wo_doc.bom_no           = default_bom
    wo_doc.production_item  = item_code
    wo_doc.qty              = qty
    wo_doc.sales_order      = sales_order
    #wo_doc.custo_name       = customer
    wo_doc.wip_warehouse    = "Work In Progress - AMF21"   # Example WIP warehouse
    wo_doc.fg_warehouse     = warehouse                     # Where the finished goods go
    wo_doc.auto_gen         = 1
    wo_doc.priority         = 0
    #wo_doc.assembly_specialist_start = 'CBE'
    if item_code.startswith("4"):
        wo_doc.wip_step = 1
    if item_code.startswith("10") or item_code.startswith("20"):
        wo_doc.wip_step = 1
        wo_doc.assembly_specialist_start = 'MBA'
        wo_doc.progress = 'En Attente'

    wo_doc.save(ignore_permissions=True)
    # Optionally submit if you require the Work Order to be in submitted state:
    if wo_doc.sales_order:
        wo_doc.submit()

    frappe.db.commit()  # commit so subsequent queries can see this record
    return wo_doc.name, False

def recursively_create_subassembly_work_orders(parent_item_code, parent_qty, warehouse):
    """
    Recursively creates Work Orders for each sub-assembly in the default BOM of `parent_item_code`.
    
    1. Fetch default BOM of the parent item.
    2. For each child item in that BOM:
       a. Calculate the total quantity needed for the parent's required qty.
       b. If the child is also a manufactured item and has a shortfall, create a Work Order.
       c. Recursively call this function for deeper sub-assemblies.
    """
    if not parent_item_code:
        frappe.throw(_("Parent Item Code is missing in sub-assembly creation."))

    default_bom = get_default_bom(parent_item_code)
    if not default_bom:
        # If there's no BOM, no sub-assemblies to create
        return

    # Retrieve the children from the BOM doctype
    bom_children = get_bom_items("BOM", default_bom)
    for child in bom_children:
        child_item_code = child.get("item_code")
        # This field name could differ based on your BOM structure
        child_qty_per_unit = flt(child.get("stock_qty", 0))  # how many units of child needed to make 1 parent

        if not child_item_code:
            continue

        # Calculate total child qty needed
        total_child_qty_needed = parent_qty * child_qty_per_unit

        if is_manufactured_item(child_item_code) and total_child_qty_needed > 0:
            child_current_stock = get_current_stock(child_item_code, warehouse)
            child_shortfall_qty = max(total_child_qty_needed - child_current_stock, 0)

            if child_shortfall_qty > 0:
                # Create Work Order for the sub-assembly
                wo_name, existing = create_work_order(
                    item_code   = child_item_code,
                    qty         = child_shortfall_qty,
                    warehouse   = warehouse,
                )

                if existing:
                    frappe.msgprint(
                        _(
                            """<div style="font-size: 14px; line-height: 1.5; margin: 6px 0;">
                                <strong>Ordre de fabrication existant et mis à jour :</strong> <a href="https://amf.libracore.ch/desk#Form/Work%20Order/{0}" target="_blank">{0}</a><br>
                                <strong>Article sous-assemblé :</strong> {1}<br>
                                <strong>Quantité ajoutée :</strong> {2} pièce(s)
                            </div>"""
                        ).format(wo_name, child_item_code, child_shortfall_qty),
                        title=_("Création des ordres de fabrication"),
                        indicator="blue"
                    )
                else:
                    frappe.msgprint(
                        _(
                            """<div style="font-size: 14px; line-height: 1.5; margin: 6px 0;">
                                <strong>Ordre de fabrication créé :</strong> <a href="https://amf.libracore.ch/desk#Form/Work%20Order/{0}" target="_blank">{0}</a><br>
                                <strong>Article sous-assemblé :</strong> {1}<br>
                                <strong>Quantité :</strong> {2} pièce(s)
                            </div>"""
                        ).format(wo_name, child_item_code, child_shortfall_qty),
                        title=_("Création des ordres de fabrication"),
                        indicator="blue"
                    )

                # Recurse down if the sub-assembly BOM also has sub-assemblies
                recursively_create_subassembly_work_orders(
                    parent_item_code = child_item_code,
                    parent_qty       = child_shortfall_qty,
                    warehouse        = warehouse,
                )
