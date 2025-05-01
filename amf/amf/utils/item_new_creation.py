# import os
# import csv
# import frappe
# from frappe import _
# from itertools import chain
# from frappe.utils.file_manager import get_file_path


# def import_items_from_csv(file_url="/private/files/auto_creation.csv"):
#     """
#     Reads a CSV from Private/Public files (via File Doc or path),
#     logs debug info, and creates new Item records.
#     :param file_url: e.g. '/private/files/auto_creation.csv'
#     :return: {'inserted': [...], 'skipped': [...]}
#     """
#     # 1) Try to resolve via the File Doc
#     try:
#         file_doc = frappe.get_doc("File", {"file_url": file_url})
#         file_path = file_doc.get_full_path()
#     except frappe.DoesNotExistError:
#         # fallback to site path resolver
#         try:
#             file_path = get_file_path(file_url)
#         except Exception as e:
#             frappe.throw(
#                 _("Could not resolve file URL {0}: {1}").format(file_url, e))

#     # 2) Log which path we're actually opening
#     frappe.log_error(message=_("Resolved CSV path: {0}").format(file_path),
#                      title="import_items_from_csv [DEBUG]")

#     if not os.path.exists(file_path):
#         frappe.throw(_("File not found at: {0}").format(file_path))

#     # 3) Read reader contents for debugging
#     with open(file_path, 'r', encoding='utf-8') as f:
#         reader = csv.reader(f)

#         # --- 1) Pull off the first row to inspect it ---
#         try:
#             first_row = next(reader)
#         except StopIteration:
#             frappe.throw(_("The CSV file is empty: {0}").format(file_path))

#         # --- 2) Detect header ---
#         header = [cell.strip().lower() for cell in first_row]
#         expected = ["item_group", "item_code", "item_name", "item_type", "reference_code", "valve_head", "plug", "seat", "raw_mat"]
#         has_header = (header == expected)

#         if has_header:
#             frappe.log_error(message="Detected header, skipping row 1",
#                              title="import_items_from_csv [DEBUG]")
#             data_rows = reader               # start with the 2nd line
#             start_idx = 2
#         else:
#             frappe.log_error(message="No header, including first row as data",
#                              title="import_items_from_csv [DEBUG]")
#             data_rows = chain([first_row], reader)   # put first_row back
#             start_idx = 1

#         # --- 3) Process rows ---
#         inserted, skipped = [], []
#         for idx, row in enumerate(data_rows, start=start_idx):
#             item_group, item_code, item_name, item_type, reference_code, valve_head, plug, seat, raw_mat = [c.strip() for c in row]
#             print(item_code)
#             if not item_code:
#                 frappe.log_error(
#                     message=_("Row {0} has empty Item Code").format(idx),
#                     title="import_items_from_csv"
#                 )
#                 continue

#             if frappe.db.exists("Item", item_code):
#                 skipped.append(item_code)
#                 continue
            
#             doc = frappe.get_doc({
#                 "doctype": "Item",
#                 "item_group":     item_group,
#                 "item_code":      item_code,
#                 "item_name":      item_name,
#                 "item_type":      item_type,
#                 "reference_code": reference_code,
#             })
#             try:
#                 doc.insert(ignore_permissions=True)
#                 frappe.db.commit()
#                 inserted.append(item_code)
#             except Exception as e:
#                 print(e,"Failed to insert Item {0}".format(item_code))
#                 frappe.log_error(
#                     message=frappe.get_traceback(),
#                     title=_("Failed to insert Item {0}").format(item_code)
#                 )
                
#             if item_code.startswith('20'):
#                 # 6) Build the BOM
#                 bom = frappe.get_doc({
#                     "doctype":    "BOM",
#                     "item":       item_code,
#                     "quantity":   1,
#                     "is_default": 1,
#                     "items": [
#                         {
#                             "item_code": seat,
#                             "qty":       1,
#                             "uom":       "Nos"
#                         }
#                     ]
#                 })
#                 try:
#                     bom.insert(ignore_permissions=True)
#                     bom.submit()
#                     frappe.db.commit()
#                 except Exception as e:
#                     frappe.log_error(frappe.get_traceback(),
#                                     _("Failed to create BOM for {0}").format(item_code))
#                     print(e)
#                     skipped.append((item_code, "insert error"))
                
#             if item_code.startswith('21'):
#                 bom = frappe.get_doc({
#                     "doctype":    "BOM",
#                     "item":       item_code,
#                     "quantity":   1,
#                     "is_default": 1,
#                     "items": [
#                         {
#                             "item_code": seat,
#                             "qty":       1,
#                             "uom":       "Nos"
#                         },
#                         {
#                             "item_code": "SPL.3039",
#                             "qty":       2,
#                             "uom":       "Nos"
#                         }
#                     ]
#                 })
#                 try:
#                     bom.insert(ignore_permissions=True)
#                     bom.submit()
#                     frappe.db.commit()
#                 except Exception as e:
#                     frappe.log_error(frappe.get_traceback(),
#                                     _("Failed to create BOM for {0}").format(item_code))
#                     print(e)
#                     skipped.append((item_code, "insert error"))
                
#             if item_code.startswith('3'):
#                 if plug and seat:
#                     bom = frappe.get_doc({
#                         "doctype":    "BOM",
#                         "item":       item_code,
#                         "quantity":   1,
#                         "is_default": 1,
#                         "items": [
#                             {
#                                 "item_code": seat,
#                                 "qty":       1,
#                                 "uom":       "Nos"
#                             },
#                             {
#                                 "item_code": plug,
#                                 "qty":       1,
#                                 "uom":       "Nos"
#                             }
#                         ]
#                     })
#                     try:
#                         bom.insert(ignore_permissions=True)
#                         bom.submit()
#                         frappe.db.commit()
#                     except Exception as e:
#                         frappe.log_error(frappe.get_traceback(),
#                                         _("Failed to create BOM for {0}").format(item_code))
#                         print(e)
#                         skipped.append((item_code, "insert error"))
#                 elif seat:
#                     bom = frappe.get_doc({
#                         "doctype":    "BOM",
#                         "item":       item_code,
#                         "quantity":   1,
#                         "is_default": 1,
#                         "items": [
#                             {
#                                 "item_code": seat,
#                                 "qty":       1,
#                                 "uom":       "Nos"
#                             }
#                         ]
#                     })
#                     try:
#                         bom.insert(ignore_permissions=True)
#                         bom.submit()
#                         frappe.db.commit()
#                     except Exception as e:
#                         frappe.log_error(frappe.get_traceback(),
#                                         _("Failed to create BOM for {0}").format(item_code))
#                         print(e)
#                         skipped.append((item_code, "insert error"))
            
#             if item_code.startswith('4'):
#                 # pull out the digits
#                 second_digit = item_code[1]
#                 third_digit  = item_code[2]
#                  # 4) Fetch the Body component
#                 body_code = frappe.db.sql_list("""
#                     SELECT name FROM `tabItem`
#                     WHERE item_group=%s
#                     AND SUBSTR(name,2,1)=%s
#                     AND SUBSTR(name,3,1)='1'
#                 """, ("Body", second_digit))

#                 # 5) Fetch the Syringe component
#                 syringe_code = frappe.db.sql_list("""
#                     SELECT name FROM `tabItem`
#                     WHERE item_group=%s
#                     AND SUBSTR(name,3,1)=%s
#                 """, ("Syringe", third_digit))
#                 print(body_code, syringe_code)
#                 # must find exactly one of each
#                 if len(body_code)!=1 or len(syringe_code)!=1:
#                     skipped.append((item_code,
#                                     f"Body found={body_code}, Syringe found={syringe_code}"))
#                     continue
#                 # 6) Build the BOM
#                 bom = frappe.get_doc({
#                     "doctype":    "BOM",
#                     "item":       item_code,
#                     "quantity":   1,
#                     "is_default": 1,
#                     "items": [
#                         {
#                             "item_code": body_code[0],
#                             "qty":       1,
#                             "uom":       "Nos"
#                         },
#                         {
#                             "item_code": syringe_code[0],
#                             "qty":       1,
#                             "uom":       "Nos"
#                         },
#                         {
#                             "item_code": valve_head,
#                             "qty":       1,
#                             "uom":       "Nos"
#                         },
#                     ]
#                 })
#                 try:
#                     bom.insert(ignore_permissions=True)
#                     bom.submit()
#                     frappe.db.commit()
#                 except Exception as e:
#                     frappe.log_error(frappe.get_traceback(),
#                                     _("Failed to create BOM for {0}").format(item_code))
#                     print(e)
#                     skipped.append((item_code, "insert error"))
                
#         # … after processing all rows …
#     print("Import complete: {0} inserted, {1} skipped.".format(len(inserted), len(skipped)))
#     frappe.msgprint(_("Import complete: {0} inserted, {1} skipped.")
#                     .format(len(inserted), len(skipped)))
#     return

import os
import csv
import frappe
from frappe import _
from itertools import chain
from frappe.utils.file_manager import get_file_path


def resolve_file_path(file_url):
    """
    Resolve a file_url to an absolute filesystem path, via File doc or site path.
    """
    try:
        file_doc = frappe.get_doc("File", {"file_url": file_url})
        return file_doc.get_full_path()
    except frappe.DoesNotExistError:
        return get_file_path(file_url)


def detect_header_and_rows(reader, expected_headers):
    """
    Read first row from CSV reader and detect if it matches expected headers.
    Returns (data_rows_iterable, start_index).
    """
    try:
        first = next(reader)
    except StopIteration:
        frappe.throw(_("The CSV file is empty."))

    normalized = [c.strip().lower().replace(' ', '_') for c in first]
    if normalized == expected_headers:
        return reader, 2
    else:
        return chain([first], reader), 1


def insert_item(item_data, commit=False):
    """
    Create and insert an Item document from a dict, return True on success.
    """
    try:
        doc = frappe.get_doc({"doctype": "Item", **item_data})
        doc.insert(ignore_permissions=True)
        if commit:
            frappe.db.commit()
        return True
    except Exception:
        frappe.log_error(frappe.get_traceback(), 
                         _(f"Failed to insert Item {item_data.get('item_code')}") )
        return False


def create_bom(item_code, components, submit=True):
    """
    Create and optionally submit a BOM for the given item with component list.
    """
    bom_items = [{"item_code": code, "qty": qty, "uom": uom}
                 for code, qty, uom in components]
    try:
        bom = frappe.get_doc({
            "doctype": "BOM",
            "item": item_code,
            "quantity": 1,
            "is_default": 1,
            "items": bom_items,
        })
        bom.insert(ignore_permissions=True)
        if submit:
            bom.submit()
        return True
    except Exception:
        frappe.log_error(frappe.get_traceback(), 
                         _(f"Failed to create BOM for {item_code}"))
        return False


def import_items_and_generate_boms(file_url: str = "/private/files/auto_creation.csv") -> dict:
    """
    Import Items from CSV and generate BOMs based on item_code patterns:
      - Prefix '20': single-seat BOM
      - Prefix '21': seat + special part
      - Prefix '3': plug and/or seat
      - Prefix '4': dynamic Body, Syringe, valve_head

    :return: {'inserted': [...], 'boms': [...], 'skipped': [...]}
    """
    # Resolve file path
    file_path = resolve_file_path(file_url)
    if not os.path.exists(file_path):
        frappe.throw(_(f"File not found: {file_path}"))

    expected_headers = [
        "item_group", "item_code", "item_name", 
        "item_type", "reference_code", "valve_head", 
        "plug", "seat", "raw_mat"
    ]

    inserted, boms_created, skipped = [], [], []

    with open(file_path, newline='', encoding='utf-8-sig') as csvfile:
        reader = csv.reader(csvfile)
        data_rows, start_idx = detect_header_and_rows(reader, expected_headers)

        for idx, row in enumerate(data_rows, start=start_idx):
            if len(row) < 5:
                frappe.log_error(_(f"Row {idx} malformed, expected >=5 columns"),
                                 "import_items_and_generate_boms")
                skipped.append((None, f"Malformed row {idx}"))
                continue

            # Unpack with defaults for missing optional fields
            (
                item_group,
                item_code,
                item_name,
                item_type,
                reference_code,
                *extras
            ) = [c.strip() for c in row]
            valve_head, plug, seat = (extras + [None]*3)[:3]

            if not item_code:
                skipped.append((None, f"Empty code at row {idx}"))
                continue

            if frappe.db.exists("Item", item_code):
                skipped.append((item_code, "Already exists"))
                continue

            # Insert Item
            item_data = {
                "item_group": item_group,
                "item_code": item_code,
                "item_name": item_name,
                "item_type": item_type,
                "reference_code": reference_code
            }
            if not insert_item(item_data):
                skipped.append((item_code, "Insert failed"))
                continue

            inserted.append(item_code)

            # Generate BOM based on prefix rules
            prefix = item_code[:2] if item_code.isdigit() else item_code[0]
            components = []
            if item_code.startswith('20'):
                components.append((seat, 1, 'Nos'))
            elif item_code.startswith('21'):
                components.extend([(seat, 1, 'Nos'), ('SPL.3039', 2, 'Nos')])
            elif item_code.startswith('3'):
                if seat:
                    components.append((seat, 1, 'Nos'))
                if plug:
                    components.append((plug, 1, 'Nos'))
            elif item_code.startswith('4') and valve_head:
                # dynamic lookup for Body and Syringe
                second, third = item_code[1], item_code[2]
                body = frappe.db.get_value(
                    "Item", {"item_group": "Body",
                             "name": ["like", f"_{second}1%"]}, "name"
                )
                syringe = frappe.db.get_value(
                    "Item", {"item_group": "Syringe",
                             "name": ["like", f"__{third}1%"]}, "name"
                )
                if body:
                    components.append((body, 1, 'Nos'))
                if syringe:
                    components.append((syringe, 1, 'Nos'))
                components.append((valve_head, 1, 'Nos'))

            # Insert BOM if components defined
            if components:
                if create_bom(item_code, components):
                    boms_created.append(item_code)
                else:
                    skipped.append((item_code, "BOM failed"))

    frappe.db.commit()
    frappe.msgprint(_(
        "Import: {0} items, {1} BOMs, {2} skipped.".
        format(len(inserted), len(boms_created), len(skipped))
    ))
    return {"inserted": inserted, "boms": boms_created, "skipped": skipped}


import os
import csv
import frappe
from frappe import _
from itertools import chain
from frappe.utils.file_manager import get_file_path
from frappe.model.rename_doc import rename_doc

def rename_item_codes_from_csv(file_url="/private/files/new_code.csv"):
    """
    Reads a CSV of [old_item_code, new_item_code] and renames each Item.
    :param file_url: path under /private/files or /public/files
    :return: dict with lists of 'renamed' tuples and 'skipped' reasons
    """
    # 1) Resolve filesystem path
    try:
        file_doc = frappe.get_doc("File", {"file_url": file_url})
        file_path = file_doc.get_full_path()
    except frappe.DoesNotExistError:
        file_path = get_file_path(file_url)

    if not os.path.exists(file_path):
        frappe.throw(_("File not found at: {0}").format(file_path))

    frappe.log_error(message=_("Renaming items via CSV at {0}").format(file_path),
                     title="rename_item_codes_from_csv [DEBUG]")

    # 2) Open and parse
    with open(file_path, newline='', encoding='utf-8-sig') as f:
        reader = csv.reader(f)

        # grab first row for optional header
        try:
            first = next(reader)
        except StopIteration:
            frappe.throw(_("CSV is empty: {0}").format(file_path))

        header = [c.strip().lower().replace(' ', '_') for c in first]
        expected_header = ["item_code", "new_item_code"]
        has_header = header == expected_header

        if has_header:
            frappe.log_error(message="Header detected, skipping first row",
                             title="rename_item_codes_from_csv [DEBUG]")
            data_rows = reader
            start_idx = 2
        else:
            frappe.log_error(message="No header detected, including first row",
                             title="rename_item_codes_from_csv [DEBUG]")
            data_rows = chain([first], reader)
            start_idx = 1

        renamed = []
        skipped = []

        # 3) Iterate and rename
        for idx, row in enumerate(data_rows, start=start_idx):
            # basic validation
            if len(row) != 2:
                frappe.log_error(
                    message=_("Row {0} has {1} columns, expected 2").format(idx, len(row)),
                    title="rename_item_codes_from_csv"
                )
                skipped.append((None, None, f"bad column count at row {idx}"))
                continue

            old_code, new_code = [c.strip() for c in row]

            if not old_code or not new_code:
                frappe.log_error(
                    message=_("Row {0} missing old or new code").format(idx),
                    title="rename_item_codes_from_csv"
                )
                print((old_code, new_code, "empty value at row", idx))
                skipped.append((old_code, new_code, f"empty value at row {idx}"))
                continue

            # existence checks
            if not frappe.db.exists("Item", old_code):
                print((old_code, new_code, "old code not found"))
                skipped.append((old_code, new_code, "old code not found"))
                continue

            if frappe.db.exists("Item", new_code):
                print((old_code, new_code, "new code already exists"))
                skipped.append((old_code, new_code, "new code already exists"))
                continue

            # perform rename
            try:
                rename_doc(
                    "Item",
                    old_code,
                    new_code
                )
                frappe.db.commit()
                renamed.append((old_code, new_code))
                print("Renamed {0} → {1}".format(old_code, new_code))
            except Exception as e:
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=_("Failed to rename {0} → {1}. Reason: {2}").format(old_code, new_code, e)
                )
                print("Failed to rename {0} → {1}. Reason: {2}".format(old_code, new_code, e))
                skipped.append((old_code, new_code, "error during rename"))
            # set reference_name on the newly-named doc
            item_name = frappe.db.get_value("Item", new_code, "item_name")
            try:
                frappe.db.set_value(
                    "Item",
                    new_code,
                    "reference_name",
                    f"{new_code}: {item_name}",
                    update_modified=True
                )
            except Exception:
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=_("Failed to set reference_name for {0}").format(new_code)
                )
                print((old_code, new_code, "error setting reference_name"))
                skipped.append((old_code, new_code, "error setting reference_name"))
                continue

    # 4) summary
    print(f"Rename complete: {len(renamed)} succeeded, {len(skipped)} skipped.")
    frappe.msgprint(_(
        "Rename complete: {0} succeeded, {1} skipped."
    ).format(len(renamed), len(skipped)))

    return
