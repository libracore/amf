# -*- coding: utf-8 -*-
import frappe
from frappe import _

def execute(filters=None):
    """
    Returns columns and data for the Unified Transactions Report—
    follows the sales funnel: Opportunity → Quotation → Sales Order → Sales Invoice.
    Each record is enriched with its linked parent documents, and intermediate rows are removed.
    """

    columns = [
        {"label": _("Doc Type"),      "fieldname": "doc_type",     "fieldtype": "Data",                                  "width": 120},
        {"label": _("Name"),          "fieldname": "doc_name",     "fieldtype": "Dynamic Link", "options": "doc_type",   "width": 200},
        {"label": _("Date"),          "fieldname": "doc_date",     "fieldtype": "Date",                                  "width": 100},
        {"label": _("Customer"),      "fieldname": "doc_customer", "fieldtype": "Link",         "options": "Customer",   "width": 200},
        {"label": _("Name"),       "fieldname": "doc_customername",  "fieldtype": "Data",                              "width": 250},
        {"label": _("Total Amount"),  "fieldname": "doc_amount",   "fieldtype": "Currency",                              "width": 120},
        {"label": _("Currency"),      "fieldname": "doc_currency", "fieldtype": "Data",                                  "width":  80},
        {"label": _("Contact"),       "fieldname": "doc_contact",  "fieldtype": "Link",         "options": "Contact",    "width": 150},
        {"label": _("Name"),       "fieldname": "doc_contactname",  "fieldtype": "Data",                              "width": 200},
        {"label": _("Prob (%)"),     "fieldname": "doc_probability",      "fieldtype": "Percent",  "width": 100},
        {"label": _("Opportunity"),         "fieldname": "linked_opportunity",   "fieldtype": "Link",     "options": "Opportunity", "width": 120},
        {"label": _("Quotation"),           "fieldname": "linked_quotation",     "fieldtype": "Link",     "options": "Quotation",   "width": 120},
        {"label": _("Sales Order"),         "fieldname": "linked_sales_order",   "fieldtype": "Link",     "options": "Sales Order", "width": 120},
    ]

    data = frappe.db.sql("""
        SELECT
            'Opportunity'           AS doc_type,
            opp.name                AS doc_name,
            opp.transaction_date    AS doc_date,
            opp.party_name          AS doc_customer,
            opp.customer_name          AS doc_customername,
            opp.opportunity_amount  AS doc_amount,
            opp.currency            AS doc_currency,
            opp.contact_person      AS doc_contact,
            ''                      AS doc_contactname
          FROM `tabOpportunity`     AS opp
         WHERE opp.docstatus >= 0

        UNION ALL

        SELECT
            'Quotation'           AS doc_type,
            quo.name              AS doc_name,
            quo.transaction_date  AS doc_date,
            quo.customer          AS doc_customer,
            quo.customer_name          AS doc_customername,
            quo.grand_total       AS doc_amount,
            quo.currency          AS doc_currency,
            quo.contact_person    AS doc_contact,
            quo.contact_display AS doc_contactname
          FROM `tabQuotation` AS quo
         WHERE quo.docstatus = 1

        UNION ALL

        SELECT
            'Sales Order'         AS doc_type,
            so.name               AS doc_name,
            so.transaction_date   AS doc_date,
            so.customer           AS doc_customer,
            so.customer_name          AS doc_customername,
            so.grand_total        AS doc_amount,
            so.currency           AS doc_currency,
            so.contact_person     AS doc_contact,
            so.contact_display AS doc_contactname
          FROM `tabSales Order` AS so
         WHERE so.docstatus = 1

        UNION ALL

        SELECT
            'Sales Invoice'       AS doc_type,
            si.name               AS doc_name,
            si.posting_date       AS doc_date,
            si.customer           AS doc_customer,
            si.customer_name          AS doc_customername,
            si.grand_total        AS doc_amount,
            si.currency           AS doc_currency,
            si.contact_person     AS doc_contact,
            '' AS doc_contactname
          FROM `tabSales Invoice` AS si
         WHERE si.docstatus = 1

        ORDER BY
          doc_date DESC,
          doc_type,
          doc_name
    """, as_dict=1)

    # Initialize new link fields
    for row in data:
        row['linked_opportunity'] = None
        row['linked_quotation'] = None
        row['linked_sales_order'] = None
        row['doc_probability'] = None

    # Map for quick lookup
    rows_map = {(r['doc_type'], r['doc_name']): r for r in data}
    
        # Helper: fetch and assign probability
    def assign_probability(row, quo_name):
        prob = frappe.db.get_value('Quotation', quo_name, 'probability')
        if prob is not None:
            row['doc_probability'] = prob

    # 1) Attach Sales Orders to Sales Invoices, and remove SO rows
    for row in list(data):
        if row['doc_type'] == 'Sales Invoice':
            inv = row['doc_name']
            so_name = frappe.db.get_value('Sales Invoice Item',
                {'parent': inv}, 'sales_order')
            if so_name:
                row['linked_sales_order'] = so_name
                # Remove the Sales Order row
                so_key = ('Sales Order', so_name)
                so_row = rows_map.get(so_key)
                if so_row:
                    data.remove(so_row)
                    del rows_map[so_key]
    #             # Attach Quotation via Sales Order
    #             quo_name = frappe.db.get_value('Sales Order', so_name, 'quotation')
    #             if quo_name:
    #                 row['linked_quotation'] = quo_name
    #                 quo_key = ('Quotation', quo_name)
    #                 quo_row = rows_map.get(quo_key)
    #                 if quo_row:
    #                     data.remove(quo_row)
    #                     del rows_map[quo_key]
    #                 # Attach Opportunity via Quotation
    #                 opp_name = frappe.db.get_value('Quotation', quo_name, 'opportunity')
    #                 if opp_name:
    #                     row['linked_opportunity'] = opp_name
    #                     opp_key = ('Opportunity', opp_name)
    #                     opp_row = rows_map.get(opp_key)
    #                     if opp_row:
    #                         data.remove(opp_row)
    #                         del rows_map[opp_key]

    # 2) Attach Quotations and Opportunities to remaining Sales Orders
    for row in list(data):
        if row['doc_type'] == 'Sales Order':
            so_name = row['doc_name']
            quo_name = frappe.db.get_value('Sales Order Item', {'parent': so_name}, 'prevdoc_docname')
            if quo_name:
                row['linked_quotation'] = quo_name
                quo_key = ('Quotation', quo_name)
                quo_row = rows_map.get(quo_key)
                if quo_row:
                    data.remove(quo_row)
                    del rows_map[quo_key]
    #             # Link Opportunity
    #             opp_name = frappe.db.get_value('Quotation', quo_name, 'opportunity')
    #             if opp_name:
    #                 row['linked_opportunity'] = opp_name
    #                 opp_key = ('Opportunity', opp_name)
    #                 opp_row = rows_map.get(opp_key)
    #                 if opp_row:
    #                     data.remove(opp_row)
    #                     del rows_map[opp_key]

    # 3) Attach Opportunities to remaining Quotations
    for row in list(data):
        if row['doc_type'] == 'Quotation':
            quo_name = row['doc_name']
            assign_probability(row, quo_name)
            opp_name = frappe.db.get_value('Quotation', quo_name, 'opportunity')
            if opp_name:
                row['linked_opportunity'] = opp_name
                
                opp_key = ('Opportunity', opp_name)
                opp_row = rows_map.get(opp_key)
                if opp_row:
                    data.remove(opp_row)
                    del rows_map[opp_key]

    return columns, data
