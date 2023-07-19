import frappe

@frappe.whitelist()
def get_planning_list():
    print("get_planning_list")
    planning_list = frappe.get_all('Planning', fields=['name', 'status', 'job_card', 'qty', 'item'])
    return planning_list
