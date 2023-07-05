import frappe
from frappe.utils import nowdate
from frappe.core.doctype.communication.email import make

def check_purchase_orders():
    # Fetch all the Purchase Orders which are 'To Bill' and today's date
    purchase_orders = frappe.get_all('Purchase Order', 
        filters = {
            'status': 'To Bill'
        }, 
        fields = ['name', 'owner', 'schedule_payment_date']  # Assuming 'email_id' field in Purchase Order doctype
    )

    # Loop through the purchase orders and send an email to the owner
    for po in purchase_orders:
        if po['schedule_payment_date'] == nowdate():
            send_email(po)

def send_email(purchase_order):
    # Creating email context
    email_context = {
        'recipients': purchase_order['owner'],
        'message': "Dear {owner},\n\nThe Purchase Order '{name}' is due for billing soon. Please proceed with the payment or send the invoice to the office manager.\n\nThanks,".format(owner=purchase_order['owner'], name=purchase_order['name']),
        'subject': "Automatic Notification for Purchase Order: {name}".format(name=purchase_order['name']),
        'communication_medium': 'Email',
        'send_email': True,
        'cc': ['madeleine.fryer@amf.ch']
    }

    # Sending email
    make(**email_context)

# This function will be triggered daily
frappe.enqueue('amf.amf.utils.document_notification.check_purchase_orders', queue='long', timeout=600, is_async=True)
