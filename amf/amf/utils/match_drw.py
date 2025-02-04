import os
import re
import difflib
import frappe
import datetime
import traceback
import csv

from amf.amf.utils.utilities import (
    create_log_entry,
    update_log_entry,
    update_error_log
)

import frappe.utils  # needed for frappe.utils.get_site_path

# ------------------------------------------
# 1) Regex Pattern & Parser
# ------------------------------------------
PATTERN = re.compile(
    r"^(?P<prefix>[A-Za-z]{3})\."         # e.g. RVM.
    r"(?P<digits_4>\d{4})"               # e.g. 1259
    r"(?P<dash_suffix>(?:-[^.\s]+)?)"     # optional dash + non-dot text. e.g. -K, -C.ASM
    r"(?:\.(?P<version>\d{2})\.(?P<revision>\d{2}))?"  # optional .01.02
    r"(?P<the_rest>.*)$"                 # capture everything else if present
)


def parse_filename_or_refcode(value):
    """
    Attempt to parse strings like: RVM.1259, RVM.1259-K, RVM.1259.01.01, RVM.1259-K.01.01.

    Returns:
      dict with prefix, digits_4, dash_suffix, version, revision, the_rest
      or None if it doesn't match the pattern.
    """
    try:
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
    except Exception:
        # If there's any unexpected error, return None
        return None


# ------------------------------------------
# 2) Build 'fuzzy_val' for difflib
# ------------------------------------------
def build_fuzzy_val(value, include_version_in_fuzzy=False):
    """
    Given a string like 'RVM.1259-K.01.01' or 'RVM.1259',
    parse it and return (fuzzy_str, version, revision).

    - fuzzy_str is used for difflib fuzzy matching (e.g. "RVM.1259-K").
    - version, revision are the parsed strings (e.g. "01", "01").

    If parsing fails, returns (original_value, None, None).
    """
    try:
        parsed = parse_filename_or_refcode(value)
        if not parsed:
            return (value, None, None)

        # Build base: prefix + '.' + digits_4
        base = f"{parsed['prefix']}.{parsed['digits_4']}"

        # Append dash_suffix if present
        if parsed["dash_suffix"]:
            base += parsed["dash_suffix"]

        version = parsed["version"]
        revision = parsed["revision"]

        if include_version_in_fuzzy and version and revision:
            fuzzy_str = f"{base}.{version}.{revision}"
        else:
            fuzzy_str = base

        return (fuzzy_str, version, revision)

    except Exception:
        # On any error, fallback to the original string
        return (value, None, None)


# ------------------------------------------
# 3) Fuzzy Matching
# ------------------------------------------
def fuzzy_match_item_code(search_str, codes_list, cutoff=0.6):
    """
    Attempt to fuzzy-match `search_str` against codes_list[i]["fuzzy_val"].
    Returns (best_reference_code, best_item_code) or (None, None).
    """
    try:
        if not codes_list or not search_str:
            return (None, None)

        possible_strings = [e["fuzzy_val"] for e in codes_list if e["fuzzy_val"]]
        best_matches = difflib.get_close_matches(search_str, possible_strings, n=1, cutoff=cutoff)

        if best_matches:
            best_str = best_matches[0]
            for entry in codes_list:
                if entry["fuzzy_val"] == best_str:
                    return (entry["reference_code"], entry["item_code"])

        return (None, None)
    except Exception:
        return (None, None)


# ------------------------------------------
# 4) Fetch Items for Matching (one DB call)
# ------------------------------------------
def get_item_codes_list():
    """
    Fetch Items from DB, skip items with empty reference_code or disabled=1.
    Returns a list of dicts with:
      {
        "fuzzy_val": <string for difflib>,
        "reference_code": <code in DB>,
        "item_code": <Item Code>,
        "version": <parsed version>,
        "revision": <parsed revision>
      }
    """
    try:
        all_item_docs = frappe.get_all(
            "Item",
            filters={"reference_code": ["!=", ""], 'disabled': 0},
            fields=["name", "reference_code", "item_code"]
        )

        codes_list = []
        for doc in all_item_docs:
            ref_code = doc["reference_code"]
            if not ref_code:
                continue
            fuzzy_val, ver, rev = build_fuzzy_val(ref_code, include_version_in_fuzzy=False)
            codes_list.append({
                "fuzzy_val": fuzzy_val,
                "reference_code": ref_code,
                "item_code": doc["item_code"],
                "version": ver,
                "revision": rev
            })

        print(f"[DEBUG] get_item_codes_list: {len(codes_list)} items loaded.")
        return codes_list

    except Exception as exc:
        # Return an empty list in case of error
        print("[ERROR] get_item_codes_list:", exc)
        return []


# ------------------------------------------
# 5) Attach File to an Item
# ------------------------------------------
def attach_file_to_item(pdf_filename, item_code, version=None, revision=None, log_id=None):
    """
    Attach the PDF file to the 'drawing_item' child table of the given item_code.
    If the file is already attached with the same version/rev, do nothing.
    """
    try:
        private_path = frappe.utils.get_site_path("private", "files", pdf_filename)
        if not os.path.exists(private_path):
            msg = f"File {pdf_filename} does not exist in {private_path}."
            frappe.throw(msg)

        # Fetch parent Item doc
        item_doc = frappe.get_doc("Item", item_code)

        drawing_path = f"/private/files/{pdf_filename}"
        ref_code = item_doc.reference_code or ""
        ver = version or ""
        rev = revision or ""

        # Check if this file is already attached
        for row in item_doc.drawing_item:
            if (row.drawing == drawing_path and
                row.version == ver and
                row.revision == rev and
                row.reference_code == ref_code):
                frappe.msgprint(
                    f"File '{pdf_filename}' (v{ver}, r{rev}) is already attached to {item_code}.",
                    alert=True
                )
                return

        # Otherwise, create new row
        row = item_doc.append("drawing_item", {})
        row.drawing = drawing_path
        row.item_code = item_code
        row.reference_code = ref_code
        row.version = ver
        row.revision = rev

        # Save
        item_doc.save(ignore_permissions=True)
        frappe.db.commit()

        frappe.msgprint(
            f"Attached file '{pdf_filename}' (v{ver}, r{rev}) to Item '{item_code}'.",
            alert=True
        )

        if log_id:
            update_log_entry(log_id, f"Attached '{pdf_filename}' => Item '{item_code}' (v{ver}, r{rev}).")

    except Exception as exc:
        # Log error
        err_msg = f"[ERROR attach_file_to_item] file '{pdf_filename}' -> {item_code} failed: {str(exc)}\n"
        err_msg += traceback.format_exc()
        if log_id:
            update_log_entry(log_id, err_msg)
        update_error_log(err_msg)
        # We do not re-throw here, because we want to continue processing
        # pass


# ------------------------------------------
# 6) Mapping Logic
# ------------------------------------------
def map_file_to_item(filename, codes_list, log_id=None):
    """
    1) Parse filename => base_ref_code.
    2) Attempt direct match in codes_list.
    3) Fuzzy fallback if direct match fails.
    4) If matched, call attach_file_to_item(...).
    Returns (matched_ref_code, item_code) or (None, None).
    """
    try:
        raw_name, _ = os.path.splitext(filename)
        parsed = parse_filename_or_refcode(raw_name)

        base_ref_code = None
        item_code = None

        # Check parse
        if parsed:
            base_ref_code = f"{parsed['prefix']}.{parsed['digits_4']}"
            if parsed["dash_suffix"]:
                base_ref_code += parsed["dash_suffix"]

            # Exact match
            for entry in codes_list:
                if entry["reference_code"] == base_ref_code:
                    item_code = entry["item_code"]
                    break

            if item_code:
                attach_file_to_item(
                    pdf_filename=filename,
                    item_code=item_code,
                    version=parsed["version"],
                    revision=parsed["revision"],
                    log_id=log_id
                )
                return base_ref_code, item_code

        # Fuzzy fallback
        search_str, ver, rev = build_fuzzy_val(raw_name, include_version_in_fuzzy=False)
        (best_code, item_code) = fuzzy_match_item_code(search_str, codes_list, cutoff=0.6)
        if best_code and item_code:
            attach_file_to_item(
                pdf_filename=filename,
                item_code=item_code,
                version=ver,
                revision=rev,
                log_id=log_id
            )
            return best_code, item_code

        # If no match
        return (None, None)

    except Exception as exc:
        # Log the error, continue
        err_msg = f"[ERROR map_file_to_item] '{filename}' => {str(exc)}\n"
        err_msg += traceback.format_exc()
        if log_id:
            update_log_entry(log_id, err_msg)
        update_error_log(err_msg)
        return (None, None)


# ------------------------------------------
# 7) set_highest_rev_version_as_default
# ------------------------------------------
def set_highest_rev_version_as_default(log_id=None):
    """
    For every Item, find the row with the highest (version, revision) in drawing_item
    and set is_default=1, is_active=1. All other rows is_default=0.
    """
    try:
        all_items = frappe.get_all("Item", fields=["name"])
        for i in all_items:
            item_doc = frappe.get_doc("Item", i.name)
            if not item_doc.drawing_item:
                continue

            best_row = None
            best_ver = -1
            best_rev = -1

            for row in item_doc.drawing_item:
                ver = int(row.version or 0)
                rev = int(row.revision or 0)
                if (ver > best_ver) or (ver == best_ver and rev > best_rev):
                    best_ver = ver
                    best_rev = rev
                    best_row = row

            # Reset all
            for row in item_doc.drawing_item:
                row.is_default = 0

            if best_row:
                best_row.is_default = 1
                best_row.is_active = 1

            item_doc.save(ignore_permissions=True)

        frappe.db.commit()
        frappe.msgprint("Successfully updated 'is_default' for highest version/revision on each Item.")
        if log_id:
            update_log_entry(log_id, "set_highest_rev_version_as_default completed successfully.")

    except Exception as exc:
        err_msg = f"[ERROR set_highest_rev_version_as_default] {str(exc)}\n"
        err_msg += traceback.format_exc()
        if log_id:
            update_log_entry(log_id, err_msg)
        update_error_log(err_msg)
        # Do not re-throw, we log and move on.


# ------------------------------------------
# 8) Main Driver
# ------------------------------------------
@frappe.whitelist()
def main_enqueue():
    """Enqueues the main function on a background queue."""
    frappe.enqueue("amf.amf.utils.match_drw.main", queue='long', timeout=15000)
    return None


def main():
    """
    1) Create a single Log Entry for the process.
    2) Scan /private/files/ for PDFs.
    3) Fetch codes_list once from DB.
    4) For each file, attempt map_file_to_item => attach to item if found.
    5) Mark highest rev/version as default.
    6) Append final success or error message to the log.
    """
    # Create a new log entry for this run
    log_id = create_log_entry(
        message="Starting PDF: Item mapping...",
        category="File Mapping"
    )

    try:
        private_files_path = frappe.utils.get_site_path("private", "files")
        pdf_files = [f for f in os.listdir(private_files_path) if f.lower().endswith(".pdf")]
        update_log_entry(log_id, f"Found {len(pdf_files)} PDF files in {private_files_path}.\n")

        # 1) Codes list
        codes_list = get_item_codes_list()

        # 2) Process each PDF
        for pdf_file in pdf_files:
            matched_code, item_code = map_file_to_item(pdf_file, codes_list, log_id=log_id)

            line_msg = (f"File: '{pdf_file}' "
                        f"Matched RefCode: {matched_code if matched_code else 'No Match'}, "
                        f"Item: {item_code if item_code else 'No Match'}")
            update_log_entry(log_id, line_msg)

        # 3) Post-processing: set default
        set_highest_rev_version_as_default(log_id=log_id)

        # 4) Final success message
        update_log_entry(log_id, "PDF: Item Mapping completed successfully.")
        frappe.msgprint(f"Mapping completed. See Log Entry '{log_id}' for details.")

    except Exception as exc:
        # If something bigger fails in the main loop
        err_msg = f"[ERROR main] {str(exc)}\nTraceback:\n{traceback.format_exc()}"
        update_log_entry(log_id, err_msg)
        update_error_log(err_msg)
        frappe.throw(err_msg)
    
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

@frappe.whitelist()
def execute_db_drw_enqueue():
    frappe.enqueue("amf.amf.utils.match_drw.remove_drw", queue='long', timeout=15000)
    return None
  
def remove_drw():
    """
    Clears the drawing_item child table for all Items,
    except those belonging to the 'Plug' or 'Valve Seat' item groups.
    """
    try:
        # 1. Retrieve names of items not in the specified groups
        #    Note: If your field is named differently, adjust the filters accordingly.
        # List all prefixes to exclude
        excluded_prefixes = ["EXS.", "BAC.", "BFV.", "DBM.", "FLU.", "HEX.", 
                            "ILP.", "NAG.", "OPT.", "OUT.", "PAC.", "THF."]
        
        # Build filters
        # Note that each filter is a condition of the form:
        # [fieldname, operator, value]
        # or [doctype, fieldname, operator, value]
        filters = [
            ["item_group", "not in", ["Plug", "Valve Seat"]],
            ["disabled", "=", 0],
        ]
        
        # Append "not like" filters for each prefix
        for prefix in excluded_prefixes:
            filters.append(["item_code", "not like", f"{prefix}%"])

        item_names = frappe.get_list(
            "Item",
            filters=filters,
            fields=['name']  # Only return the 'name' field
        )
        
        # 2. Iterate over each Item
        for item_name in item_names:
            item_doc = frappe.get_doc("Item", item_name)
            
            # 3. Clear the drawing_item child table.
            #    If your child table field name differs, use the correct field name instead.
            if item_doc.drawing_item:
                item_doc.drawing_item = []
            # 4. Save changes. If permissions are restrictive, consider ignore_permissions=True
            try:
                item_doc.save(ignore_permissions=True)
                frappe.db.commit()
            except frappe.ValidationError as ee:
                frappe.log_error(
                    title=f"Drawing Error: {str(ee)}",
                    message=frappe.get_traceback()
                )

    except frappe.DoesNotExistError as dne:
        # Handles the case if "Item" DocType or certain records unexpectedly don't exist
        frappe.log_error(
            message=f"Record not found error: {str(dne)}",
            title="Clearing Drawing Items - DoesNotExistError"
        )
        # Raise, handle, or pass based on desired behavior.
        raise
    
    except Exception as e:
        # Catches any other exceptions that may occur
        frappe.log_error(
            message=f"An error occurred while clearing drawing items: {str(e)}",
            title="Clearing Drawing Items - Exception"
        )
        # Re-raise the exception or handle it gracefully here
        raise
    
    except frappe.ValidationError as ee:
        # If any step failed, roll back to the savepoint
        #frappe.db.rollback(save_point="before_bom_refactor")
        frappe.log_error(
            title=f"Drawing Error: {str(ee)}",
            message=frappe.get_traceback()
        )
        # Move to the next BOM
        raise    
    
    return None