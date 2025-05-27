# -*- coding: utf-8 -*-
import frappe
from frappe import _

def execute(filters=None):
    """
    Unified Transactions Report with document Status.
    For Quotations: if new_valid_till < today AND status = 'Open', show 'Expired'.
    """

    columns = [
        {"label": _("Doc Type"),       "fieldname": "doc_type",          "fieldtype": "Data",         "width": 120},
        {"label": _("Name"),           "fieldname": "doc_name",          "fieldtype": "Dynamic Link", "options": "doc_type", "width": 200},
        {"label": _("Status"),         "fieldname": "doc_status",        "fieldtype": "Data",         "width": 150},
        {"label": _("Key Account"),    "fieldname": "doc_keyaccount",    "fieldtype": "Data",         "width": 200},
        {"label": _("Date"),           "fieldname": "doc_date",          "fieldtype": "Date",         "width": 100},
        {"label": _("Customer"),       "fieldname": "doc_customer",      "fieldtype": "Link",         "options": "Customer",  "width": 200},
        {"label": _("Customer Name"),  "fieldname": "doc_customername",  "fieldtype": "Data",         "width": 250},
        {"label": _("Total Amount"),   "fieldname": "doc_amount",        "fieldtype": "Currency",     "width": 120},
        {"label": _("Currency"),       "fieldname": "doc_currency",      "fieldtype": "Data",         "width":  80},
        {"label": _("Contact"),        "fieldname": "doc_contact",       "fieldtype": "Link",         "options": "Contact",   "width": 150},
        {"label": _("Contact Name"),   "fieldname": "doc_contactname",   "fieldtype": "Data",         "width": 200},
        {"label": _("Prob (%)"),       "fieldname": "doc_probability",   "fieldtype": "Percent",      "width": 100},
        {"label": _("Quotation"),      "fieldname": "linked_quotation",  "fieldtype": "Link",         "options": "Quotation", "width": 120},
        {"label": _("Sales Order"),    "fieldname": "linked_sales_order","fieldtype": "Link",         "options": "Sales Order","width": 120},
        {"label": _("Opportunity"),    "fieldname": "linked_opportunity","fieldtype": "Link",         "options": "Opportunity","width": 120},
    ]

    # Single SQL block with CASE for Expired quotations
    data = frappe.db.sql("""
        SELECT
            'Opportunity' AS doc_type,
            opp.name AS doc_name,
            opp.owner AS doc_keyaccount,
            opp.transaction_date AS doc_date,
            opp.party_name AS doc_customer,
            opp.customer_name AS doc_customername,
            opp.opportunity_amount AS doc_amount,
            opp.currency AS doc_currency,
            opp.contact_person AS doc_contact,
            '' AS doc_contactname,
            NULL AS linked_quotation,
            NULL AS linked_sales_order,
            NULL AS linked_opportunity,
            opp.status AS doc_status
        FROM `tabOpportunity` opp
        WHERE opp.docstatus >= 0

        UNION ALL

        SELECT
            'Quotation' AS doc_type,
            quo.name AS doc_name,
            quo.sales_contact_name AS doc_keyaccount,
            quo.transaction_date AS doc_date,
            quo.party_name AS doc_customer,
            quo.customer_name AS doc_customername,
            quo.grand_total AS doc_amount,
            quo.currency AS doc_currency,
            quo.contact_person AS doc_contact,
            quo.contact_display AS doc_contactname,
            NULL, NULL, NULL,
            CASE
                WHEN quo.status = 'Open'
                 AND quo.new_valid_till < CURDATE()
                THEN 'Expired'
                ELSE quo.status
            END AS doc_status
        FROM `tabQuotation` quo
        WHERE quo.docstatus = 1

        UNION ALL

        SELECT
            'Sales Order' AS doc_type,
            so.name AS doc_name,
            so.sales_contact_name AS doc_keyaccount,
            so.transaction_date AS doc_date,
            so.customer AS doc_customer,
            so.customer_name AS doc_customername,
            so.grand_total AS doc_amount,
            so.currency AS doc_currency,
            so.contact_person AS doc_contact,
            so.contact_display AS doc_contactname,
            NULL AS linked_quotation,
            NULL AS linked_sales_order,
            NULL AS linked_opportunity,
            so.status AS doc_status
        FROM `tabSales Order` so
        WHERE so.docstatus = 1
        AND so.status != 'Completed'

        UNION ALL

        SELECT
            'Sales Invoice' AS doc_type,
            si.name AS doc_name,
            si.owner AS doc_keyaccount,
            si.posting_date AS doc_date,
            si.customer AS doc_customer,
            si.customer_name AS doc_customername,
            si.grand_total AS doc_amount,
            si.currency AS doc_currency,
            si.contact_person AS doc_contact,
            si.contact_display AS doc_contactname,
            NULL, NULL, NULL,
            si.status AS doc_status
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1
        AND si.status != 'Paid'

        ORDER BY doc_date DESC, doc_type, doc_name
    """, as_dict=True)

    # Map for quick lookup
    rows_map = {(r['doc_type'], r['doc_name']): r for r in data}

    # Attach links & probability (minimal Python overhead)
    for row in list(data):
        if row['doc_type'] == 'Sales Invoice':
            so_name = frappe.db.get_value('Sales Invoice Item',
                                          {'parent': row['doc_name']},
                                          'sales_order')
            if so_name:
                row['linked_sales_order'] = so_name
                rows_map.pop(('Sales Order', so_name), None)

        elif row['doc_type'] == 'Sales Order':
            quo_name = frappe.db.get_value('Sales Order Item',
                                           {'parent': row['doc_name']},
                                           'prevdoc_docname')
            if quo_name:
                row['linked_quotation'] = quo_name
                rows_map.pop(('Quotation', quo_name), None)

        elif row['doc_type'] == 'Quotation':
            prob = frappe.db.get_value('Quotation', row['doc_name'], 'probability')
            row['doc_probability'] = prob or 0
            opp_name = frappe.db.get_value('Quotation', row['doc_name'], 'opportunity')
            if opp_name:
                row['linked_opportunity'] = opp_name
                rows_map.pop(('Opportunity', opp_name), None)

        elif row['doc_type'] == 'Opportunity':
            prob = frappe.db.get_value('Opportunity', row['doc_name'], 'probability')
            row['doc_probability'] = prob or 0

    return columns, data
