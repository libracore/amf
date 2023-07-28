import json
import frappe
from frappe import _

@frappe.whitelist()
def get_planning_list():
    planning_list = frappe.get_all('Planning', fields=['name', 'status', 'job_card', 'qty', 'item', 'project', 'who', 'created_on', 'planned_for', 'end_date', 'delivered_qty', 'material', 'drawing', 'program', 'comments', 'filter'])
    return planning_list

@frappe.whitelist()
def update_status(name, status):
    doc = frappe.get_doc("Planning", name)
    doc.status = status
    doc.filter = update_filter(status)
    doc.save()

@frappe.whitelist()
def update_filter(status):
    filterValue = 0
    if status == "QC":
            filterValue = 1
    elif status == "Free":
            filterValue = 70
    elif status == "Reserved":
            filterValue = 65
    elif status == "On Hold":
            filterValue = 60
    elif status == "Cancelled":
            filterValue = 75
    elif status == "Fab":
            filterValue = 5
    elif status == "Done":
            filterValue = 80
    elif status == "Rework":
            filterValue = 50
    elif status == "Planned #1":
            filterValue = 10
    elif status == "Planned #2":
            filterValue = 20
    elif status == "Planned #3":
            filterValue = 30
    elif status == "Planned #4":
            filterValue = 40
    elif status == "Planned #5":
            filterValue = 50
    print(filterValue)
    return filterValue

@frappe.whitelist()
def create_job_card(row_data_str):
    row_data = json.loads(row_data_str)
    print(row_data)

    update_status(row_data[2], "Fab")
    
    # You can include additional validation if needed
    if not row_data[2]:
        return {
            'status': 'error',
            'message': _('Job Card Name cannot be empty.')
        }

    try:
        print("Creating a new Job Card")
        # Create a new Job Card
        doc = frappe.new_doc('Job Card')
        doc.work_order = "OF-00072"
        doc.for_quantity = row_data[3]
        doc.description_operation = row_data[14]
        doc.workstation = "Machining Station"
        doc.operation = "CNC Machining"
        # doc.time_logs[0].from_time = doc.creation
        # doc.jc_planning[0].status = row_data[1]
        # doc.jc_planning[0].id = row_data[2]

        time_log = doc.append('time_logs', {})
        time_log.from_time = doc.creation

        planning = doc.append('jc_planning', {})
        planning.status = row_data[1]
        planning.name1 = row_data[2]
        planning.qty = row_data[3]
        planning.item = row_data[4]
        planning.project = row_data[5]
        planning.who = row_data[6]
        planning.created_on = row_data[7]
        planning.planned_for = row_data[8]
        planning.end_date = row_data[9]
        planning.delivered_qty = row_data[10]
        planning.material = row_data[11]
        planning.drawing = row_data[12]
        planning.program = row_data[13]
        planning.comments = row_data[14]
        
        
        # You can set additional fields here if needed
        doc.insert()

        return {
            'status': 'success',
            'message': _('Job Card created successfully.')
        }
    except Exception as e:
        return {
            'status': 'error',
            'message': str(e)
        }