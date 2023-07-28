import json
import frappe
from frappe import _

@frappe.whitelist()
def get_planning_list():
    fields = [
        'name', 'status', 'job_card', 'qty', 'item', 'project',
        'who', 'created_on', 'planned_for', 'end_date', 'delivered_qty',
        'material', 'drawing', 'program', 'comments', 'filter'
    ]
    return frappe.get_all('Planning', fields=fields)

@frappe.whitelist()
def update_planning(name, status, jobcard_name):
    doc = frappe.get_doc("Planning", name)
    doc.status = status
    doc.job_card = jobcard_name
    doc.filter = _get_filter_value(status)
    doc.save()
    print("Planning " + doc.name + " updated successfuly")

@frappe.whitelist()
def terminate_planning(data):
    print("Planning " + data + " terminated successfuly")

def _get_filter_value(status):
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
    return status_mapping.get(status, 0)

@frappe.whitelist()
def create_job_card(row_data_str):
    row_data = json.loads(row_data_str)

    planning_name = row_data[2]
    if not planning_name:
        return {
            'status': 'error',
            'message': _('Job Card Name cannot be empty.')
        }
    
    try:
        doc = _create_new_job_card(row_data)
        doc.insert()
        update_planning(planning_name, "Fab", doc.name)
        return {
            'status': 'success',
            'message': _('Job Card created successfully.')
            
        }
    except Exception as e:
        return {
            'status': 'error',
            'message': str(e)
        }

def _create_new_job_card(row_data):
    doc = frappe.new_doc('Job Card')
    doc.update({
        'work_order': "OF-00072",
        'for_quantity': row_data[3],
        'description_operation': row_data[14],
        'workstation': "Machining Station",
        'operation': "CNC Machining",
    })

    time_log = doc.append('time_logs', {})
    time_log.from_time = doc.creation

    planning = doc.append('jc_planning', {})
    planning_fields = [
        'status', 'name1', 'qty', 'item', 'project', 'who', 'created_on',
        'planned_for', 'end_date', 'delivered_qty', 'material', 'drawing',
        'program', 'comments'
    ]
    for i, field in enumerate(planning_fields, start=1):
        setattr(planning, field, row_data[i])

    return doc
