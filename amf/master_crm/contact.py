# -*- coding: utf-8 -*-
# Copyright (c) 2024, libracore AG and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import get_url_to_form
from erpnextswiss.scripts.crm_tools import get_primary_customer_address
from frappe import _


@frappe.whitelist()
def get_header(contact=None):
    contact_doc = {}
    address_display = ""
    customer_url = ""
    customer_name = ""
    status = {
        'value': 'Lead',
        'options': 'Lead'
    }
    if contact and frappe.db.exists("Contact", contact):
        contact_doc = frappe.get_doc("Contact", contact)
        status['value'] = contact_doc.status
        if contact_doc.address:
            # fetch address from contact
            address_display = get_address_display(contact_doc.address)
        elif contact_doc.links and len(contact_doc.links) > 0:
            # fetch address from company
            for l in contact_doc.links:
                if l.link_doctype == "Customer":
                    customer = l.link_name
                    customer_url = get_url_to_form("Customer", customer)
                    customer_name = frappe.get_value(
                        "Customer", customer, "customer_name")
                    address = get_primary_customer_address(l.link_name)
                    if address:
                        address_display = get_address_display(address.name)
                    break
        if contact_doc.csat:
            csat = contact_doc.csat
        else:
            csat = "N/A"
        if contact_doc.nps:
            nps = contact_doc.nps
        else:
            nps = "N/A"
    # get status
    contact_fields = frappe.get_meta("Contact").as_dict().get('fields')
    for f in contact_fields:
        if f['fieldname'] == "status":
            status['options'] = f['options']

    html = frappe.render_template(
        "amf/templates/includes/contact_header.html",
        {
            'doc': contact_doc,
            'address_display': address_display,
            'customer_url': customer_url,
            'customer_name': customer_name,
            'status': status,
            'csat': csat,
            'nps': nps
        }
    )
    return html


def get_address_display(address):
    template = frappe.get_all("Address Template", filters={
                              'is_default': 1}, fields=['name', 'template'])
    if len(template) > 0:
        address_doc = frappe.get_doc("Address", address)
        address_display = frappe.render_template(
            template[0]['template'], address_doc.as_dict())
        return address_display
    else:
        return None


def before_save(self, method):
    check_unique_primary_contact(self)
    return


def validate(self, method):
    # prevent_duplicates(self)              # uncomment this to enable duplicate validation on save
    return


def prevent_duplicates(self):
    if self.email_id:
        other_contacts = frappe.db.sql("""
            SELECT `name` 
            FROM `tabContact`
            WHERE `email_id` = "{email_id}"
              AND `name` != "{name}";
            """.format(email_id=self.get("email_id"), name=self.get("name")), as_dict=True)
        if len(other_contacts) > 0:
            frappe.throw(_("Another contact with this email exists: {0}").format(
                other_contacts[0]['name']), _("Validation"))
    return


def check_unique_primary_contact(contact):
    # check if there is a linked customer
    customer = None
    if contact.get('links'):
        for l in contact.get('links'):
            if l.get("link_doctype") == "Customer":
                customer = l.get('link_name')

    if customer:
        # check if this customer has other linked primary contacts
        other_primary_contacts = frappe.db.sql("""
            SELECT `tabContact`.`name`
            FROM `tabContact`
            JOIN `tabDynamic Link` ON `tabDynamic Link`.`parent` = `tabContact`.`name` AND `tabDynamic Link`.`link_doctype` = "Customer"
            WHERE 
                `tabContact`.`is_primary_contact` = 1
                AND `tabDynamic Link`.`link_name` = "{customer}"
                AND `tabContact`.`name` != "{contact}";
            """.format(contact=contact.name, customer=customer), as_dict=True)

        if len(other_primary_contacts) > 0:
            # disable other primary
            for o in other_primary_contacts:
                frappe.db.set_value("Contact", o.get(
                    'name'), 'is_primary_contact', 0)
            frappe.db.commit()

    return


@frappe.whitelist()
def create_update_contact(first_name=None, last_name=None, phone=None, email=None, position=None):
    existing_contact = frappe.get_all(
        "Contact", filters={'email_id': email}, fields=['name'])

    if len(existing_contact) > 0:
        # update
        contact = frappe.get_doc("Contact", existing_contact[0]['name'])
        contact.update({
            'first_name': first_name or "",
            'last_name': last_name or "",
            'position': position or ""
        })
        contact.email_ids = []
        contact_phone_nos = []
        if email:
            contact.append("email_ids", {
                'email_id': email,
                'is_primary': 1
            })
        if phone:
            contact.append("phone_nos", {
                'phone': phone,
                'is_primary_phone': 1
            })
        contact.save()
        frappe.db.commit()
        return contact.name

    else:
        # create
        new_contact = frappe.get_doc({
            'doctype': 'Contact',
            'first_name': first_name or "",
            'last_name': last_name or "",
            'full_name': "{0} {1}".format(first_name or "", last_name or ""),
            'position': position or "",
            'status': 'Lead'
        })
        if email:
            new_contact.append("email_ids", {
                'email_id': email,
                'is_primary': 1
            })
        if phone:
            new_contact.append("phone_nos", {
                'phone': phone,
                'is_primary_phone': 1
            })
        new_contact.insert()
        frappe.db.commit()
        return new_contact.name


def set_contact_status(contact_names, status_label):
    """Helper function to bulk-update Contact status for a given set of contact names."""
    if not contact_names:
        return  # No contacts to update
    contacts_str = "', '".join(contact_names)
    frappe.db.sql(f"""
        UPDATE `tabContact`
        SET status = '{status_label}'
        WHERE name IN ('{contacts_str}')
    """)


def update_contact_statuses():
    """
    Once a week, update every Contact's status based on whether they appear in:
      - Quotation => 'Prospect'
      - Sales Order => 'Customer'
      - Purchase Order => 'Supplier'
    """

    # 1. Gather distinct contacts referenced in Quotations
    contacts_in_quotation = frappe.db.sql(
        """
        SELECT DISTINCT contact_person
        FROM `tabQuotation`
        WHERE contact_person IS NOT NULL
          AND contact_person != ''
        """,
        as_list=True
    )
    contacts_in_quotation = {row[0] for row in contacts_in_quotation}

    # 2a. Gather distinct contacts referenced in Sales Orders
    contacts_in_sales_order = frappe.db.sql(
        """
        SELECT DISTINCT contact_person
        FROM `tabSales Order`
        WHERE contact_person IS NOT NULL
          AND contact_person != ''
        """,
        as_list=True
    )
    contacts_in_sales_order = {row[0] for row in contacts_in_sales_order}

    # 2b. Gather distinct contacts referenced in Purchase Orders
    contacts_in_purchase_order = frappe.db.sql(
        """
        SELECT DISTINCT contact_person
        FROM `tabPurchase Order`
        WHERE contact_person IS NOT NULL
          AND contact_person != ''
        """,
        as_list=True
    )
    contacts_in_purchase_order = {row[0] for row in contacts_in_purchase_order}

    # (Optional) Default ALL contacts to 'Lead' or 'Suspect' – uncomment if needed
    # frappe.db.sql("""
    #     UPDATE `tabContact`
    #     SET status = 'Lead'
    # """)

    # Bulk-update statuses in a logical sequence:
    print("Prospect:", len(contacts_in_quotation))
    set_contact_status(contacts_in_quotation, "Prospect")

    print("Customer:", len(contacts_in_sales_order))
    set_contact_status(contacts_in_sales_order, "Customer")

    print("Supplier:", len(contacts_in_purchase_order))
    set_contact_status(contacts_in_purchase_order, "Supplier")

    # Commit changes if you’re not in a transaction
    frappe.db.commit()
