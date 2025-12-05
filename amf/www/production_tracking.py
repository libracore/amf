import frappe
from frappe import _

@frappe.whitelist()
def get_work_orders():
# fetch the work_orders in two list ongoing and upcoming
    # fetch work orders with status "In Process" or "Not Started" and not like %100_ (521000,591000,521003,...)
    ongoing = frappe.get_all(
        "Work Order",
        filters={"status": "In Process",
                 "production_item": ["not like", "%100_"] },
        fields=["name", "production_item","item_name"]
    )

    # fetch work orders with status "Not Started" but submitted and not like %100_ (521000,591000, 52100_,...)
    upcoming = frappe.get_all(
        "Work Order",
        filters={"docstatus": 1, "status": "Not Started",
                 "production_item": ["not like", "5_100_"] },
        fields=["name", "production_item","item_name"]
    )

    # fetch work orders with status "Draft" and priority <= 5 (for usinage)
    draft = frappe.get_all(
        "Work Order",
        filters={"docstatus": 0, "status": "Draft", "priority": ["<=",5]},
            fields=["name", "production_item","item_name", "progress"]
    )
    for wo in ongoing:
        # wo["item_group"] = frappe.get_value("Item", wo.production_item, "item_group") 
        wo["operation_type"] = "Assemblage" # usinage never started
        wo["timer_info"] = get_timer_info(wo["name"])
        print(wo["timer_info"])
    
    for wo in upcoming:
        # wo["item_group"] = frappe.get_value("Item", wo.production_item, "item_group")
        wo["operation_type"] = "Assemblage" # usinage never submited
        wo["timer_info"] = get_timer_info(wo["name"])
    for wo in draft:
        wo["item_group"] = frappe.get_value("Item", wo.production_item, "item_group")
        wo["operation_type"] = find_operation_type(wo)
        # keeping only usinage work orders in draft 
        if wo["operation_type"] == "Usinage" :
            #  checking the progress to put in ongoing or upcoming
            if wo["progress"] in ["Fabrication", "QC"] :
                ongoing.append(wo)
                # wo["timer_info"] = get_timer_info(wo["name"]) # timer pas utilisé en usinage
                wo["timer_info"] = {"status": None, "operators": "MBA"}
            else :
                upcoming.append(wo)
                # wo["timer_info"] = get_timer_info(wo["name"]) # timer pas utilisé en usinage
                wo["timer_info"] = {"status": None, "operators": "MBA"}
        
    return {
        "ongoing": ongoing,
        "upcoming": upcoming
    }

# Determine operation type based on production item code and item group (assemblage or usinage)
def find_operation_type(work_order):
    code = str(work_order.production_item or "")

    if not (len(code) == 6 and code.isdigit()):
        return "Assemblage"   

    second_digit = code[1]

    group = (work_order.item_group or "").lower()

    if second_digit == "0" and group in ["plug", "valve seat"]:
        return "Usinage"
    else:
        return "Assemblage"


def get_timer_info(work_order):
    """retourne le statut et le(s) operateur(s) du'un work order si un timer existe"""
    if frappe.db.exists("Timer Production", {"work_order": work_order, "status": ["in", ["IN PROCESS", "PAUSED"]]}):
        timer = frappe.get_doc("Timer Production", {"work_order": work_order})
        return {
            "status": timer.status,
            "operators": timer.assigned_operators
        }
    return {
        "status": None,
        "operators": None,
    }


# Get shipments for the current week (Monday to Sunday)
@frappe.whitelist()
def get_shipments():
    from datetime import date, timedelta

    today = date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)

    # get all sales orders with delivery date in the current week and docstatus = 1 (submitted)
    shipments = frappe.get_all(
        "Sales Order",
        filters={
            "delivery_date": ["between", [monday, sunday]],
            "docstatus": 1  # validées
        },
        fields=["name", "customer_name", "delivery_date"],
        order_by="delivery_date asc"
    )

    for so in shipments:
        # Vérifier si une DN est liée
        has_dn = frappe.db.exists(
            "Delivery Note Item",
            {"against_sales_order": so["name"]}
        )

        if has_dn:
            so["shipment_status"] = "green"
        else:
            if so["delivery_date"] >= today:
                so["shipment_status"] = "white"
            else:
                so["shipment_status"] = "orange"

    return shipments




# Gestion de la zone de note pour le suivi de production
@frappe.whitelist()
def get_note():
    """Retourne la note globale depuis le Doctype Production Notes."""
    note_doc = frappe.get_all("Production Notes", fields=["prod_tracking_note"], limit=1)
    if note_doc:
        return note_doc[0].prod_tracking_note
    return ""

@frappe.whitelist()
def save_note(note_text):
    """Sauvegarde ou crée la note globale dans le Doctype Production Notes."""
    note_doc = frappe.get_all("Production Notes", fields=["name"], limit=1)
    if note_doc:
        frappe.db.set_value("Production Notes", note_doc[0].name, "prod_tracking_note", note_text)
    else:
        frappe.get_doc({
            "doctype": "Production Notes",
            "prod_tracking_note": note_text
        }).insert(ignore_permissions=True)
    frappe.db.commit()
    return "saved"



