# Import necessary Frappe framework functions
import frappe
import treepoem
import os

from frappe.utils.file_manager import save_file

def generate_barcode(data):
    # Generate a barcode image using the pdf417 barcode type
    img = treepoem.generate_barcode(
        barcode_type='pdf417',
        data=data,
    )
    # Define the file path and save the image as a PNG in the private file system
    file_path = frappe.utils.get_files_path(f"{data}.png", is_private=True)
    img.convert('1').save(file_path)

    # Strip the site path prefix to get the relative path for storing in ERPNext
    relative_path = os.path.relpath(file_path, start=frappe.utils.get_site_path())
    
    # Return the relative file path to be stored in the document
    return f"/{relative_path}"

def after_insert_handler(doc, method=None):
    # Generate a barcode for the document using its unique name or identifier
    barcode_path = generate_barcode(doc.name)

    # Prepare the file data to attach it to the document
    file_name = f"{doc.name}.png"
    file_path = frappe.utils.get_site_path(barcode_path)
    
    # with open(file_path, "rb") as filedata:
    #     img_data = filedata.read()
    
    # Use frappe's save_file to attach the barcode image to the document
    attached_file = frappe.get_doc({
        "doctype": "File",
        "file_name": file_name,
        "file_url": barcode_path,
        "attached_to_doctype": doc.doctype,
        "attached_to_name": doc.name,
        "is_private": 1
    })
    attached_file.save()

    # Save the barcode path in a custom field 'barcode' in the document
    doc.db_set('barcode', attached_file.file_url)

    # Commit the transaction to ensure the changes are saved
    frappe.db.commit()

# Example usage or test function
def test_generate_barcode():
    name = "V-D-1-10-050-C-P 2024"
    barcode_path = generate_barcode(name)
    print(f"Barcode saved at: {barcode_path}")
    # Further processing can be done here if necessary
