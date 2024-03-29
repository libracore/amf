from pipes import quote
import frappe
from collections import defaultdict
from frappe.utils.file_manager import save_file
from base64 import b64decode
from amf.amf.utils.qr_code_generator import generate_qr_code

@frappe.whitelist()
def get_latest_serial_no(so_detail, sales_order, item_code):
    serial_no = frappe.db.sql("""
        SELECT 
            soi.name AS sales_order_item, 
            (SELECT sed.serial_no 
            FROM `tabStock Entry` AS se 
            JOIN `tabStock Entry Detail` AS sed ON se.name = sed.parent
            WHERE sed.item_code = soi.item_code AND se.docstatus = 1
            AND se.work_order = (
                SELECT wo.name 
                FROM `tabWork Order` AS wo 
                WHERE wo.sales_order_item = %s 
                AND wo.status = 'Completed'
                LIMIT 1
            )
            LIMIT 1
        ) AS serial_no
        FROM `tabSales Order` AS so 
        JOIN `tabSales Order Item` AS soi ON soi.parent = so.name
        WHERE so.name = %s AND soi.item_code = %s
    """, (so_detail, sales_order, item_code), as_dict=1)
    return serial_no[0]['serial_no'] if serial_no else None

@frappe.whitelist()
def get_latest_serial_no_new(so_detail, sales_order, item_code):
    try:
        serial_nos = frappe.db.sql("""
            SELECT 
                soi.name AS sales_order_item,
                sed.serial_no AS serial_no
            FROM `tabSales Order` AS so 
            JOIN `tabSales Order Item` AS soi ON soi.parent = so.name
            JOIN `tabWork Order` AS wo ON wo.sales_order_item = soi.name
            JOIN `tabStock Entry` AS se ON se.work_order = wo.name
            JOIN `tabStock Entry Detail` AS sed ON se.name = sed.parent
            JOIN `tabSerial No` AS srl ON se.name = srl.purchase_document_no
            WHERE 
                so.name = %s AND soi.item_code = %s AND soi.name = %s AND wo.status = 'Completed' AND se.docstatus = 1 AND sed.serial_no IS NOT NULL AND srl.warehouse IS NOT NULL
            GROUP BY sed.serial_no
        """, (sales_order, item_code, so_detail), as_dict=1)

        if serial_nos:
            # Initialize a dictionary to group serial numbers by sales_order_item
            grouped_serial_nos = defaultdict(list)
            
            # Populate the dictionary
            for entry in serial_nos:
                grouped_serial_nos[entry['sales_order_item']].append(entry['serial_no'])
            # Convert the lists of serial numbers to strings joined by '\n'
            for sales_order_item, serial_list in grouped_serial_nos.items():
                grouped_serial_nos[sales_order_item] = "\n".join(serial_list)
            print(grouped_serial_nos)
            # Return the dictionary, or further process as needed
            return grouped_serial_nos
        
        return None
    except Exception as e:
        frappe.log_error(message=f"An error occurred: {e}", title="Get Latest Serial Number Error")
        return None

    #     if serial_nos:
    #         print(serial_nos)
    #         # Collecting all serial numbers
    #         all_serial_nos = [entry['serial_no'] for entry in serial_nos]
    #         print("\n".join(all_serial_nos))
    #         # You can return them as a list or join them into a string
    #         return "\n".join(all_serial_nos)
        
    #     return None
    # except Exception as e:
    #     frappe.log_error(message=f"An error occurred: {e}", title="Get Latest Serial Number Error")
    #     return None


def attach_qr_code_to_document(doc, method):
    # Example data to encode in the QR code - customize as needed
    data = frappe.utils.get_url_to_form(doc.doctype, doc.name)
    print("data: ", data)
    # Generate the QR code image as a base64 string
    img_base64 = generate_qr_code(data)

    # Decode the base64 string to binary data
    img_data = b64decode(img_base64)

    # Filename for the QR code image
    file_name = f"{doc.name}_qr.png"
    
    # Create and attach the file to the document
    file_url = save_file(file_name, img_data, doc.doctype, doc.name, is_private=1).file_url
    
    # Optionally update a field in the document with the URL of the attached image
    doc.db_set('qrcode', file_url)

@frappe.whitelist()
def qr_code_to_document(doc, method=None):
    # Form the URL as specified
    data = frappe.utils.get_url_to_form(doc.doctype, doc.name)
    print("data: ", data)
    
    # Generate the QR code image as a base64 string
    img_base64 = generate_qr_code(data)
    
    # Decode the base64 string to binary data
    img_data = b64decode(img_base64)

    # Filename for the QR code image
    file_name = f"{doc.name}_qr.png"
    
    # Create and attach the file to the document
    file_url = save_file(file_name, img_data, doc.doctype, doc.name, is_private=1).file_url
    print("file_url: ", file_url)
    # Optionally update a field in the document with the URL of the attached image
    doc.db_set('qrcode', file_url)

@frappe.whitelist()
def generate_qr_for_submitted(doctype=None):
    if doctype:
        doc_types = [doctype]
    else:
        doc_types = ['Work Order', 'Job Card', 'Stock Entry']
    print("doctype:", doc_types)

    for doc_type in doc_types:
        # Fetch all submitted documents of the current DocType
        documents = frappe.get_list(doc_type, filters={'docstatus': 1}, fields=['name'])
        
        for doc in documents:
            # Fetch the document object
            doc_obj = frappe.get_doc(doc_type, doc['name'])
            
            # Assuming qr_code_to_document is properly defined and imported
            try:
                qr_code_to_document(doc_obj)
                frappe.db.commit()  # Commit changes after each document to ensure data is saved
            except Exception as e:
                # Log errors without stopping the entire operation
                frappe.log_error(f"Failed to generate QR for {doc_type} {doc['name']}: {e}", "QR Code Generation Error")

@frappe.whitelist()
def set_all_standard_fields(doctype, standard_field, new_custom_field):
    test_mode = None
    """
    Update the 'standard_field' of all documents of a given 'doc_type' 
    with the value provided in 'new_custom_field_value'.
    
    :param doc_type: The DocType to update.
    :param standard_field: The name of the standard field to update.
    :param new_custom_field_value: The value to set for the standard field.
    """
    # Ensure the DocType and field names are provided
    if not doctype or not standard_field:
        return 'DocType and standard field names are required.'
    
    try:
        # Fetch all documents of the specified DocType
        documents = frappe.get_all(doctype, fields=['name'])
        if test_mode:
            print(doctype)
            print(new_custom_field)
            print(standard_field)
        
        for doc in documents:
            # Fetch the document
            document = frappe.get_doc(doctype, doc['name'])
            new_value = getattr(document, new_custom_field, None)
            # Update the standard field with the new custom field value
            if test_mode:
                print(getattr(document, standard_field, 'Field not found'))
            elif test_mode is None:
                setattr(document, standard_field, new_value)
                if doctype == 'Issue':
                    if not document.impact:
                        setattr(document, 'impact', '-')
                    if not document.urgency:
                        setattr(document, 'urgency', '-')
                    if not document.input_selection:
                        setattr(document, 'input_selection', '-')
                    if not document.issue_type:
                        setattr(document, 'issue_type', '-')
                document.save()
        if not test_mode:
            # Commit the changes to the database
            frappe.db.commit()

        return f'Successfully updated {len(documents)} documents.'
    except Exception as e:
        # Log detailed error information
        error_message = f'Error updating documents: {str(e)}'
        frappe.log_error(error_message, 'set_all_standard_fields')
        return error_message  # Provide more detailed feedback to the caller.