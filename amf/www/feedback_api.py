# Frappe / ERPNext Framework Python Script
# Filename: feedback_api.py
# Place this file in the same folder as your sales_invoice_hooks.py
# e.g., my_custom_app/my_custom_app/feedback_api.py

import frappe

@frappe.whitelist(allow_guest=True)
def save_feedback(rating, customer_email, comments=None):
    """
    Saves customer feedback to the 'Customer Feedback' DocType.
    This function is callable from the client-side (Web Pages).
    `allow_guest=True` is important as the user clicking the link may not be logged in.
    """
    try:
        # Create a new document for the "Customer Feedback" DocType
        # This assumes you have created a Custom DocType with these field names.
        new_feedback = frappe.get_doc({
            "doctype": "Customer Feedback",
            "rating": rating,
            "customer_email": customer_email,
            "comments": comments
        })
        
        # Insert the document into the database
        new_feedback.insert()
        
        # The .insert() method automatically commits, so no need for frappe.db.commit()
        
        return {"status": "success", "message": "Feedback saved successfully."}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Customer Feedback API Error")
        return {"status": "error", "message": str(e)}
