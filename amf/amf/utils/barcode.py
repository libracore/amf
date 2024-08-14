# Import necessary Frappe framework functions
import frappe
import treepoem

def generate_barcode(data):
    # Generate a barcode image
    img = treepoem.generate_barcode(
        barcode_type='pdf417',
        data=data,
    )
    # Define file path and save the image
    file_path = frappe.utils.get_files_path(f"{data}.png", is_private=True)
    img.convert('1').save(file_path)
    # Return the file path for storage in ERPNext
    return file_path

def after_insert_handler(doc, method=None):
    # Generate a barcode for the new document using its name or any unique identifier
    barcode_path = generate_barcode(doc.name)
    # Attach the barcode image to the document or store the path
    # Assuming storing the barcode file path in a custom field named 'barcode'
    doc.db_set('barcode', barcode_path)
    frappe.db.commit()

# Example usage or test function
def test_generate_barcode():
    name = "V-D-1-10-050-C-P 2024"
    barcode_path = generate_barcode(name)
    print(f"Barcode saved at: {barcode_path}")
    # Further processing can be done here if necessary
