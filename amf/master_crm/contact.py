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
    csat = 0
    nps = 0
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
        if contact_doc.nps:
            nps = contact_doc.nps
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


# def update_contact_statuses():
#     """
#     Once a week, update every Contact's status based on whether they appear in:
#       - Quotation => 'Prospect'
#       - Sales Order => 'Customer'
#       - Purchase Order => 'Supplier'
#     """

#     # 1. Gather distinct contacts referenced in Quotations
#     contacts_in_quotation = frappe.db.sql(
#         """
#         SELECT DISTINCT contact_person
#         FROM `tabQuotation`
#         WHERE contact_person IS NOT NULL
#           AND contact_person != ''
#         """,
#         as_list=True
#     )
#     contacts_in_quotation = {row[0] for row in contacts_in_quotation}

#     # 2a. Gather distinct contacts referenced in Sales Orders
#     contacts_in_sales_order = frappe.db.sql(
#         """
#         SELECT DISTINCT contact_person
#         FROM `tabSales Order`
#         WHERE contact_person IS NOT NULL
#           AND contact_person != ''
#         """,
#         as_list=True
#     )
#     contacts_in_sales_order = {row[0] for row in contacts_in_sales_order}

#     # 2b. Gather distinct contacts referenced in Purchase Orders
#     contacts_in_purchase_order = frappe.db.sql(
#         """
#         SELECT DISTINCT contact_person
#         FROM `tabPurchase Order`
#         WHERE contact_person IS NOT NULL
#           AND contact_person != ''
#         """,
#         as_list=True
#     )
#     contacts_in_purchase_order = {row[0] for row in contacts_in_purchase_order}

#     # (Optional) Default ALL contacts to 'Lead' or 'Suspect' – uncomment if needed
#     # frappe.db.sql("""
#     #     UPDATE `tabContact`
#     #     SET status = 'Lead'
#     # """)

#     # Bulk-update statuses in a logical sequence:
#     print("Prospect:", len(contacts_in_quotation))
#     set_contact_status(contacts_in_quotation, "Prospect")

#     print("Supplier:", len(contacts_in_purchase_order))
#     set_contact_status(contacts_in_purchase_order, "Supplier")
    
#     print("Customer:", len(contacts_in_sales_order))
#     set_contact_status(contacts_in_sales_order, "Customer")

#     # Commit changes if you’re not in a transaction
#     frappe.db.commit()

def update_contact_statuses():
    """
    Weekly job that bumps a Contact’s status according to its presence in
    business documents.

      • Quotation      → Prospect   (only if status ∈ {Suspect, Lead, Prospect})
      • Sales Order    → Customer   (only if status ∈ {Suspect, Lead, Prospect})
      • Purchase Order → Supplier   (always)
    """
    # ------------------------------------------------------------------
    # 0.  Common helper
    # ------------------------------------------------------------------
    def get_distinct_contacts(sql: str, params: tuple = ()) -> set[str]:
        """Run *sql* and return a set of single-column strings."""
        rows = frappe.db.sql(sql, params, as_list=True)
        return {row[0] for row in rows}

    # ------------------------------------------------------------------
    # 1.  Collect contacts in Quotations   ▸ Upgrade to Prospect
    # ------------------------------------------------------------------
    status_filter = ("Suspect", "Lead", "Prospect")          # keep sync with docstring!
    placeholders   = ", ".join(["%s"] * len(status_filter))  # → “%s, %s, %s”

    contacts_in_quotation = get_distinct_contacts(
        f"""
        SELECT DISTINCT q.contact_person
          FROM `tabQuotation` AS q
          JOIN `tabContact`  AS c ON c.name = q.contact_person
         WHERE q.contact_person IS NOT NULL            -- sanity
           AND q.contact_person != ''
           AND c.status IN ({placeholders})            -- ← new filter
        """,
        status_filter,
    )

    # ------------------------------------------------------------------
    # 2.  Collect contacts in Sales Orders ▸ Upgrade to Customer
    # ------------------------------------------------------------------
    contacts_in_sales_order = get_distinct_contacts(
        f"""
        SELECT DISTINCT so.contact_person
          FROM `tabSales Order` AS so
          JOIN `tabContact`     AS c  ON c.name = so.contact_person
         WHERE so.contact_person IS NOT NULL
           AND so.contact_person != ''
           AND c.status IN ({placeholders})
        """,
        status_filter,
    )

    # ------------------------------------------------------------------
    # 3.  Collect contacts in Purchase Orders ▸ Upgrade to Supplier
    #     (no status filter here)
    # ------------------------------------------------------------------
    contacts_in_purchase_order = get_distinct_contacts(
        """
        SELECT DISTINCT contact_person
          FROM `tabPurchase Order`
         WHERE contact_person IS NOT NULL
           AND contact_person != ''
        """
    )

    # ------------------------------------------------------------------
    # 4.  Bulk-update in order: Prospect → Supplier → Customer
    # ------------------------------------------------------------------
    print(f"Prospect  ◂ {len(contacts_in_quotation)} contacts")
    set_contact_status(contacts_in_quotation,      "Prospect")

    print(f"Supplier  ◂ {len(contacts_in_purchase_order)} contacts")
    set_contact_status(contacts_in_purchase_order, "Supplier")

    print(f"Customer  ◂ {len(contacts_in_sales_order)} contacts")
    set_contact_status(contacts_in_sales_order,    "Customer")

    frappe.db.commit()      # commit if not already inside a transaction

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def set_organization_flag(org_names: set[str], fieldname: str):
    """
    Bulk-update a boolean flag (`is_supplier` or `is_customer`) for a set of
    Organization names.
    """
    if not org_names:
        return
    orgs_str = "', '".join(org_names)
    frappe.db.sql(
        f"""
        UPDATE `tabCustomer`
           SET {fieldname} = 1
         WHERE name IN ('{orgs_str}')
        """
    )

# ---------------------------------------------------------------------------
# Scheduler job
# ---------------------------------------------------------------------------
def update_organization_flags():
    """
    Weekly job that marks Organizations as suppliers / customers based on the
    documents in which they appear.

      • Purchase Order → is_supplier
      • Sales Order    → is_customer
    """

    def _get_distinct_orgs(sql: str, params: tuple = ()) -> set[str]:
        """Utility: execute *sql* and return a set with the first column."""
        rows = frappe.db.sql(sql, params, as_list=True)
        return {row[0] for row in rows}

    # 1.  Organizations in Purchase Orders  ──────────────────────────────
    orgs_in_po = _get_distinct_orgs(
        """
        SELECT DISTINCT po.supplier
            FROM `tabPurchase Order` AS po
            JOIN `tabCustomer`      AS sup ON sup.name = po.supplier   -- ← ensure it exists
        WHERE po.supplier IS NOT NULL
            AND po.supplier != ''
            AND po.status NOT IN ('Cancelled', 'Draft')
        """
    )

    # 2. Organisations that are customers  ─────────────────────────────────
    orgs_in_so = _get_distinct_orgs(
        """
        SELECT DISTINCT so.customer
            FROM `tabSales Invoice` AS so
            JOIN `tabCustomer`    AS cust ON cust.name = so.customer   -- ← ensure it exists
        WHERE so.customer IS NOT NULL
            AND so.customer != ''
            AND so.status NOT IN ('Cancelled', 'Draft')
        """
    )

    # 3.  Bulk-update (supplier first, then customer)  ───────────────────
    print(f"is_supplier  ◂ {len(orgs_in_po)} organizations")
    set_organization_flag(orgs_in_po, "is_supplier")

    print(f"is_customer  ◂ {len(orgs_in_so)} organizations")
    set_organization_flag(orgs_in_so, "is_customer")

    frappe.db.commit()          # commit if outside an explicit transaction
