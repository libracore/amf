import datetime
import json
import frappe
from frappe import _
from frappe.utils.data import flt
from erpnext.stock.doctype.stock_entry.stock_entry import get_additional_costs


"""
EXAMPLE:
comments: "10:25"
created_on: "2023-10-31"
creation: "2023-10-31 10:35:23.673113"
delivered_qty: ""
docstatus: 0
doctype: "Planning"
drawing: ""
filter: "5"
idx: 0
item: "SPL.1225-C"
material: "PCTFE ∅40mm"
met: ""
modified: "2023-10-31 14:05:34.009613"
modified_by: "staff.production@amf.ch"
name: "M-0000"
owner: "staff.production@amf.ch"
planned_for: "2023-11-03"
prog_time: ""
program: "?"
project: "Prod@AMF"
qty: "25"
start_date: "2023-10-31 14:05:34.006457"
status: "Fab"
who: "ARD"
work_order: "OF-00319"
"""

@frappe.whitelist()
def get_planning_list():
    print("Getting all planning list.")
    fields = [
        'name', 'status', 'work_order', 'qty', 'item', 'project',
        'who', 'created_on', 'planned_for', 'start_date', 'end_date', 'delivered_qty',
        'material', 'drawing', 'drawing_url', 'program', 'prog_time', 'met', 'comments', 'filter'
    ]
    print("Ending all planning list.")
    return frappe.get_all('Planning', fields=fields)

@frappe.whitelist()
def update_planning(doc, method):
    """
    Updates fields in the Planning DocType based on the provided dictionary and method.

    :param doc: Dictionary containing fields and values to update.
    :param method: String indicating the operation type (create, update, etc.).
    """
    print("Entering Update Planning:", doc.get('name'))
    # Check if the input is a dictionary
    if not isinstance(doc, dict):
        frappe.throw(_("Invalid input. Expected a dictionary."))

    # Fetch the planning document
    planning_name = doc.get('name')
    
    if not planning_name:
        frappe.throw(_("No planning name provided in the input dictionary."))

    planning_doc = frappe.get_doc("Planning", planning_name)

    # Update the fields in the planning document based on the input dictionary
    for field, value in doc.items():
        if value is not None and field != 'name':
            planning_doc.set(field, value)

    # Save the updated planning document
    planning_doc.save()

    # Log the result based on the provided method
    log_msg = f"Planning {planning_doc.name} "
    if method == "create":
        print(log_msg + "created successfully.")
    elif method == "update":
        print(log_msg + "updated successfully.")
    else:
        print(log_msg + f"processed. Method used: {method}")


def get_filter_value(doc, method=None):
    # print("Entering Filter Value. Status:", doc.status)
    status_mapping = {
            "QC": 1,
            "Free": 70,
            "Reserved": 65,
            "On Hold": 60,
            "Cancelled": 75,
            "Fab": 5,
            "Done": 80,
            "Rework": 50,
            "Planned #1": 10,
            "Planned #2": 20,
            "Planned #3": 30,
            "Planned #4": 40,
            "Planned #5": 50
    }
    new_filter_value = status_mapping.get(doc.status, 0)
    
    # Only update and save if filter value actually changed
    if doc.filter != new_filter_value:
        doc.filter = new_filter_value
        doc.save(ignore_permissions=True)
        print("Status/Filter change detected:",doc.filter)

    # print("Ending Filter Value.")

@frappe.whitelist()
def start_planning(name):
    print("Starting Planning:", name)
    return create_work_order(name)

def create_work_order(planning_name):
    doc = frappe.get_doc("Planning", planning_name)
    print("Loading Planning:", doc.name)
    print("Planning Work Order:", doc.work_order)
    if doc.work_order:
        print("Planning Work Order detected.")
        return {
            'status': 'error',
            'message': _('Work Order already exists: {0}').format(doc.work_order)
        }
    
    try:
        workorder = create_new_work_order(doc)
        print("New Work Order:", workorder.name)
        update_data = {
            'name': planning_name,
            'status': 'Fab',
            'work_order': workorder.name,
            'start_date': datetime.datetime.now()
        }
        update_planning(update_data, 'update')
        return {
            'status': 'success',
            'message': _('Work Order created successfully: {0}').format(workorder.name)
        }
    except Exception as e:
        return {
            'status': 'error',
            'message': str(e)
        }
    
def create_new_work_order(planning):
    print("Creating New Work Order...")
    item_code = planning.item
    bom_doc = frappe.get_all("BOM", filters={"item": item_code}, fields=["name", "item", "quantity"]) # Get the BOM based on the planning item
    workorder = frappe.new_doc('Work Order')
    workorder.update({
        'production_item': item_code,
        'qty': int(planning.qty),
        'destination': 'N/A',
        'start_date_time': datetime.datetime.now(),
        'p_s_d': datetime.datetime.now(),
        'p_e_d': planning.planned_for,
        'bom_no': bom_doc[0].get("name"),
        'assembly_specialist_start': 'MBA'
    })
    workorder.insert()
    workorder.submit()
    try:
        make_stock_entry(workorder.name, 'Material Transfer for Manufacture', workorder.qty)
    except Exception as e:  # Replace Exception with the specific exception type you're expecting, if applicable.
        print(f"An error occurred while making the stock entry: {e}")
    #workorder.save()
    print("Saved New Work Order.")
    return workorder

def make_stock_entry(work_order_id, purpose, qty=None):
    print("Creating new Stock Entry...")
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
    stock_entry.fg_completed_qty = flt(qty) or (flt(work_order.qty) - flt(work_order.produced_qty))
    
    if work_order.bom_no:
        stock_entry.inspection_required = frappe.db.get_value('BOM', work_order.bom_no, 'inspection_required')

    if purpose=="Material Transfer for Manufacture":
        stock_entry.to_warehouse = wip_warehouse
        stock_entry.project = work_order.project
    else:
        stock_entry.from_warehouse = wip_warehouse
        stock_entry.to_warehouse = work_order.fg_warehouse
        stock_entry.project = work_order.project
        if purpose=="Manufacture":
            additional_costs = get_additional_costs(work_order, fg_qty=stock_entry.fg_completed_qty)
            stock_entry.set("additional_costs", additional_costs)

    stock_entry.set_stock_entry_type()
    stock_entry.get_items()
    stock_entry.save()
    stock_entry.submit()
    print("Done creating and submitting Stock Entry.")

@frappe.whitelist()
def terminate_planning(doc):
    planning = json.loads(doc)
    print("Planning " + planning['name'] + " about to be terminated.")
    return terminate_work_order(planning)

def terminate_work_order(planning):
    doc = frappe.get_doc("Planning", planning['name'])
    print("Planning Work Order:", doc.work_order)
    if doc.work_order is None:
        print("No Planning Work Order detected.")
        return {
            'status': 'error',
            'message': _('Work Order does not exist.')
        }
    
    try:
        workorder = terminate_new_work_order(doc, planning['finalQty'])
        print("Work Order Terminate:", workorder.name)
        update_data = {
            'name': planning['name'],
            'status': 'QC',
            'end_date': datetime.datetime.now(),
            'prog_time': planning['progTime'],
            'met': planning['met'],
            'delivered_qty': planning['finalQty'],
        }
        update_planning(update_data, 'update')
        return {
            'status': 'success',
            'message': _('Work Order terminated successfully: {0}').format(workorder.name)
        }
    except Exception as e:
        return {
            'status': 'error',
            'message': str(e)
        }

def terminate_new_work_order(planning, finalQty):
    print("Terminating Work Order.")
    
    # Start a new transaction
    frappe.db.begin()
    
    try:
        workorder = frappe.get_doc("Work Order", planning.work_order)
        workorder.update({
            'end_date_time': datetime.datetime.now(),
            'assembly_specialist_end': 'MBA'
        })
        workorder.save()

        make_stock_entry(workorder.name, 'Manufacture', finalQty)
        
        # Commit the transaction
        frappe.db.commit()
        
        print("Saved Work Order.")
        
    except Exception as e:  # Replace Exception with the specific exception type you're expecting.
        # Rollback the transaction
        frappe.db.rollback()

        print(f"An error occurred: {e}")
        frappe.log_error(frappe.get_traceback(), "Error in terminating work order")

    return workorder if 'workorder' in locals() else None