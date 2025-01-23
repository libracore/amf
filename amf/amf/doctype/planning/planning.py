# -*- coding: utf-8 -*-
# Copyright (c) 2024, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import json
import frappe
from frappe.model.document import Document
from frappe.utils.data import now_datetime
from frappe.utils.pdf import get_pdf
from frappe.utils.file_manager import save_file
from frappe.utils.print_format import download_pdf

class Planning(Document):
    pass

@frappe.whitelist()
def get_rawmat_items(item_code):
    # Get all active BOMs for the given item code
    active_boms = frappe.db.get_list('BOM', {'item': item_code, 'is_active': 1}, 'name')
    
    if not active_boms:
        return {'message': frappe._('No active BOM found for item code {0}').format(item_code), 'items': []}
    
    mat_items = []
    
    # Iterate over each BOM to get the BOM items
    for bom in active_boms:
        bom_items = frappe.db.get_list('BOM Item',
                                       filters={
                                           'parent': bom['name'],
                                           'item_code': ['like', 'MAT.%']
                                       },
                                       fields=['item_code', 'item_name'])
        mat_items.extend(bom_items)
    
    if mat_items:
        # Create a list to hold "item_code: item_name" strings
        items_list = ['{}: {}'.format(item['item_code'], item['item_name']) for item in mat_items]
        return {
            'message': 'MAT items found',
            'items': items_list
        }
    else:
        return {
            'message': 'No "MAT" items found in the active BOMs for item code {}'.format(item_code),
            'items': []
        }

@frappe.whitelist()
def create_work_order(form_data: str, wo=None) -> dict:
    """
    Create a Work Order and manage the stock entries.

    Args:
        form_data (str): JSON-formatted string or dictionary containing work order details.
        wo: if a work_order is passed as args from the doctype or not
    
    Returns:
        dict: Success or failure message along with created document references.
    """
    try:
        # Parse form data
        data = _parse_form_data(form_data)
        # Validate item existence
        if not frappe.db.exists('Item', data['item_code']):
            return _error_response('Item code not found')

        # Fetch active BOM number
        matched_bom_no = _get_active_bom(data['item_code'], data['matiere'][:8])
        if not matched_bom_no:
            return _error_response(f"No active BOM matches the item code {data['item_code']}")

        # Create and submit Work Order
        if wo is None:
            work_order = _create_work_order_doc(data, matched_bom_no)
            work_order.insert()
            work_order.submit()
        else:
            # 1. Fetch the existing Work Order by name/ID
            work_order = frappe.get_doc("Work Order", wo)
            
            # 2. Update fields in the existing Work Order from the Planning doc
            #    (Examples: set the same item_code, planned_start_date, etc.)
            work_order.qty = int(data['quantite_validee']) + int(data['quantite_scrap'])
            work_order.assembly_specialist_start = data['responsable']
            work_order.start_date_time = data['date_de_debut']
            work_order.end_date_time = data['date_de_fin']
            work_order.fg_warehouse = "Quality Control - AMF21"
            work_order.scrap_qty = data['quantite_scrap']
            work_order.machine = data['machine']
            work_order.wip_step = 1
            work_order.skip_transfer = 1
            work_order.raw_material = data['matiere']
            work_order.raw_material_batch = data['batch_matiere']
            work_order.raw_material_dim = data['dimension_matiere']
            work_order.start_datetime = data['date_de_debut']
            work_order.end_datetime = data['date_de_fin']
            work_order.cycle_time = data['temps_de_cycle_min']
            work_order.program = data['programme']
            work_order.program_time = data['temps_de_programmation_hr']
            work_order.setup_time = data['temps_de_reglage_hr']
            work_order.production_comments = data['remarque_usinage']
            work_order.simple_description = data['remarque_assemblage']
            work_order.label = data['suivi_usinage']
            # ... set other fields as needed ...

            # 3. Optionally, pull some info directly from 'data' if relevant
            #    For example:
            # work_order.some_custom_field = data.get("some_custom_value")

            # 4. Save and/or submit. If the Work Order is still a Draft, you can submit it
            work_order.save()
            if work_order.docstatus == 0:
                work_order.submit()

        # Create stock entries (manufacture and transfer if applicable)
        manufacture_entry, manufacture_batch = _create_manufacture_entry(work_order, data)
        transfer_entry = _create_transfer_entry_if_applicable(work_order, data, manufacture_entry)

        # Commit the transaction
        frappe.db.commit()

        return _success_response(work_order, manufacture_entry, manufacture_batch)

    except frappe.ValidationError as e:
        frappe.log_error(frappe.get_traceback(), 'Validation Error in Work Order Creation')
        return _error_response(str(e))

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), 'Work Order Creation Failed')
        return _error_response(str(e))


def _parse_form_data(form_data: str) -> dict:
    """Helper function to parse the form data."""
    return json.loads(form_data) if isinstance(form_data, str) else form_data


def _get_active_bom(item_code: str, raw_material: str) -> str:
    """Fetches the active BOM number based on the item code and raw material."""
    bom_no_list = frappe.db.get_all(
        'BOM Item',
        filters={'item_code': raw_material, 'parenttype': 'BOM', 'parentfield': 'items'},
        fields=['parent']
    )

    # Find the BOM that matches the item code and is active
    for bom in bom_no_list:
        bom_no = bom['parent']
        is_active = frappe.db.get_value('BOM', {'name': bom_no, 'is_active': 1}, 'item')
        if is_active == item_code:
            return bom_no
    return None


def _create_work_order_doc(data: dict, bom_no: str) -> Document:
    """Creates and returns a new Work Order document."""
    return frappe.get_doc({
        'doctype': 'Work Order',
        'production_item': data['item_code'],
        'bom_no': bom_no,
        'destination': 'N/A',
        'qty': int(data['quantite_validee']) + int(data['quantite_scrap']),
        'wip_warehouse': 'Main Stock - AMF21',
        'fg_warehouse': 'Quality Control - AMF21',
        'company': frappe.db.get_single_value('Global Defaults', 'default_company'),
        'assembly_specialist_start': data['responsable'],
        'assembly_specialist_end': data['responsable'],
        'start_date_time': data['date_de_debut'],
        'end_date_time': data['date_de_fin'],
        'scrap_qty': data['quantite_scrap'],
        'machine': data['machine'],
        'wip_step': 1,
        'skip_transfer': 1,
        'raw_material': data['matiere'],
        'raw_material_batch': data['batch_matiere'],
        'raw_material_dim': data['dimension_matiere'],
        'start_datetime': data['date_de_debut'],
        'end_datetime': data['date_de_fin'],
        'cycle_time': data['temps_de_cycle_min'],
        'program': data['programme'],
        'program_time': data['temps_de_programmation_hr'],
        'setup_time': data['temps_de_reglage_hr'],
        'production_comments': data['remarque_usinage'],
        'simple_description': data['remarque_assemblage'],
        'label': data['suivi_usinage']
    })


def _create_manufacture_entry(work_order: Document, data: dict) -> tuple:
    """Creates a manufacture stock entry."""
    return _make_stock_entry(
        work_order.name, 'Manufacture', int(data['quantite_validee']), int(data['quantite_scrap'])
    )


def _create_transfer_entry_if_applicable(work_order: Document, data: dict, manufacture_entry: Document) -> Document:
    """Creates a transfer stock entry if there's scrap quantity."""
    if int(data['quantite_scrap']) > 0:
        return _make_stock_entry(
            work_order.name, 'Material Transfer', None, int(data['quantite_scrap']), manufacture_entry
        )
    return None


def _make_stock_entry(work_order_id, purpose, qty=None, scrap=None, ft_stock_entry=None):
    """Helper function to create stock entries for manufacturing or transfer purposes."""
    work_order = frappe.get_doc("Work Order", work_order_id)

    if purpose == 'Manufacture':
        stock_entry, batch_no = _create_stock_entry(work_order, purpose, qty, scrap, True if qty else False)
    
    # Create transfer stock entry if no quantity is provided (i.e., scrap)
    if qty is None:
        _create_stock_entry(work_order, purpose, None, scrap, False, ft_stock_entry)

    if qty:
        return stock_entry.as_dict(), batch_no


def _create_stock_entry(work_order, purpose, qty, scrap, from_bom, ft_stock_entry=None):
    """
    Create and return a Stock Entry document based on the Work Order.

    Args:
        work_order (Document): The related work order document.
        purpose (str): The purpose of the stock entry ('Manufacture' or 'Material Transfer').
        qty (int): Quantity of items.
        scrap (int): Scrap quantity.
        from_bom (bool): If the stock entry is from BOM.
        ft_stock_entry (dict): Additional stock entry details, if applicable.

    Returns:
        tuple: Created Stock Entry and Batch number.
    """
    stock_entry = frappe.new_doc("Stock Entry")
    stock_entry.purpose = purpose
    stock_entry.work_order = work_order.name
    stock_entry.company = work_order.company
    stock_entry.from_bom = from_bom
    stock_entry.bom_no = work_order.bom_no if from_bom else None
    stock_entry.use_multi_level_bom = work_order.use_multi_level_bom
    
    if purpose == "Material Transfer":
        _set_material_transfer_data(stock_entry, scrap, ft_stock_entry)
    else:
        _set_manufacture_data(stock_entry, qty, scrap, from_bom)

    stock_entry.set_stock_entry_type()
    stock_entry.get_stock_and_rate()

    stock_entry.insert()
    batch_no = create_batch_if_manufacture(stock_entry) if qty else None

    stock_entry.submit()
    return stock_entry, batch_no


def _set_material_transfer_data(stock_entry, scrap, ft_stock_entry):
    """Helper function to set data for material transfer stock entry."""
    stock_entry.fg_completed_qty = scrap
    stock_entry.from_warehouse = 'Quality Control - AMF21'
    stock_entry.to_warehouse = 'Scrap - AMF21'
    item = ft_stock_entry['items'][-1]
    item['qty'] = scrap
    item['s_warehouse'] = stock_entry.from_warehouse
    item['t_warehouse'] = stock_entry.to_warehouse
    stock_entry.append('items', item)


def _set_manufacture_data(stock_entry, qty, scrap, from_bom):
    """Helper function to set data for manufacture stock entry."""
    stock_entry.fg_completed_qty = qty + scrap
    stock_entry.from_warehouse = 'Main Stock - AMF21' if qty else 'Quality Control - AMF21'
    stock_entry.to_warehouse = 'Quality Control - AMF21' if qty else 'Scrap - AMF21'
    if from_bom:
        stock_entry.get_items()
    # Now set the warehouses for each item
    for item in stock_entry.items:
        # 's_warehouse' is the warehouse from which the item is drawn
        item.s_warehouse = 'Main Stock - AMF21' if qty else 'Quality Control - AMF21'
        # 't_warehouse' is the warehouse into which the item is placed
        item.t_warehouse = 'Quality Control - AMF21' if qty else 'Scrap - AMF21'


def create_batch_if_manufacture(stock_entry):
    """
    Create a batch if the stock entry is for manufacturing.

    Args:
        stock_entry (Document): The stock entry document.

    Returns:
        str: Batch number.
    """
    if stock_entry.purpose == 'Manufacture' and stock_entry.items:
        last_item = stock_entry.items[-1]
        item_has_batch_no = frappe.db.get_value('Item', last_item.item_code, 'has_batch_no')

        if item_has_batch_no:
            unique_suffix = now_datetime().strftime('%Y%m%d%H%M%S')
            batch_id = f"{unique_suffix} {last_item.item_code} AMF"
            existing_batch = frappe.db.exists('Batch', {'batch_id': batch_id})

            if existing_batch:
                # Generate a unique batch ID if necessary
                batch_id += f" #2"

            new_batch_doc = frappe.get_doc({
                'doctype': 'Batch',
                'item': last_item.item_code,
                'batch_id': batch_id,
                'work_order': stock_entry.work_order,
            })
            new_batch_doc.insert()
            last_item.batch_no = new_batch_doc.name
            return last_item.batch_no

def _error_response(message: str) -> dict:
    """
    Helper function to format error responses.

    Args:
        message (str): The error message to return.

    Returns:
        dict: A dictionary with a success flag set to False and the error message.
    """
    return {
        'success': False,
        'message': message
    }
    
def _success_response(work_order, manufacture_entry=None, manufacture_batch=None) -> dict:
    """
    Helper function to format success responses.

    Args:
        work_order (Document): The created Work Order document.
        manufacture_entry (Document, optional): The manufacture Stock Entry document.
        transfer_entry (Document, optional): The transfer Stock Entry document (if applicable).
        manufacture_batch (str, optional): The batch number associated with the manufacturing entry (if applicable).

    Returns:
        dict: A dictionary with a success flag set to True and relevant document details.
    """
    return {
        'success': True,
        'work_order': work_order.name,
        'stock_entry': manufacture_entry.name if manufacture_entry else None,
        'batch': manufacture_batch if manufacture_batch else None
    }
    
@frappe.whitelist()
def generate_and_attach_pdf(doctype, docname, print_format):
    try:
        print("##### START GENERATE PDF #####")
        # Get the document
        # Get the HTML for the document using the specified print format
        doc = download_pdf(doctype, docname, print_format, None, 1)
        print(doc)
        # Define file name
        file_name = f'{docname}_sticker.pdf'
        
        # Attach the PDF to the document
        _file = save_file(file_name, doc, doctype, docname, is_private=1)
        
        # Return success message
        return {"success": True}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "PDF Generation Failed")
        return {"success": False, "error": str(e)}
    
@frappe.whitelist()
def get_next_suivi_usinage():
    """
    Returns the next suivi_usinage string in the format 'M-XXXX'.
    It checks the most recent 'Planning' record with a valid pattern,
    increments the numeric part, and zero-pads to 4 digits.
    """
    # 1) Query for the last suivi_usinage matching 'M-%'
    last_entry = frappe.db.get_list(
        "Planning",
        fields=["suivi_usinage"],
        filters=[["suivi_usinage", "like", "M-%"]],
        order_by="creation desc",
        limit_page_length=1
    )

    # 2) If a record was found, parse and increment
    if last_entry:
        last_value = last_entry[0].get("suivi_usinage", "")
        # Split e.g. "M-0123" -> ["M", "0123"]
        parts = last_value.split("-")
        if len(parts) == 2 and parts[1].isdigit():
            last_digits_int = int(parts[1])
        else:
            # Fallback if pattern is off
            last_digits_int = 0
        new_digits_int = last_digits_int + 1
    else:
        # If no matching records, start at 1
        new_digits_int = 1

    # 3) Construct new value with zero-padding (4 digits)
    new_digits_str = str(new_digits_int).zfill(4)  # or padStart(4,'0') in Python style
    new_suivi = f"M-{new_digits_str}"

    return new_suivi