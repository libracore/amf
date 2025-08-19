import frappe
import datetime

from frappe.utils import now_datetime

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

# ——— Log Handling Utilities —————————————————
def _get_or_create_log(doc):
    """
    Retrieve existing Log Entry for this Stock Entry or create a new one.
    """
    reference = f"{doc.doctype}: {doc.name}"
    existing = frappe.get_all(
        "Log Entry",
        filters={"reference_name": reference},
        order_by="creation desc",
        limit_page_length=1,
        fields=["name"]
    )
    if existing:
        return existing[0].name
    # not found → create
    msg = f"[{now_datetime()}] {doc.doctype} {doc.name} initiated"
    return create_log_entry(msg, doc.doctype, reference)

def _create_log_entry(message, category, name):
    """
    Create a new Log Entry and return its ID.
    """
    log = frappe.get_doc({
        "doctype": "Log Entry",
        "timestamp": datetime.datetime.now(),
        "category": category,
        "message": message,
        "reference_name": name,
    }).insert(ignore_permissions=True)
    frappe.db.commit()
    return log.name


def _update_log_entry(log_id, message):
    """
    Append a message to an existing Log Entry.
    """
    log = custom_try(frappe.get_doc, "Log Entry", log_id)
    if not log:
        return
    log.message = (log.message or "") + "\n" + (message or "")
    custom_try(log.save, ignore_permissions=True)


def _custom_try(func, *args, **kwargs):
    """
    Execute func safely, logging exceptions.
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        frappe.log_error(message=str(e), title=f"Error in {func.__name__}")
        frappe.db.rollback()
        return None

@frappe.whitelist()
def update_item_defaults_for_syringes():
    """
    This function updates the default expense and income accounts for items
    that belong to the 'Syringe' item group and have an item code starting with 'C'.

    Note: Please replace 'Your New Expense Account' and 'Your New Income Account'
    with the actual account names you want to set.
    """
    
    # Define the new account heads
    new_expense_account = "4006 - Cost of general and accessory materials - AMF21"  # e.g., "Cost of Goods Sold - My Company"
    new_income_account = "3005 - Accessory sales revenue - AMF21"    # e.g., "Sales - My Company"

    # Fetch the names of all items matching the criteria
    try:
        sql_query = """
            SELECT name
            FROM `tabItem`
            WHERE item_group = 'Syringe' OR item_code LIKE 'C%'
        """
        # frappe.db.sql returns a list of tuples, e.g., [('ITEM-001',), ('ITEM-002',)]
        # We need to flatten this into a simple list of names.
        query_result = frappe.db.sql(sql_query)
        items_to_update = [item[0] for item in query_result]

        if not items_to_update:
            print("No items found matching the criteria.")
            return

        print(f"Found {len(items_to_update)} items to update.")

        # Loop through each item found
        for item_name in items_to_update:
            try:
                # Load the full item document
                item_doc = frappe.get_doc("Item", item_name)
                
                # The 'item_defaults' field holds the child table data
                if item_doc.get("item_defaults"):
                    # Loop through each row in the 'Item Defaults' child table
                    for item_default in item_doc.get("item_defaults"):
                        # You might want to add a condition here if you have multiple companies,
                        # for example: if item_default.company == "Your Company Name":
                        item_default.expense_account = new_expense_account
                        item_default.income_account = new_income_account
                        print(f"Updating accounts for {item_name} in company {item_default.company}")

                    # Save the document to persist the changes
                    item_doc.save(ignore_permissions=True) # Use ignore_permissions if running from console
                    print(f"Successfully saved changes for {item_name}.")

            except Exception as e:
                print(f"Error processing item {item_name}: {e}")

        # Commit the changes to the database
        frappe.db.commit()
        print("\nUpdate process completed and changes have been committed.")

    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        frappe.db.rollback() # Rollback in case of a major error
