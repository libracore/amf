import re
import difflib
import frappe
import csv

def extract_item_code(filename):
    """
    Use Regex to find a substring that matches your known Item Code format.
    Adjust pattern as necessary to fit your own naming conventions.
    """
    # Example pattern: e.g. "ITM-1234" or "ITM_1234"
    pattern = r"(ITM[-_]\d+)"
    match = re.search(pattern, filename, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    return None

def fuzzy_match_item_code(filename, item_codes, cutoff=0.6):
    """
    Use difflib.get_close_matches to find the best fuzzy match over item_codes.
    'cutoff' is the similarity threshold (0 to 1). You can adjust as needed.
    """
    best_matches = difflib.get_close_matches(filename, item_codes, n=1, cutoff=cutoff)
    if best_matches:
        return best_matches[0]
    return None

def map_file_to_item(filename):
    """
    1) Try a direct regex extraction (e.g. if the filename includes something
    that looks like an Item Code).
    2) If that fails or doesn't exist in the DB, fallback to fuzzy matching
    on the entire filename vs. all Item codes.
    """
    # Step 1: Attempt Regex Extraction
    extracted_code = extract_item_code(filename)
    if extracted_code:
        # If we found a code via regex, verify it exists in ERPNext:
        if frappe.db.exists("Item", extracted_code):
            # Return the exact matched Item Code
            return extracted_code

def main():
    # Step 2: Fuzzy match on all item codes  
    all_item_codes = frappe.get_all("Item", fields=["name", "reference_code"])  
    item_codes_list = [row["reference_code"] for row in all_item_codes]  

    best_code = fuzzy_match_item_code('filename', item_codes_list, cutoff=0.6)  
    if best_code:  
        return best_code  

    # If we can't match anything reliably, return None or handle as needed  
    return None  

@frappe.whitelist()
def update_items_from_csv_enqueue():
    frappe.enqueue("amf.amf.utils.match_drw.update_items_from_csv", queue='long', timeout=15000)
    return None

def update_items_from_csv(file_path=None):
    """
    Processes a CSV file that has two columns:
    1) item_code
    2) number

    For each record:  
    - if number == 0: set 'is_sales_item' to 0  
    - if number == 2: disable (set 'disabled' = 1) the item  
    """  
    file_path = frappe.utils.get_site_path("private", "files", "action.csv")
    with open(file_path, mode='r', encoding='utf-8-sig') as csvfile:  
        reader = csv.reader(csvfile)  
        
        for row in reader:  
            # Skip empty lines or malformed rows  
            if not row or len(row) < 2:  
                continue  

            item_code, number_str = row[:2]  
            
            if not item_code or not number_str.isdigit():  
                continue  
            
            number = int(number_str)  
            
            # Attempt to fetch the Item document, handle if not found  
            try:  
                item_doc = frappe.get_doc("Item", item_code.strip())  
            except frappe.DoesNotExistError:  
                # Log an error and skip this row  
                frappe.log_error(  
                    title="Item Not Found",  
                    message=f"Item code '{item_code.strip()}' from the CSV was not found in the system."  
                )  
                continue
            # If the item is already disabled, skip  
            if item_doc.disabled:  
                frappe.log_error(  
                    title="Item Already Disabled",  
                    message=f"Skipping item '{item_code}'. It is already disabled."  
                )  
                continue  

            # Update the fields based on the number  
            if number == 0:  
                item_doc.is_sales_item = 0
            if number == 1:  
                item_doc.is_sales_item = 1
            elif number == 2:  
                item_doc.disabled = 1  

            # Attempt to save the document  
            try:  
                item_doc.save()  
            except frappe.exceptions.ValidationError as e:  
                # If the doc is disabled mid-save or any other disabled-related error, log and skip  
                if "disabled" in str(e).lower():  
                    frappe.log_error(  
                        title="Validation Error - Item Disabled",  
                        message=(  
                            f"Skipping item '{item_code}' due to disabled-related ValidationError.\n"  
                            f"Full Error: {str(e)}"  
                        )  
                    )  
                    continue  
                # If it's another type of validation error, re-raise  
                raise e  

    # Commit all changes  
    frappe.db.commit() 