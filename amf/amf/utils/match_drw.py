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
- prefix:       3 letters (e.g. RVM)
- digits_4:     4 digits (e.g. 1259)
- dash_suffix:  (optional) text like "-K" or "-C.ASM" or any dash + more
- version, revision: (optional) two digits each, preceded by .##.##
- the_rest:     anything else leftover
"""
PATTERN = re.compile(
    r"^(?P<prefix>[A-Za-z]{3})\."         # e.g. RVM.
    r"(?P<digits_4>\d{4})"               # e.g. 1259
    r"(?P<dash_suffix>(?:-[^.\s]+)?)"     # optional dash + non-dot text. e.g. -K, -C.ASM
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

    Returns a dict or None if no match:
      {
        "prefix": "RVM",
        "digits_4": "1259",
        "dash_suffix": "-K" (or ""),
        "version": "01" (or None),
        "revision": "01" (or None),
        "the_rest": ".whatever" (or "")
      }
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
def build_fuzzy_val(value, include_version_in_fuzzy=False):
    """
    Given a string like 'RVM.1259-K.01.01' or 'RVM.1259',
    parse it and return a tuple: (fuzzy_str, version, revision).

    1) fuzzy_str is the canonical string used for fuzzy matching:
         - "RVM.1259" + optional dash_suffix
         - Optionally append ".<version>.<revision>" if `include_version_in_fuzzy=True`.
    2) version, revision are separate strings (or None) for later usage.

    Example:
      "RVM.1259-K.01.01" -> ("RVM.1259-K.01.01", "01", "01")
      if `include_version_in_fuzzy=False` -> ("RVM.1259-K", "01", "01")
    """
    parsed = parse_filename_or_refcode(value)
    if not parsed:
        # If parsing fails, fallback: no version/revision, fuzzy_str = original
        return (value, None, None)

    # Base: prefix + '.' + digits_4
    base = f"{parsed['prefix']}.{parsed['digits_4']}"
    # Append dash_suffix if present
    if parsed["dash_suffix"]:
        base += parsed["dash_suffix"]  # e.g. '-K'

    version = parsed["version"]
    revision = parsed["revision"]

    # If you want to incorporate version/revision in the fuzzy match, do so here:
    if include_version_in_fuzzy and version and revision:
        fuzzy_str = f"{base}.{version}.{revision}"
    else:
        fuzzy_str = base

    return (fuzzy_str, version, revision)


# ------------------------------------------
# 3) Fuzzy Matching
# ------------------------------------------
def fuzzy_match_item_code(search_str, codes_list, cutoff=0.6):
    """
    Attempt to fuzzy-match `search_str` (a string) against
    `codes_list[i]["fuzzy_val"]` (all strings).

    `codes_list` is a list of dicts, e.g.:
        {
          "fuzzy_val": "RVM.1259-K",
          "reference_code": "RVM.1259-K.01.01",
          "item_code": "ITEM-0001",
          "version": "01" or None,
          "revision": "01" or None
        }

    Returns (best_reference_code, best_item_code) or (None, None).
    """
    if not codes_list or not search_str:
        return (None, None)

    # Build a list of the fuzzy_val strings
    possible_strings = [entry["fuzzy_val"] for entry in codes_list if entry["fuzzy_val"]]
    best_matches = difflib.get_close_matches(search_str, possible_strings, n=1, cutoff=cutoff)

    if best_matches:
        best_str = best_matches[0]
        # Identify which dict matched
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
       {
         "fuzzy_val": <string for difflib>,
         "reference_code": <actual code in DB>,
         "item_code": <Item Code>,
         "version": <parsed version or None>,
         "revision": <parsed revision or None>
       }
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

        # Here, we parse the reference_code to get a fuzzy_val + version/revision
        fuzzy_val, ver, rev = build_fuzzy_val(ref_code, include_version_in_fuzzy=False)
        codes_list.append({
            "fuzzy_val": fuzzy_val,        # e.g. "RVM.1259-K"
            "reference_code": ref_code,    # e.g. "RVM.1259-K.01.01"
            "item_code": doc["item_code"],
            "version": ver,
            "revision": rev
        })

    return codes_list


# ------------------------------------------
# 5) Main Mapping Logic
# ------------------------------------------
def map_file_to_item(filename):
    """
    1) Parse the filename (without extension) to build a base_ref_code (RVM.1259[-K]).
    2) Attempt direct DB lookup on that base code in "Item.reference_code".
    3) If not found, fallback to fuzzy matching.
    4) If a match is found, attach the PDF to the child table "drawing_item".
    5) Return (best_code, item_code) or (None, None).
    """
    raw_name, _ = os.path.splitext(filename)  # remove '.pdf' if present
    parsed = parse_filename_or_refcode(raw_name)

    # Attempt direct match
    if parsed:
        base_ref_code = f"{parsed['prefix']}.{parsed['digits_4']}"
        if parsed["dash_suffix"]:
            base_ref_code += parsed["dash_suffix"]  # e.g. -K, -C.ASM

        # Direct DB check
        item_code = frappe.db.get_value("Item", {"reference_code": base_ref_code}, "item_code")
        if item_code:
            # Attach the PDF to the child table. Pass version/revision if you want:
            attach_file_to_item(
                pdf_filename=filename,
                item_code=item_code,
                version=parsed["version"],
                revision=parsed["revision"],
            )
            return base_ref_code, item_code

    # Otherwise, fuzzy fallback
    codes_list = get_item_codes_list()
    # Build fuzzy_val from the filename
    search_str, ver, rev = build_fuzzy_val(raw_name, include_version_in_fuzzy=False)
    best_code, item_code = fuzzy_match_item_code(search_str, codes_list, cutoff=0.6)

    if best_code and item_code:
        attach_file_to_item(
            pdf_filename=filename,
            item_code=item_code,
            version=ver,
            revision=rev,
        )

    return best_code, item_code


def attach_file_to_item(pdf_filename, item_code, version=None, revision=None):
    """
    Attach the PDF file to the Item record by creating a row in the 'drawing_item' child table.
    Child table fields:
      - drawing (Attach)
      - item_code (Data)
      - reference_code (Data)
      - version (Data)
      - revision (Data)

    item_code is assumed to be the docname for the parent Item. If not, adjust the lookup.
    """
    private_path = frappe.utils.get_site_path("private", "files", pdf_filename)

    if not os.path.exists(private_path):
        frappe.throw(f"File {pdf_filename} does not exist in {private_path}.")

    # Fetch the parent Item doc
    item_doc = frappe.get_doc("Item", item_code)

    # Build the fields we want to compare
    drawing_path = f"/private/files/drw/{pdf_filename}"
    ref_code = item_doc.reference_code or ""
    ver = version or ""
    rev = revision or ""

    # ----------------------------------------
    # 1) Check if the same row already exists
    # ----------------------------------------
    already_exists = False
    for row in item_doc.drawing_item:
        if (row.drawing == drawing_path 
            and row.version == ver 
            and row.revision == rev 
            and row.reference_code == ref_code):
            already_exists = True
            break

    if already_exists:
        frappe.msgprint(
            f"This file '{pdf_filename}' (v{ver}, r{rev}) "
            f"is already attached to Item '{item_code}' with the same reference code.",
            alert=True
        )
        return

    # ----------------------------------------
    # 2) If no exact match, create a new row
    # ----------------------------------------
    row = item_doc.append("drawing_item", {})
    row.drawing = drawing_path
    row.item_code = item_code
    row.reference_code = ref_code
    row.version = ver
    row.revision = rev

    # Save and commit
    item_doc.save(ignore_permissions=True)
    frappe.db.commit()

    frappe.msgprint(
        f"Attached file '{pdf_filename}' (v{ver}, r{rev}) to "
        f"Item '{item_code}' in child table 'Drawing Item'.",
        alert=True
    )
    
def set_highest_rev_version_as_default():
    """
    For every Item in the system, find the drawing_item row
    with the highest (version,revision) and set 'is_default' = 1 on that row.
    All other rows get 'is_default' = 0.
    """
    all_items = frappe.get_all("Item", fields=["name"])
    for i in all_items:
        item_doc = frappe.get_doc("Item", i.name)
        if not item_doc.drawing_item:
            continue  # no child rows at all

        # 1) Find the row with the highest (version,revision)
        best_row = None
        best_ver = -1
        best_rev = -1

        for row in item_doc.drawing_item:
            # Safely convert version/revision to integers (fallback = 0 if blank)
            ver = int(row.version or 0)
            rev = int(row.revision or 0)

            if (ver > best_ver) or (ver == best_ver and rev > best_rev):
                best_ver = ver
                best_rev = rev
                best_row = row

        # 2) Set 'is_default' = 0 for all rows
        for row in item_doc.drawing_item:
            row.is_default = 0

        # 3) Mark the best row as default
        if best_row:
            best_row.is_default = 1
            best_row.is_active = 1

        # 4) Save changes
        item_doc.save(ignore_permissions=True)

    # Finally commit all changes
    frappe.db.commit()

    frappe.msgprint("Successfully updated is_default for the highest version/revision in each Item.")


# ------------------------------------------
# 6) Main Driver
# ------------------------------------------
@frappe.whitelist()
def main_enqueue():
    """Enqueues the main function on a long queue."""
    frappe.enqueue("amf.amf.utils.match_drw.main", queue='long', timeout=15000)
    return None

def main():
    """
    1) Scan the /private/files/drw directory for .pdf files.
    2) For each file, attempt to map it to an Item.
    3) Write results to a CSV for review.
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
    set_highest_rev_version_as_default()
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