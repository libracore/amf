import frappe
import datetime

# Global Variables

# Global Methods
def get_items_by_group(item_group):
    """ Retrieve items based on the specified item groups.

    :param item_groups: List of item groups to filter items.
    :return: List of items matching the filters. """
    filters = {
        'item_group': ['in', item_group],
        'disabled': '0'
    }
    fields = ['name', 'item_code', 'item_name', 'item_group']
    items = custom_try(frappe.get_all, 'Item', filters=filters, fields=fields)
    return items

def get_items_pattern(item_group, pattern):
    """ Retrieve items based on the specified item group and item name pattern.

    :param item_group: The item group to filter items.
    :param item_name_pattern: The pattern to match item names.
    :return: List of items matching the filters. """
    filters = {
        'item_group': item_group,
        'item_name': ['like', f'%{pattern}%'],
        'disabled': '0'
    }
    fields = ['name', 'item_code', 'item_name', 'item_group']
    items = custom_try(frappe.get_all, 'Item', filters=filters, fields=fields)
    return items

def get_plug():
    """ Retrieve items belonging to the 'Plug' item group. """
    return get_items_by_group(['Plug'])

def get_seat():
    """ Retrieve items belonging to the 'Valve Seat' item group. """
    return get_items_by_group(['Valve Seat'])

def get_plug_and_seat():
    """ Retrieve items belonging to the 'Plug' and 'Valve Seat' item groups. """
    return get_items_by_group(['Plug', 'Valve Seat'])

def create_log_entry(message, category):
    """ Create a new log entry and return its ID. """
    log_doc = frappe.get_doc({
        "doctype": "Log Entry",
        "timestamp": datetime.datetime.now(),
        "category": category,
        "message": message
    })
    custom_try(log_doc.insert, ignore_permissions=True)
    commit_database()
    return log_doc.name

def update_log_entry(log_id, message):
    """ Update an existing log entry with additional messages. """
    log = custom_try(frappe.get_doc, "Log Entry", log_id)
    if message:
        log.message += "\n" + message  # Append new information
    else:
        log.message += "\n + no message..."
    custom_try(log.save, ignore_permissions=True)
    return None

def update_error_log(message):
    """ Update the existing log entry cat. error with additional messages. """
    log = frappe.get_all('Log Entry', filters={'category': 'Global Errors'}, fields=['name'])
    if message:
        log.message += "\n" + message  # Append new information
    else:
        log.message += "\n + no message..."
    custom_try(log.save, ignore_permissions=True)
    return None

def commit_database():
    """ Commit the current transaction to the database. """
    custom_try(frappe.db.commit)
    return None

def create_document(doc_type, data):
    """ Create and insert a new document in the Frappe database. """
    doc = frappe.get_doc({"doctype": doc_type, **data})
    custom_try(doc.insert, ignore_permissions=True)
    if doc_type=='BOM':
        custom_try(doc.submit)
    return doc

def custom_try(command, *args, **kwargs):
    """ Execute a command with the given arguments and handle exceptions.

    :param command: The command to execute (a callable).
    :param args: Positional arguments to pass to the command.
    :param kwargs: Keyword arguments to pass to the command.
    :return: The result of the command if successful, None otherwise. """
    try:
        result = command(*args, **kwargs)
        return result
    except frappe.db.OperationalError as e:
        update_error_log(f"Operational error occurred: {e}")
    except frappe.db.ProgrammingError as e:
        update_error_log(f"Programming error occurred: {e}")
    except frappe.db.InternalError as e:
        update_error_log(f"Internal error occurred: {e}")
    except frappe.db.DataError as e:
        update_error_log(f"Data error occurred: {e}")
    except Exception as e:
        update_error_log(f"An unexpected error occurred: {e}")
    return None
