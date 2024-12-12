import frappe
from frappe import _
import socket

@frappe.whitelist()
def send_to_zebra(work_order_name):
    # Get the Work Order document
    work_order = frappe.get_doc('Work Order', work_order_name)

    # Generate ZPL command based on Work Order
    zpl_command = generate_zpl_command(work_order)

    # Send ZPL command to Zebra printer
    send_zpl_to_printer(zpl_command)

    return {'status': 'success'}

def generate_zpl_command(work_order):
    # Customize this function based on your printing needs
    zpl = '^XA'  # Start of label
    zpl += '^FO50,50^A0N,50,50^FDWork Order:^FS'
    zpl += f'^FO50,110^A0N,50,50^FD{work_order.name}^FS'
    # Add more fields as necessary
    zpl += '^XZ'  # End of label
    return zpl

def send_zpl_to_printer(zpl_command):
    # Replace with your printer's IP and port
    printer_ip = '192.168.1.100'  # Change to your printer's IP
    printer_port = 9100  # Default port for Zebra printers

    # Create a socket connection
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((printer_ip, printer_port))
        s.sendall(zpl_command.encode('utf-8'))

@frappe.whitelist()
def get_serial_numbers_for_manufacture(work_order):
    # Fetch all Stock Entries with purpose 'Manufacture' linked to this Work Order
    stock_entries = frappe.get_all('Stock Entry', 
                                   filters={'work_order': work_order, 'purpose': 'Manufacture'},
                                   order_by="creation desc")

    serial_no_dict = {}

    for stock_entry in stock_entries:
        stock_entry_name = stock_entry['name']
        
        # Fetch the items in the Stock Entry, sorted by creation time
        stock_entry_items = frappe.get_all('Stock Entry Detail', 
                                           filters={'parent': stock_entry_name}, 
                                           fields=['item_code', 'serial_no', 'idx'],
                                           order_by="idx desc")

        # Check the last stock entry item (the one with the highest idx)
        if stock_entry_items:
            last_item = stock_entry_items[0]  # Last item based on idx
            if last_item.serial_no:
                print(last_item.serial_no)
                # Add to the dictionary, with Stock Entry name as key and serial_no as value
                serial_no_dict[stock_entry_name] = last_item.serial_no

    # If serial numbers are found, print labels and return the serial numbers
    if serial_no_dict:
        return list(serial_no_dict.values())
    else:
        return []

@frappe.whitelist()    
def get_serial_numbers_for_manufacture_updated(work_order):
    """
    Fetches the serial numbers for the manufacture process of a given work order.

    Args:
        work_order (str): The name of the work order.

    Returns:
        list: A list of serial numbers used in the manufacture process.
    """
    # Fetch all Stock Entries with purpose 'Manufacture' linked to this Work Order
    stock_entries = frappe.get_all(
        'Stock Entry',
        filters={'work_order': work_order, 'purpose': 'Manufacture', 'docstatus': 1},
        order_by="creation desc"
    )

    serial_no_dict = {}

    for stock_entry in stock_entries:
        stock_entry_name = stock_entry['name']

        # Fetch the items in the Stock Entry, sorted by creation time
        stock_entry_items = frappe.get_all(
            'Stock Entry Detail',
            filters={'parent': stock_entry_name},
            fields=['item_code', 'serial_no', 'idx'],
            order_by="idx desc"
        )

        # Check the last stock entry item (the one with the highest idx)
        if stock_entry_items:
            last_item = stock_entry_items[0]  # Last item based on idx
            if last_item.serial_no:
                # Handle multiple serial numbers separated by '\n'
                serial_numbers = last_item.serial_no.split('\n')
                serial_numbers = [sn.strip() for sn in serial_numbers if sn.strip()]  # Clean up whitespace
                print(serial_numbers)

                # Add to the dictionary with Stock Entry name as the key and serial numbers as the value
                serial_no_dict[stock_entry_name] = serial_numbers

    # If serial numbers are found, consolidate them into a list and return
    if serial_no_dict:
        # Flatten the dictionary values (list of lists) into a single list of serial numbers
        all_serial_numbers = [sn for serials in serial_no_dict.values() for sn in serials]
        return all_serial_numbers
    else:
        return []


def print_label(serial_no):
    # Logic to print the label for the given serial number
    # This could involve sending the serial number to a specific printer or creating a print format
    print(f"Printing label for serial number: {serial_no}")
    for serial in serial_no:
        frappe.print_format('Label Serial No', { 'docname': serial })

