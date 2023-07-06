import frappe
from frappe.utils import nowdate, add_days
from frappe.core.doctype.communication.email import make

def update_purchase_orders():
    # get all purchase orders
    pos = frappe.get_all('Purchase Order', filters={'docstatus': ['<', 2]}, fields=['name'])

    for po in pos:
        po_doc = frappe.get_doc('Purchase Order', po.name)
        
        # check if payment_schedule exists and is not empty
        if po_doc.payment_schedule:
            # sort the payment_schedule by due_date
            po_doc.payment_schedule.sort(key=lambda x: x.due_date)

            # subtract 3 days from the earliest due_date and set as schedule_payment_date
            po_doc.schedule_payment_date = add_days(po_doc.payment_schedule[0].due_date, -3)
            
            # Check if schedule_payment_date has a value and the status is 'To Bill'
            if po_doc.schedule_payment_date and po_doc.status == 'To Bill':
                # Set check_payment_reminder to 1
                po_doc.payment_reminder = 1
            
            # save the changes
            po_doc.save()

def check_purchase_orders():
    # Fetch all the Purchase Orders which are 1 in payment_reminder
    purchase_orders = frappe.get_all('Purchase Order', 
        filters = {
            'payment_reminder': '1'
        }, 
        fields = ['name', 'owner']
    )

    # Loop through the purchase orders and send an email to the owner
    for po in purchase_orders:
        if po['payment_reminder']:
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
# frappe.enqueue('amf.amf.utils.document_notification.check_purchase_orders', queue='long', timeout=600, is_async=True)
