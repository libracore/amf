import frappe
from frappe.utils import add_to_date, nowdate

def delete_old_doctype_entries(doctype_name, months_old=1):
    """
    Deletes all entries from a specified DocType that are older than
    a given number of months.

    :param doctype_name: The name of the DocType to clean up (e.g., 'Error Log').
    :param months_old: The age in months. Records older than this will be deleted.
    """
    if not doctype_name:
        frappe.log_error("DocType name not provided for cleanup.", "Log Cleanup Failed")
        return

    try:
        # Calculate the cutoff date. All records with a 'creation' date
        # before this date will be deleted.
        cutoff_date = add_to_date(nowdate(), months=-months_old)

        # Use Frappe's DB API to perform the bulk deletion.
        # This is more efficient than loading each document into memory.
        # Note: Table names in the database are prefixed with 'tab'.
        frappe.db.delete(doctype_name, {
            "creation": ["<", cutoff_date]
        })

        # Commit the changes to the database.
        frappe.db.commit()

        frappe.log_error(
            f"Successfully deleted '{doctype_name}' entries older than {cutoff_date}.",
            "Log Cleanup Success"
        )

    except Exception as e:
        # Log any exceptions that occur during the process.
        frappe.log_error(f"An error occurred while deleting old {doctype_name} entries: {e}", "Log Cleanup Error")

def enqueue_log_cleanup():
    """
    Enqueues the main cleanup job to run as a background task.
    This prevents timeouts for very large cleanup operations.
    The job is placed in the 'long' queue, which is processed by workers
    configured for longer-running tasks.
    """
    frappe.enqueue(
        'amf.amf.utils.cleaning.scheduled_cleanup',
        queue='long',
        timeout=15000 # Timeout set to 5 hours (18000 seconds)
    )
    frappe.log_error(
        "Successfully enqueued the log cleanup job.",
        "Log Cleanup Enqueued"
    )
    
    return None

# --- Example Usage ---
# To run this automatically, you should call the `enqueue_log_cleanup` method
# from your app's hooks.py scheduler_events.
#
# The user requested to delete from 'log_entry'. Please ensure this is the correct DocType name.
# Often, users want to clear 'Error Log' or 'Activity Log'.
def scheduled_cleanup():
    """
    A function to be called by the Frappe scheduler.
    """
    # Deletes log_entry records older than 1 month
    delete_old_doctype_entries('Log Entry', months_old=1)

    # Example: To delete Error Logs older than 3 months, you would call:
    # delete_old_doctype_entries('Error Log', months_old=3)

    # Example: To delete Activity Logs older than 6 months, you would call:
    # delete_old_doctype_entries('Activity Log', months_old=6)

