import frappe
from frappe.utils import flt
from erpnext.manufacturing.doctype.bom.bom import get_children as get_bom_items

@frappe.whitelist()
def enqueue_work_orders_for_sales_order(doc, method):
    # doc is the Sales Order document in memory
    print("enqueuing...")
    frappe.enqueue(
        method="amf.amf.utils.sales_order_utils.create_work_orders_for_sales_order",
        queue="long",
        timeout=4000,
        enqueue_after_commit=True,# adjust as needed
        docname=doc.name
    )

@frappe.whitelist()
def create_work_orders_for_sales_order(docname):
    """
    Triggered by doc_events when a Sales Order is submitted (or inserted).
    - doc: The Sales Order document (python object).
    - method: The event method (e.g., 'on_submit').
    """
    # print("Enqueued 'create_work_orders_for_sales_order'. Launching...")
    # print(f"Debug: About to create WO for Sales Order {doc.name}, docstatus={doc.docstatus}")
    # exists = frappe.db.exists("Sales Order", doc.name)
    # print(f"Debug: frappe.db.exists says: {exists}")
    doc = frappe.get_doc("Sales Order", docname)
    # Loop through items in the Sales Order
    for so_item in doc.items:
        item_code = so_item.item_code
        qty_required = so_item.qty

        # 1. Check if the item is manufactured (e.g., has a default BOM).
        if is_manufactured_item(item_code):
            # 2. Check stock availability for item_code in the default warehouse
            #    or derive the warehouse from so_item.warehouse
            warehouse = "Main Stock - AMF21"
            current_stock = get_current_stock(item_code, warehouse)

            # 3. Determine if a Work Order is needed for the shortfall.
            #    Example logic: if current_stock < qty_required
            shortfall_qty = max(flt(qty_required - current_stock), 0)
            if shortfall_qty > 0:
                # 4. Create a Work Order for the main item
                wo_name = create_work_order(item_code, shortfall_qty, doc.name, doc.customer, warehouse)

                # 5. If the BOM for this item has sub-assemblies, create them too
                recursively_create_subassembly_work_orders(item_code, shortfall_qty, doc.name, doc.customer, warehouse)

                frappe.msgprint(
                    msg=f"Ordre de Fabrication '{wo_name}' crée pour l'article '{item_code}' > '{shortfall_qty}' pièces.",
                    title="Ordres de Fabrication crées avec succès",
                    indicator="green"
                )
            else:
                frappe.msgprint(
                    msg=f"Aucun Ordre de Fabrication requis. Stock suffisant",
                    title="Ordres de Fabrication non crées",
                    indicator="orange"
                )

def is_manufactured_item(item_code):
    """
    Checks if this item is a manufactured item.
    - Typically, you can check if 'is_manufactured_item' is set or if a default BOM exists.
    """
    # Quick check: does this item have a default BOM?
    default_bom = frappe.db.get_value("Item", item_code, "default_bom")
    return True if default_bom else False


def get_current_stock(item_code, warehouse):
    """
    Returns the current stock quantity of `item_code` in `warehouse`.
    This uses the `Bin` doctype or other ERPNext stock APIs.
    """
    # Option A: Use get_bin_qty from erpnext.stock.doctype.bin.bin
    # (Make sure you pass the correct filters)
    # bin_qty = get_bin_qty(item_code, warehouse)
    # return flt(bin_qty)

    # Option B: Direct DB query on `tabBin`
    bin_qty = frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty") or 0
    return flt(bin_qty)


def create_work_order(item_code, qty, sales_order, customer, warehouse):
    """
    Creates a new Work Order for item_code with the given qty, linked to a specific Sales Order.
    Optionally includes the customer, warehouse, etc.
    Returns the Work Order name.
    """
    default_bom = frappe.db.get_value("Item", item_code, "default_bom")
    if not default_bom:
        frappe.throw(f"No default BOM found for item {item_code}. Cannot create Work Order.")

    # Create the Work Order doc
    wo_doc = frappe.new_doc("Work Order")
    wo_doc.company = frappe.defaults.get_user_default("Company")
    wo_doc.bom_no = default_bom
    wo_doc.production_item = item_code
    wo_doc.qty = qty
    wo_doc.sales_order = sales_order
    wo_doc.custo_name = customer
    wo_doc.wip_warehouse = "Work In Progress - AMF21"  # or use a dedicated WIP warehouse
    wo_doc.fg_warehouse = "Main Stock - AMF21"   # finished goods warehouse
    wo_doc.auto_gen = 1

    wo_doc.save(ignore_permissions=True)
    # Submit the Work Order
    #wo_doc.submit()
    frappe.db.commit()
    return wo_doc.name


def recursively_create_subassembly_work_orders(parent_item_code, parent_qty, sales_order, customer, warehouse):
    """
    For each sub-assembly (child item) in the BOM of `parent_item_code`,
    check if it is a manufactured item. If so, create Work Orders as needed.
    """
    # 1. Get the BOM details of the parent item (assumes the 'default BOM' is used)
    default_bom = frappe.db.get_value("Item", parent_item_code, "default_bom")
    if not default_bom:
        return  # No BOM, no sub-assemblies

    # 2. Retrieve BOM children
    bom_children = get_bom_items('BOM', default_bom)

    # 3. Loop through each child item
    for child in bom_children:
        child_item_code = child.item_code
        # child_qty is the per-unit quantity needed for the parent item
        child_qty_per_unit = flt(child.qty)
        # total qty needed for the parent's production
        child_total_qty_required = parent_qty * child_qty_per_unit

        # Check if child item is also manufactured
        if is_manufactured_item(child_item_code):
            # Check the current stock
            child_current_stock = get_current_stock(child_item_code, warehouse)
            child_shortfall_qty = max(child_total_qty_required - child_current_stock, 0)

            if child_shortfall_qty > 0:
                # Create Work Order for the sub-assembly
                wo_name = create_work_order(child_item_code, child_shortfall_qty, sales_order, customer, warehouse)

                frappe.msgprint(
                    msg=f"Work Order '{wo_name}' created for Sub-assembly Item '{child_item_code}' "
                        f"with Qty '{child_shortfall_qty}'.",
                    title="Sub-assembly Work Order Created",
                    indicator="blue"
                )

                # Recursively check the sub-assemblies of this child item
                recursively_create_subassembly_work_orders(child_item_code, child_shortfall_qty, 
                                                           sales_order, customer, warehouse)
