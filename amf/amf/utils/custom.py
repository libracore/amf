import os
from pipes import quote
import frappe
from collections import defaultdict
from frappe.utils.file_manager import save_file
from amf.amf.utils.qr_code_generator import generate_qr_code
import re
from pylibdmtx.pylibdmtx import encode
from base64 import b64encode, b64decode
from io import BytesIO
from PIL import Image

from io import BytesIO

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

@frappe.whitelist()    
def update_item_descriptions():
    # Fetch all items in the 'Valve Head' group
    test_mode = False
    items = frappe.get_list('Item', filters={'item_group': 'Valve Head', 'disabled': False}, fields=['name'])
    if test_mode: items = frappe.get_list('Item', filters={'item_code': 'V-DS-1-10-100-C-P', 'item_group': 'Valve Head'}, fields=['name'])
    for item in items:
        try:
            if test_mode: print(item)
            # Clear the description first
            frappe.db.set_value('Item', item.name, 'description', '')
            item_doc = frappe.get_doc('Item', item.name)
            
            # Building the new description from item attributes
            # Building the new description from item attributes in HTML table format
            # Building the new description from item attributes in HTML table format with styling
            new_description = """
            <table style="width: 20%; border-collapse: collapse;">
            """
            for attribute in item_doc.attributes:
                new_description += f"""
                <tr>
                    <td style="background-color: #f2f2f2;">{attribute.attribute}</td>
                    <td>{attribute.attribute_value}</td>
                </tr>
                """
            new_description += "</table>"

            # Clear and update the description
            item_doc.description = new_description
            item_doc.save()
        except frappe.exceptions.ValidationError as e:
            # Log the error for later review, including the item name that caused it
            frappe.log_error(f"Error updating item {item.name}: {str(e)}", "Item Update Error")
            continue  # Proceed with the next item

# Function to extract quantity from the item name
def extract_qty_from_item_name(item_name):
    # Find the first occurrence of a digit followed by a hyphen and another digit
    match = re.findall('-\d', item_name)
    if match:
        # Return the quantity which is the second digit in the matched pattern
        return int(match[1].replace('-', ''))
    return None

def create_new_items_and_boms():

    cancel_and_delete_boms_and_items_with_pattern()

    # Define the starting point for the new item codes
    item_code_start = {
        'Plug': 100001,
        'Valve Seat': 200001  # Starting code for Valve Seat items
    }
    
    # Fetch all items from the "Plug" and "Valve Seat" item groups
    item_groups = {
        'Plug': frappe.get_all('Item', filters={'item_group': 'Plug', 'disabled': False}, fields=['name', 'item_name']),
        'Valve Seat': frappe.get_all('Item', filters={'item_group': 'Valve Seat', 'disabled': False}, fields=['name', 'item_name'])
    }
    
    for group_name, items in item_groups.items():
        for item in items:
            # Extract the item code suffix
            item_code_suffix = extract_qty_from_item_name(item['item_name']) if group_name == 'Plug' else 2

            # Prepare the new item code and name
            new_item_code = str(item_code_start[group_name])
            new_item_name = 'P' + item['item_name'][4:] + '-ASM' if group_name == 'Plug' else 'S' + item['item_name'][4:] + '-ASM'
            suffix_code = 'SPL.3013' if group_name == 'Plug' else 'SPL.3039'

            # Create the new Item
            new_item = frappe.get_doc({
                'doctype': 'Item',
                'item_code': new_item_code,
                'item_name': new_item_name,
                'stock_uom': 'Nos',
                'is_stock_item': True,
                'include_item_in_manufacturing': True,
                'default_material_request_type': 'Manufacture',
                'description': f'{group_name} {new_item_name} Assembly w/ Components',
                'item_group': group_name,
                'item_defaults': [{
                    'company': 'Advanced Microfluidics SA',
                    'default_warehouse': 'Assemblies - AMF21'
                }],
            })
            new_item.insert(ignore_permissions=True)

            # Prepare the BOM
            new_bom = frappe.get_doc({
                'doctype': 'BOM',
                'item': new_item_code,
                'quantity': 1,
                'is_default': 1,
                'is_active': 1,
                'items': [
                    {'item_code': item['name'], 'qty': 1},
                    {'item_code': suffix_code, 'qty': item_code_suffix},
                ],
            })
            new_bom.insert(ignore_permissions=True)
            new_bom.submit()

            # Increment the item code for the next new item
            item_code_start[group_name] += 1

    # Commit the transaction
    frappe.db.commit()

def cancel_and_delete_boms_and_items_with_pattern():
    # Pattern to match a six-digit number
    pattern = "______"
    
    # Fetch all items with a six-digit item code
    items_to_delete = frappe.get_all('Item', filters={'item_code': ['like', pattern], 'item_group': ['like', 'Plug'], 'item_group': ['like', 'Valve Seat']}, fields=['name', 'item_code'], order_by='item_code asc')

    # For each item, cancel and delete associated BOMs
    for item in items_to_delete:
        associated_boms = frappe.get_all('BOM', filters={'item': item['name']}, fields=['name', 'docstatus'])
        for bom in associated_boms:
            if bom['docstatus'] == 1:  # BOM is submitted
                bom_doc = frappe.get_doc('BOM', bom['name'])
                bom_doc.cancel()
            frappe.delete_doc('BOM', bom['name'], force=1)
        
        # Once all BOMs are handled, delete the item
        frappe.delete_doc('Item', item['name'], force=1)

    frappe.db.commit()


def qrcode_serial_no_old(doc, method=None):
    data = doc.name
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
    return None

# def generate_data_matrix_old(data):
#     buffer = BytesIO()
#     # Create the Data Matrix barcode and save it to a BytesIO buffer
#     generate('datamatrix', data, output=buffer)
    
#     # Get the base64 string of the image
#     img_base64 = b64encode(buffer.getvalue()).decode('utf-8')
#     return img_base64

def generate_data_matrix(data, size='26x26'):
    # Generate a Data Matrix barcode with a specified size
    encoded = encode(data.encode(), size=size)

    # Create an image from the encoded data
    img = Image.frombytes('RGB', (encoded.width, encoded.height), encoded.pixels)

    # Save the image to a BytesIO object
    buffer = BytesIO()
    img.save(buffer, format="PNG")

    # Get the base64 string of the image
    img_base64 = b64encode(buffer.getvalue()).decode('utf-8')
    return img_base64

def qrcode_serial_no(doc, method=None):
    data = doc.name
    if doc.item_code == "522100":
        data = "BA" + data[-6:]
    print("data: ", data)
    
    # Generate the Data Matrix image as a base64 string with a higher resolution Data Matrix
    img_base64 = generate_data_matrix(data, size='26x26')

    # Decode the base64 string to binary data
    img_data = b64decode(img_base64)

    # Filename for the Data Matrix image
    file_name = f"{doc.name}_dm.png"
    
    # Create and attach the file to the document
    file_url = save_file(file_name, img_data, doc.doctype, doc.name, is_private=1).file_url
    
    # Optionally update a field in the document with the URL of the attached image
    doc.db_set('qrcode', file_url)
    return None

def generate_qr_codes_for_range(start=250, end=550):
    # Directory path to save the generated QR codes
    output_directory = '/home/libracore/frappe-bench/sites/site1.local/public/files/'
    
    # Ensure the directory exists; create it if it doesn't
    if not os.path.exists(output_directory):
        os.makedirs(output_directory)
    
    for num in range(start, end + 1):
        # Format the number to be 6 digits, e.g., 250 -> "000250"
        serial_no = f"{num:06d}"
        
        # Create the data with "BA" prefix
        data = "BA" + serial_no
        
        # Generate the QR code
        img_base64 = generate_data_matrix(data, size='26x26')
        
        # Decode the base64 string to binary data
        img_data = b64decode(img_base64)
        
        # Filename for the QR code image, following the naming convention "code_dm.png"
        file_name = f"P221-O00{serial_no}_qr.png"
        
        # Full path to save the file
        file_path = os.path.join(output_directory, file_name)
        
        # Save the file in the specified directory
        with open(file_path, "wb") as f:
            f.write(img_data)
        
        # Print the path where the file was saved (optional)
        print(f"Generated QR Code for {data}, saved as {file_path}")
