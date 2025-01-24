import os
import re
import difflib
import frappe
import csv

# ------------------------------------------
# 1) A Single Regex & Parser
# ------------------------------------------
"""
This pattern captures:
- prefix:    3 letters (e.g. RVM)
- digits_4:  4 digits (e.g. 1259)
- dash_suffix: (optional) text like "-K" or "-C.ASM" or any dash + more
- version, revision: (optional) two digits each, preceded by a dot: .##.##
- the_rest:  anything else leftover
"""
PATTERN = re.compile(
    r"^(?P<prefix>[A-Za-z]{3})\."         # e.g. RVM.
    r"(?P<digits_4>\d{4})"               # e.g. 1259
    r"(?P<dash_suffix>(?:-[^.\s]+)?)"     # optional dash + non-dot, non-space text. e.g. -K, -C.ASM
    r"(?:\.(?P<version>\d{2})\.(?P<revision>\d{2}))?"  # optional .01.02
    r"(?P<the_rest>.*)$"                 # capture everything else if present
)

def parse_filename_or_refcode(value):
    """
    Attempts to parse strings like:
      - RVM.1259
      - RVM.1259-K
      - RVM.1259.01.01
      - RVM.1259-K.01.01
      - Possibly leftover text (the_rest)

    Returns a dict:
      {
        "prefix":      (e.g. "RVM"),
        "digits_4":    (e.g. "1259"),
        "dash_suffix": (e.g. "-K" or "-C.ASM"), possibly "",
        "version":     (e.g. "01"), possibly None,
        "revision":    (e.g. "01"), possibly None,
        "the_rest":    (e.g. ".DRW stuff"), possibly ""
      }
    or None if it doesn't match at all.
    """
    match = PATTERN.match(value.strip())
    if not match:
        return None
    return {
        "prefix": match.group("prefix"),
        "digits_4": match.group("digits_4"),
        "dash_suffix": match.group("dash_suffix") or "",
        "version": match.group("version"),
        "revision": match.group("revision"),
        "the_rest": match.group("the_rest") or ""
    }

# ------------------------------------------
# 2) Build a 'fuzzy_val' for difflib
# ------------------------------------------
def build_fuzzy_val(value):
    """
    Given a string like 'RVM.1259-K.01.01' or 'RVM.1259',
    parse it and return a 'canonical' string used for fuzzy matching.

    Example approach:
      - Always include the prefix.digits_4
      - Include dash_suffix if present
      - If you'd also like version/revision for fuzzy matching, uncomment below.
    """
    parsed = parse_filename_or_refcode(value)
    if not parsed:
        # If parsing fails, fallback to raw string
        return value

    # Base: prefix + '.' + digits_4
    base = f"{parsed['prefix']}.{parsed['digits_4']}"
    # Append dash_suffix if present
    if parsed["dash_suffix"]:
        base += parsed["dash_suffix"]  # e.g. '-K', '-C.ASM', etc.

    # If you do want version/revision in the fuzzy match, uncomment:
    # if parsed["version"] and parsed["revision"]:
    #     base += f".{parsed['version']}.{parsed['revision']}"

    return base

# ------------------------------------------
# 3) Fuzzy Matching
# ------------------------------------------
def fuzzy_match_item_code(search_str, codes_list, cutoff=0.6):
    """
    Attempt to fuzzy-match `search_str` against 'fuzzy_val' in `codes_list`.

    `codes_list` is a list of dicts of the form:
        {
          "fuzzy_val": "RVM.1259-K",
          "reference_code": "RVM.1259-K.01.01",
          "item_code": "ITEM-0001"
        }

    Returns:
      (best_reference_code, best_item_code)
    or
      (None, None) if no match.
    """
    if not codes_list or not search_str:
        return (None, None)

    possible_strings = [entry["fuzzy_val"] for entry in codes_list if entry["fuzzy_val"]]
    best_matches = difflib.get_close_matches(search_str, possible_strings, n=1, cutoff=cutoff)

    if best_matches:
        best_str = best_matches[0]
        # Identify the dict that has fuzzy_val == best_str
        for entry in codes_list:
            if entry["fuzzy_val"] == best_str:
                return (entry["reference_code"], entry["item_code"])

    return (None, None)

# ------------------------------------------
# 4) Fetch Items for Matching
# ------------------------------------------
def get_item_codes_list():
    """
    Fetch Items from DB, skip empty reference_code.
    Return a list of dicts with the fields needed for fuzzy matching:
       "fuzzy_val", "reference_code", "item_code"
    """
    all_item_docs = frappe.get_all(
        "Item",
        filters={"reference_code": ["!=", ""]},
        fields=["name", "reference_code", "item_code"]
    )

    codes_list = []
    for doc in all_item_docs:
        ref_code = doc["reference_code"]
        if not ref_code:
            continue

        fuzzy_val = build_fuzzy_val(ref_code)
        codes_list.append({
            "fuzzy_val": fuzzy_val,       # e.g. "RVM.1259-K"
            "reference_code": ref_code,   # e.g. "RVM.1259-K.01.01"
            "item_code": doc["item_code"]
        })

    return codes_list

# ------------------------------------------
# 5) Main Mapping Logic
# ------------------------------------------
def map_file_to_item(filename):
    """
    1) Parse the file's name. If we can extract a base reference_code (RVM.1259[-K]),
       we try an exact DB lookup for "Item" with that reference_code.
    2) If no direct match, fallback to fuzzy matching against "fuzzy_val."
    3) Return (best_code, item_code) or (None, None).
    """
    # 5a) Parse the filename (strip the extension if you want).
    #     For simplicity, let's parse the full filename (e.g. 'RVM.1259-K.01.01.pdf')
    #     If the extension is messing you up, you can remove it first.
    raw_name = os.path.splitext(filename)[0]  # remove '.pdf'
    parsed = parse_filename_or_refcode(raw_name)
    #print(" -> parsed:",parsed)
    if parsed:
        # Build a "base code" from the parse
        base_ref_code = f"{parsed['prefix']}.{parsed['digits_4']}"
        if parsed["dash_suffix"]:
            base_ref_code += parsed["dash_suffix"]  # e.g. '-K' or '-C.ASM'

        # Attempt direct DB match on the "base_ref_code"
        item_code = frappe.db.get_value("Item", {"reference_code": base_ref_code}, "item_code")
        if item_code:
            return base_ref_code, item_code

    # 5b) Fuzzy fallback
    codes_list = get_item_codes_list()
    # If we parsed something, use that for searching. Otherwise fallback to the entire filename.
    search_str = build_fuzzy_val(raw_name)
    best_code, item_code = fuzzy_match_item_code(search_str, codes_list, cutoff=0.6)
    if best_code and item_code:
        attach_file_to_item(filename, item_code)
    return best_code, item_code

def attach_file_to_item(pdf_filename, item_code):
    """
    Attach the PDF file to the Item record. The `item_code` should be the
    `name` of the Item document or a unique field that can fetch the doc's name.

    If your Item is named by item_code (i.e., doc.name == item_code), this is direct.
    Otherwise, you'll need to find the actual doc.name from the DB.
    """
    private_path = frappe.utils.get_site_path("private", "files", "drw", pdf_filename)

    # Optionally, verify the file actually exists:
    if not os.path.exists(private_path):
        frappe.throw(f"File {pdf_filename} does not exist in {private_path}.")

    # If your Item's `name` field == item_code, then attached_to_name can be the item_code directly.
    # If not, you might do something like:
    # item_name = frappe.db.get_value("Item", {"item_code": item_code}, "name")
    # Then attach to that name:
    item_name = item_code  

    # Create a File doc
    file_doc = frappe.get_doc({
        "doctype": "File",
        "file_name": pdf_filename,
        "attached_to_doctype": "Item",
        "attached_to_name": item_name,
        "folder": "Home/Attachments",  # or "Home/Private" if you want it in a private folder
        "is_private": 1,  # set to 1 if you want it private
    })

    # Instead of directly referencing the local filesystem path, we often set content or file_url.
    # Because your files are in /private/files/, you can do something like:
    file_doc.file_url = f"/private/files/drw/{pdf_filename}"

    # Save the File doc so it’s attached
    file_doc.save()

    frappe.db.commit()
    frappe.msgprint(
        f"Attached file '{pdf_filename}' to Item: {item_name}",
        alert=True
    )


# ------------------------------------------
# 6) Main Driver
# ------------------------------------------
@frappe.whitelist()
def main_enqueue():
    frappe.enqueue("amf.amf.utils.match_drw.main", queue='long', timeout=15000)
    return None

def main():
    """
    1) Scan a directory for .pdf files.
    2) For each file, attempt to map it to an Item (reference_code, item_code).
    3) Write results to a CSV.
    """
    private_files_path = frappe.utils.get_site_path("private", "files", "drw")
    pdf_files = [f for f in os.listdir(private_files_path) if f.lower().endswith(".pdf")]

    csv_output_path = os.path.join(private_files_path, "file_item_mapping.csv")
    with open(csv_output_path, mode="w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["Filename", "Matched Reference Code", "Item Code"])

        for pdf_file in pdf_files:
            matched_code, item_code = map_file_to_item(pdf_file)
            writer.writerow([
                pdf_file,
                matched_code if matched_code else "No Match",
                item_code if item_code else "No Match"
            ])

    frappe.msgprint(f"Mapping completed. Results stored in {csv_output_path}")
    
###############################################################################################################################################
###############################################################################################################################################
###############################################################################################################################################
###############################################################################################################################################

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