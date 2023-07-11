import frappe
from frappe.utils import nowdate, add_days
from frappe.core.doctype.communication.email import make

from frappe.utils import add_days

def update_purchase_orders():
    # get all purchase orders that are not cancelled
    pos = frappe.get_all('Purchase Order', filters={'docstatus': ['<', 2]}, fields=['name'])

    for po in pos:
        po_doc = frappe.get_doc('Purchase Order', po.name)
        
        # check if payment_schedule exists and is not empty
        if po_doc.payment_schedule:
            # filter the payment_schedule to exclude rows where payment_reminder_date is checked
            payment_schedule = [x for x in po_doc.payment_schedule if not x.payment_reminder_date]
            
            # if no schedule left, continue to next Purchase Order
            if not payment_schedule:
                continue

            # sort the filtered payment_schedule by due_date
            payment_schedule.sort(key=lambda x: x.due_date)

            # subtract 3 days from the earliest due_date and set as schedule_payment_date
            po_doc.schedule_payment_date = add_days(payment_schedule[0].due_date, -3)

            # Check if schedule_payment_date has a value and the status is 'To Bill'
            if po_doc.schedule_payment_date and po_doc.status == 'To Bill':
                # Set global payment_reminder to 1
                po_doc.payment_reminder = 1
                
                # Set payment_reminder_date for the corresponding row to 1 (checked)
                payment_schedule[0].payment_reminder_date = 1
            
            # save the changes
            # try:
            #     po_doc.save()
            #     frappe.db.commit()  # ensure changes are committed to the database
            # except Exception as e:
            #     frappe.log_error(message=f"Error updating Purchase Order {po.name}: {e}", title="Update Purchase Orders Script")


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

@frappe.whitelist()
def generate_payment_schedule(po_name):
    # get the purchase order
    po_doc = frappe.get_doc('Purchase Order', po_name)
    # get the linked payment terms template
    if po_doc.payment_terms_template:
        payment_terms_template = frappe.get_doc('Payment Terms Template', po_doc.payment_terms_template)
    else:
        return
    # clear the existing payment schedule
    po_doc.set('payment_schedule', [])
    # dictionary to store total amount and total percentage for each schedule_date
    schedule_totals = {}
    # calculate total amount for each schedule_date
    for item in po_doc.items:
        schedule_date = item.schedule_date
        if schedule_date not in schedule_totals:
            schedule_totals[schedule_date] = {'total_amount': 0}
        schedule_totals[schedule_date]['total_amount'] += item.amount
    # create a new payment schedule entry for each schedule_date
    for schedule_date, totals in schedule_totals.items():
        for term in payment_terms_template.terms:
            # calculate due_date based on schedule_date and credit_days from the term
            due_date = add_days(schedule_date, term.credit_days)

            # calculate invoice_portion
            invoice_portion = (totals['total_amount'] / po_doc.total) * 100  # as a percentage

            # append new payment schedule entry
            po_doc.append('payment_schedule', {
                'payment_term': term.payment_term,
                'due_date': due_date,
                'payment_amount': totals['total_amount'],
                'invoice_portion': invoice_portion,
            })
    # for schedule in po_doc.payment_schedule:
    #     print(schedule.due_date)
    #     print(schedule.invoice_portion)
    #     print(schedule.payment_amount)

    
    # save the changes
    try:
        po_doc.save()
        frappe.db.commit()  # ensure changes are committed to the database
        return 'Payment schedule generated successfully for Purchase Order: ' + po_name
    except Exception as e:
        frappe.log_error(message=f"Error updating Purchase Order {po_name}: {e}", title="Generate Payment Schedule")
        return 'Error while generating payment schedule: ' + str(e)