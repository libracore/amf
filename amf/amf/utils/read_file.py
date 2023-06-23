import pandas as pd
import frappe
import os

@frappe.whitelist()
def create_expense_items(expense_claim, attach):
    # Get the file document
    file_doc = frappe.get_doc('File', {'file_url': attach})

    # Get the absolute file path
    base_path = frappe.utils.get_site_path('')
    file_path = os.path.join(base_path, file_doc.file_url.strip("/"))

    # Read the Excel file
    df = pd.read_excel(file_path, skiprows=7, usecols=range(11))

    # Convert the DataFrame to a list of dictionaries
    items = df.to_dict('records')

    expense_claim_doc = frappe.get_doc("Expense Claim", expense_claim)
    child = frappe.new_doc("Expense Items")
    # Add items to the Expense Claim document
    for item in items:
        # Check if 'Pos.' is empty, and if so, stop processing
        if pd.isna(item.get('Pos.')):
            break
        expense_claim_doc.append('expense_items', {
            'position': item['Pos.'],
            'date': item['Date'],
            'cost_center': item['Projet/Centre de Coût'],
            'reason': item['Motif'],  # Assuming 'Motif' corresponds to an existing expense type
            'description': item['Description'],
            'account_number': item['Numéro de compte'],  # Make sure this account exists
            'paid_by': item['Payé par'],  # This should match a valid 'Paid By' option
            'currency': item['Monnaie'],
            'quantity': item['Qte'],
            'unit_price': item['Montant unitaire'],
            'amount_chf': item['Montant CHF'],  # If this is the total amount
            # If you need to set quantity and unit amount, add those fields to your child table
        })
    # Save and submit the document
    expense_claim_doc.save(ignore_permissions=True)
    frappe.db.commit()
    return 'Expense items created successfully'
