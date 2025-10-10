import frappe
from frappe import _

@frappe.whitelist()
def get_work_orders():
# fetch the work_orders in two list ongoing and upcoming
    ongoing = frappe.get_all(
        "Work Order",
        filters={"status": "In Process"},
        fields=["name", "production_item","item_name","assembly_specialist_start"]
    )

    upcoming = frappe.get_all(
        "Work Order",
        filters={"docstatus": 1, "status": "Not Started"},
        fields=["name", "production_item","item_name","assembly_specialist_start"]
    )

    draft = frappe.get_all(
        "Work Order",
        filters={"docstatus": 0, "status": "Draft", "priority": ["<=",5]},
            fields=["name", "production_item","item_name","assembly_specialist_start", "progress"]
    )
    for wo in ongoing:
        # wo["item_group"] = frappe.get_value("Item", wo.production_item, "item_group") 
        wo["operation_type"] = "Assemblage" # usinage never started
    
    for wo in upcoming:
        # wo["item_group"] = frappe.get_value("Item", wo.production_item, "item_group")
        wo["operation_type"] = "Assemblage" # usinage never submited

    for wo in draft:
        wo["item_group"] = frappe.get_value("Item", wo.production_item, "item_group")
        wo["operation_type"] = find_operation_type(wo)
        if wo["operation_type"] == "Usinage" :
            print(wo["name"])
            if wo["progress"] in ["Fabrication", "QC"] :
                ongoing.append(wo)
            else :
                upcoming.append(wo)
        
    return {
        "ongoing": ongoing,
        "upcoming": upcoming
    }

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
    

@frappe.whitelist()
def get_shipments():
    from datetime import date, timedelta

    today = date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)

    shipments = frappe.get_all(
        "Sales Order",
        filters={
            "delivery_date": ["between", [monday, sunday]],
            "docstatus": 1  # validées
        },
        fields=["name", "customer_address", "delivery_date"],
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




