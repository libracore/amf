import os
import csv
import frappe
from frappe import _
from itertools import chain
from frappe.utils.file_manager import get_file_path

def main():
    import_items_and_generate_boms()
    rename_item_codes_from_csv()
    import_items_with_motor_bom()
    return

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
                "reference_code": reference_code,
                "reference_name": f"{item_code}: {reference_code}",
                "description": f"Group: Valve Head<br>Code: {item_code}<br>Reference: {reference_code}",
                "default_material_request_type": "Manufacture",
                "is_purchase_item": 0,
                "is_sales_item": 1,
                "has_batch_no": 1,
                "country_of_origin": "Switzerland",
                "customs_tariff_number": "8487.9000",
                "item_defaults": [
                    {   "company": "Advanced Microfluidics SA",
                        "default_warehouse": "Main Stock - AMF21",
                        "expense_account": "4003 - Cost of material: RVM rotary valve - AMF21",
                        "income_account":  "3003 - RVM sales revenue - AMF21"}
                ]
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
        expected_header = ["item_code", "new_item_code", "new_item_name", "new_ref_code"]
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
            if len(row) != 4:
                frappe.log_error(
                    message=_("Row {0} has {1} columns, expected 3").format(idx, len(row)),
                    title="rename_item_codes_from_csv"
                )
                skipped.append((None, None, f"bad column count at row {idx}"))
                continue

            old_code, new_code, new_item_name, new_ref_code = [c.strip() for c in row]

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
            try:
                frappe.db.set_value(
                    "Item",
                    new_code,
                    "item_name",
                    new_item_name,
                    update_modified=True
                )
                frappe.db.commit()
            except Exception:
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=_("Failed to set item_name for {0}").format(new_code)
                )
                print((old_code, new_code, "error setting item_name"))
                skipped.append((old_code, new_code, "error setting item_name"))
                continue
            try:
                if new_item_name:
                    ref_name = f"{new_code}: {new_item_name}"
                else:
                    ref_name = new_code
                frappe.db.set_value(
                    "Item",
                    new_code,
                    "reference_name",
                    ref_name,
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
            try:
                if new_ref_code:
                    ref_code = new_ref_code
                else:
                    ref_code = new_code
                frappe.db.set_value(
                    "Item",
                    new_code,
                    "reference_code",
                    ref_code,
                    update_modified=True
                )
            except Exception:
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=_("Failed to set reference_code for {0}").format(new_code)
                )
                print((old_code, new_code, "error setting reference_code"))
                skipped.append((old_code, new_code, "error setting reference_code"))
                continue
            try:
                frappe.db.set_value(
                    "Item",
                    new_code,
                    "description",
                    f"Code: {new_code}<br>Reference: {new_ref_code}<br>Name: {new_item_name}",
                    update_modified=True
                )
            except Exception:
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=_("Failed to set description for {0}").format(new_code)
                )
                print((old_code, new_code, "error setting description"))
                skipped.append((old_code, new_code, "error setting description"))
                continue

    # 4) summary
    print(f"Rename complete: {len(renamed)} succeeded, {len(skipped)} skipped.")
    frappe.msgprint(_(
        "Rename complete: {0} succeeded, {1} skipped."
    ).format(len(renamed), len(skipped)))

    return

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


def import_items_with_motor_bom(file_url: str = "/private/files/new_creation.csv") -> dict:
    """
    Import Items from CSV with columns:
      item_code, item_name, reference_code, default_expense, default_income, motor
    Set:
      - item_group='Body'
      - item_type='Actuator'
      - stock_uom='Nos'
    For codes with 3rd digit = '1':
      - has_serial_no = 1
      - serial_no_series = f"{item_code}-.########"
    Populate child table `item_defaults` with default_expense and default_income.
    If `motor` provided, create a BOM with that motor component.

    :return: {'inserted': [...], 'boms': [...], 'skipped': [...]}  
    """
    # Resolve CSV path
    file_path = resolve_file_path(file_url)
    if not os.path.exists(file_path):
        frappe.throw(_(f"File not found: {file_path}"))

    # Expected CSV header
    expected_headers = [
        "item_code", "item_name", "reference_code",
        "default_expense", "default_income", "motor"
    ]

    inserted, boms_created, skipped = [], [], []

    with open(file_path, newline='', encoding='utf-8-sig') as csvfile:
        reader = csv.reader(csvfile)
        data_rows, start_idx = detect_header_and_rows(reader, expected_headers)

        for idx, row in enumerate(data_rows, start=start_idx):
            # Validate row length
            if len(row) < 5:
                skipped.append((None, f"Malformed row {idx}"))
                continue

            # Unpack columns
            (item_code, item_name, reference_code,
             default_expense, default_income, *rest) = [c.strip() for c in row]
            motor = rest[0].strip() if rest and rest[0].strip() else None

            if not item_code:
                skipped.append((None, f"Empty code at row {idx}"))
                continue

            if frappe.db.exists("Item", item_code):
                skipped.append((item_code, "Already exists"))
                continue

            # Prepare item data
            item_data = {
                "item_group":      "Body",
                "item_type":       "Actuator",
                "stock_uom":       "Nos",
                "item_code":       item_code,
                "item_name":       item_name,
                "reference_code":  reference_code,
                "reference_name": f"{item_code}: {item_name}",
                "description": f"Code: {item_code}<br>Reference: {reference_code}<br>Name: {item_name}",
                "default_material_request_type": "Manufacture",
                "is_purchase_item": 0,
                "is_sales_item": 1 if len(item_code) >= 3 and item_code[2] == '1' else 0,
                "country_of_origin": "Switzerland",
                "customs_tariff_number": "8413.5000",
                "item_defaults": [
                    {   "company": "Advanced Microfluidics SA",
                        "default_warehouse": "Main Stock - AMF21",
                        "expense_account": default_expense,
                        "income_account":  default_income}
                ]
            }

            # Serial number fields if 3rd digit == '1'
            if len(item_code) >= 3 and item_code[2] == '1':
                item_data.update({
                    "has_serial_no":     1,
                    "serial_no_series":  f"{item_code}-.########"
                })

            # Insert the Item
            if not insert_item(item_data):
                skipped.append((item_code, "Insert failed"))
                continue

            inserted.append(item_code)

            # Create BOM if motor provided
            if motor:
                # Ensure motor exists
                if not frappe.db.exists("Item", motor):
                    skipped.append((item_code, f"Motor '{motor}' not found"))
                else:
                    if create_bom(item_code, [(motor, 1, 'Nos')]):
                        boms_created.append(item_code)
                    else:
                        skipped.append((item_code, "BOM failed"))

    # Final commit and message
    frappe.db.commit()
    frappe.msgprint(_(
        "Imported: {0} items, {1} BOMs, {2} skipped.".
        format(len(inserted), len(boms_created), len(skipped))
    ))
    return {"inserted": inserted, "boms": boms_created, "skipped": skipped}
