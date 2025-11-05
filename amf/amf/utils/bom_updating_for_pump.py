from __future__ import unicode_literals
import time
import frappe
from frappe import _, _dict
from frappe.utils import flt, now_datetime, add_days
from amf.amf.utils.bom_creation import create_bom_for_assembly
from amf.amf.utils.stock_entry import (
    _get_or_create_log,
    update_log_entry
)



@frappe.whitelist()
def enqueue_update_pumps_bom():
    """Called from frontend — enqueue the background job"""
    frappe.enqueue(
        "amf.amf.utils.bom_updating_for_pump.update_pumps_bom",  # chemin vers la fonction ci-dessous
        queue='long',
        timeout=1200,  # jusqu'à 20min d'exécution
    )
    return _("BOM update has been queued. You can monitor it under Background Jobs.")


def update_pumps_bom():
    """ Update BOM for pump item to latest version - (moving RVM.1204 in scraps section)"""
    # Initialize log
    context = _dict(doctype="BOM", name="Pumps BOM Update")
    log_id = _get_or_create_log(context)
    print("start")
    update_log_entry(log_id, f"[{now_datetime()}] Starting update_pumps_bom")

    # Getting all the pumps affected by the modification.
    pumps = frappe.db.get_all('Item', 
                    filters={'item_group': 'Product', 'disabled': 0},
                    or_filters=[['item_name', 'like', 'P100%'],
                                ['item_name', 'like', 'P110%'],],
                    fields=['item_code', 'item_name'])

    count = len(pumps)
    update_log_entry(log_id, f"[{now_datetime()}] Found {count} pump(s) to process")


    for pump in pumps:
        try:
            pump_materials = prepare_materials_for_pump(pump.item_code, pump.item_name)
            pump_scraps = [{"item_code": "RVM.1204", "qty": 1},]
            create_bom_for_assembly(pump.item_code, pump_materials, pump_scraps, check_existence=False, log_id=log_id)
        
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), f"Error updating BOM for pump {pump.item_code}")
            update_log_entry(log_id,f"[{now_datetime()}] Error while creating BOM for {pump.item_code}: {e}")
            #continue with next pump
            continue
    update_log_entry(log_id, f"[{now_datetime()}] Completed update_pumps_bom\n")
    print("done!"),
    frappe.db.commit()
    

        

def prepare_materials_for_pump(item_code, item_name):
    """ Prepares materials list for pump BOM update """
    parts = item_name.split('/')
    expected_head_rnd = '/'.join(parts[1:-1])
    head_code = f"300{item_code[-3:]}"
    head_rnd = frappe.db.get_value('Item', head_code, 'reference_code')
    if not (head_rnd and head_rnd.startswith(expected_head_rnd)):
        print("Mismatch in head RND for pump ", item_code, ": expected ", expected_head_rnd, " but got ", head_rnd)
        try:
            head_code = frappe.db.get_value(
                "Item",
                filters={
                    "reference_code": expected_head_rnd,
                    "disabled": 0,
                },
                fieldname="item_code",
            )

            if not head_code:
                msg = (f"No active item found for pump '{item_name}' "
                       f"with reference_code '{expected_head_rnd}'. Skipping.")
                print(msg)
                frappe.log_error(message=msg, title="Pump BOM Update - Missing Head Item")
                return None


        except Exception as e:
            msg = f"Error retrieving head item for pump '{item_name}': {e}"
            print(msg)
            frappe.log_error(message=msg, title="Pump BOM Update - DB Error")
            return None
    motor_code = f"5{item_code[1]}1000"   
    syringe_code = f"70{item_code[2]}000" 
    #print("Preparing materials for pump:", item_code, "and motor:", motor_code, "and syringe:", syringe_code, "with head:", head_rnd,)   
    materials = [
        {"item_code": motor_code, "qty": 1},
        {"item_code": syringe_code, "qty": 1},
        {"item_code": head_code, "qty": 1},
        {"item_code": "SPL.3028", "qty": 2},
    ]   
    return materials