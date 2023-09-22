import datetime
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

# @frappe.whitelist()
# def update_planning(name, status, jobcard_name=None):
#     doc = frappe.get_doc("Planning", name)
#     doc.status = status
#     doc.set('status', status)
#     if(jobcard_name):
#         doc.job_card = jobcard_name
#     doc.set('filter', _get_filter_value(status))
#     doc.save()
#     print("Planning " + doc.name + " updated successfuly.")
"""  
1-Name
2-Status
3-Job Card
4-Quantity
5-Item
6-Company
7-Who
8-Creation Date
9-Planned For
10-Start Date
11-End Date
12-Delivered Qty
13-Material
14-Drawing
15-Program
16-Comments
"""
@frappe.whitelist()
def update_planning_(name, status=None, jobcard=None, qty=None, item=None, company=None, resp=None, creation=None, plan_for=None,
                     start=None, end=None, end_qty=None, mat=None, drw=None, prog=None, comments=None):
    print("Loading Planning DocType Name:",name)
    doc = frappe.get_doc("Planning", name)
    if(status):
        print("Change in 'Status' detected.")
        doc.set('status', status)
    if(jobcard):
        print("Change in 'Job Card' detected.")
        doc.set('job_card', jobcard)
    if(qty):
        print("Change in 'Quantity' detected.")
        doc.set('qty', qty)
    if(item):
        print("Change in 'Item' detected.")
        doc.set('item', item)
    if(company):
        print("Change in 'Company' detected.")
        doc.set('project', company)
    if(resp):
        print("Change in 'Who' detected.")
        doc.set('who', resp)
    if(creation):
        print("Change in 'Creation' detected.")
        doc.set('created_on', creation)
    if(plan_for):
        print("Change in 'Planned For' detected.")
        doc.set('planned_for', plan_for)
    if(start):
        print("Change in 'Start Date' detected.")
        doc.set('start_date', start)
    if(end):
        print("Change in 'End Date' detected.")
        doc.set('end_date', end)
    if(end_qty):
        print("Change in 'Delivered Quantity' detected.")
        doc.set('delivered_qty', end_qty)
    if(mat):
        print("Change in 'Material' detected.")
        doc.set('material', mat)
    if(drw):
        print("Change in 'Drawing' detected.")
        doc.set('drawing', drw)
    if(prog):
        print("Change in 'Program' detected.")
        doc.set('program', prog)
    if(comments):
        print("Change in 'Comments' detected.")
        doc.set('comments', comments)
    doc.set('filter', _get_filter_value(status))
    doc.save()
    print("Planning " + doc.name + " updated successfuly.")

@frappe.whitelist()
def terminate_planning(name, delivery_qty):
    return _terminate_job_card(name, delivery_qty)
    # update_planning_(name, 'QC', None,  None, None, None, None, None, None, None, datetime.datetime.now())
    # print("Planning " + name + " terminated successfuly.")

@frappe.whitelist()
def start_planning(name):
    return _create_job_card(name)
    # update_planning_(name, 'Fab', None,  None, None, None, None, None, None, datetime.datetime.now())
    # print("Planning " + name + " started successfuly.")

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

def _create_job_card(planning_name):
    doc = frappe.get_doc("Planning", planning_name)
    print("Planning Job Card:", doc.job_card)
    if doc.job_card:
        print("Planning Job Card detected.")
        return {
            'status': 'error',
            'message': _('Job Card already exists: {0}').format(doc.job_card)
        }
    
    try:
        jobcard = _create_new_job_card(doc)
        print(jobcard.name)
        update_planning_(planning_name, 'Fab', jobcard.name,  None, None, None, None, None, None, datetime.datetime.now())
        return {
            'status': 'success',
            'message': _('Job Card created successfully: {0}').format(jobcard.name)
        }
    except Exception as e:
        return {
            'status': 'error',
            'message': str(e)
        }

""" @frappe.whitelist()
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
        update_planning_(planning_name, "Fab", doc.name)
        return {
            'status': 'success',
            'message': _('Job Card created successfully.')
            
        }
    except Exception as e:
        return {
            'status': 'error',
            'message': str(e)
        }
 """

def _create_new_job_card(planning):
    print("Creating New Job Card.")
    jobcard = frappe.new_doc('Job Card')
    jobcard.update({
        'work_order': "OF-00072",
        'for_quantity': planning.qty,
        'description_operation': planning.comments,
        #'product_item': planning.item,
        'workstation': "Machining Station",
        'operation': "CNC Machining",
        'planning_name': planning.name
    })
    time_log = jobcard.append('time_logs', {})
    time_log.from_time = datetime.datetime.now()
    jobcard.insert()
    return jobcard
# item marche pas (détection auto à coder)
# assign jobcard.name to planning.jobcard

def _terminate_job_card(planning_name, qty):
    print("Terminating Job Card.")
    planning_doc = frappe.get_doc("Planning", planning_name)
    jobcard_doc = frappe.get_doc("Job Card", planning_doc.job_card)
    update_planning_(planning_name, 'QC', None,  None, None, None, None, None, None, None, datetime.datetime.now(), qty)
    if jobcard_doc.time_logs:  # check if the child table has at least one row
        row = jobcard_doc.time_logs[0]  # accessing the first row
        row.to_time = datetime.datetime.now()  # replace 'fieldname' with the actual field name you want to update and 'new_value' with the new value
        row.completed_qty = float(planning_doc.delivered_qty)
    # Save the parent document to persist changes
    jobcard_doc.save()
    return {
            'status': 'success',
            'message': _('Job Card terminated successfully: {0}').format(jobcard_doc.name)
        }