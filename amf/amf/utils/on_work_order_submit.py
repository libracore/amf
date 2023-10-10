from io import BytesIO
from amf.amf.utils.qr_code_generator import generate_qr_code
import frappe
from frappe import _
import base64
from frappe.utils.data import now_datetime
from datetime import datetime

from frappe.utils.file_manager import save_file

@frappe.whitelist()
def generate_qr(doc, method=None):
    from frappe.utils.file_manager import save_file
    from amf.amf.utils.qr_code_generator import generate_qr_code  # assuming generate_qr_code is in utils/qr_code_generator

    # get some data from the Work Order to put in the QR code
    #data = doc.name  # for example
    data = frappe.utils.get_url_to_form(doc.doctype, doc.name)

    # generate the QR code
    qr_code_str = generate_qr_code(data)

    # decode base64 string to bytes
    qr_code_bytes = base64.b64decode(qr_code_str)

    # save the QR code to a file and attach it to the Work Order
    if doc.doctype == "Work Order":
        file_data = save_file("qr_code.png", qr_code_bytes, "Work Order", doc.name, is_private=1)
    elif doc.doctype == "Job Card":
        file_data = save_file("qr_code.png", qr_code_bytes, "Job Card", doc.name, is_private=1)
    
    # Set the field to the file's URL
    doc.qr_code = file_data.file_url

    # Save the document (don't trigger events)
    #doc.save()
    #doc.reload()

@frappe.whitelist()
def generate_qr_item():
    print("generate_qr_item")
    items = frappe.get_all('Item', fields=['item_code', 'item_name', 'item_group'],
                                   filters={"item_code": ["not like", "%/%"], "disabled": 0},
                                   order_by="")
    for item in items:
        qr_code_data = generate_qr_code(item['item_code'])
        qr_code_img = base64.b64decode(qr_code_data)
        file_data = save_file("qr_code.png", qr_code_img, "Item", item.name, is_private=1)
        item['qr_code'] = file_data.file_url

def on_submit_wo(doc, method):
    # Step 1: Locate the associated Job Card
    job_card = frappe.get_all('Job Card', filters={'work_order': doc.name, 'docstatus': 0}, fields=['name'])

    if job_card:
        job_card_doc = frappe.get_doc('Job Card', job_card[0].name)
        # Set the production item in the Job Card to match the Work Order item
        job_card_doc.product_item = doc.production_item
        job_card_doc.employee = "HR-EMP-00003"
        current_time = now_datetime()
        # Step 2: Add a Row to the "time_logs" Child Table
        new_time_log = job_card_doc.append('time_logs', {
            'from_time': current_time,
            'to_time': current_time,
            'time_in_mins': 0,
            'completed_qty': job_card_doc.for_quantity
        })
        
        job_card_doc.save()
        job_card_doc.submit()

@frappe.whitelist()
def calculate_duration(doc, method=None):
    print("start calculate_duration()")
    start_date_time = doc.start_date_time
    end_date_time = doc.end_date_time

    if start_date_time and end_date_time:
        # Convert to datetime objects
        start_date = datetime.strptime(start_date_time, '%Y-%m-%d %H:%M:%S')
        end_date = datetime.strptime(end_date_time, '%Y-%m-%d %H:%M:%S')

        # Calculate the time difference in seconds
        time_difference = (end_date - start_date).total_seconds()

        # Set the calculated duration
        doc.duration = time_difference

        # Save the document
        doc.save()
        frappe.db.commit()

    return "Duration calculated"