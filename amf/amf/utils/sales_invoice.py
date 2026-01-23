from xml.dom.minidom import Document
import frappe
from frappe import _
from frappe.utils import cint
from typing import Optional


# If True: block when customer country cannot be determined (safer for VAT compliance)
STRICT_COUNTRY_REQUIRED = True


def _get_customer_country(customer: str, customer_address: Optional[str] = None) -> Optional[str]:
    """
    Returns the customer's country using:
    1) Sales Invoice.customer_address if present
    2) Otherwise the most relevant linked Address (primary first, then latest modified)
    """
    if customer_address:
        return frappe.db.get_value("Address", customer_address, "country")

    # Find an address linked to the Customer through Dynamic Link
    row = frappe.db.sql(
        """
        SELECT dl.parent
        FROM `tabDynamic Link` dl
        INNER JOIN `tabAddress` a ON a.name = dl.parent
        WHERE dl.parenttype = 'Address'
          AND dl.link_doctype = 'Customer'
          AND dl.link_name = %s
        ORDER BY IFNULL(a.is_primary_address, 0) DESC, a.modified DESC
        LIMIT 1
        """,
        (customer,),
        as_list=True,
    )
    if row and row[0] and row[0][0]:
        return frappe.db.get_value("Address", row[0][0], "country")

    return None


def _has_swiss_vat_line(doc) -> bool:
    """
    Minimal, pragmatic detection of TVA/VAT lines in Sales Invoice taxes.

    Assumption: your VAT/TVA accounts or descriptions contain one of:
    - "tva" (FR)
    - "vat" (EN)
    - "mwst" (DE, common in CH)
    Adjust keywords to match your chart of accounts.
    """
    keywords = ("tva", "vat", "mwst")

    for t in (doc.get("taxes") or []):
        account_head = (t.account_head or "").strip().lower()
        description = (t.description or "").strip().lower()

        if any(k in account_head for k in keywords) or any(k in description for k in keywords):
            return True

    return False

def _coerce_to_document(doc) -> Document:
    """
    Accepts:
      - Frappe Document (hooks)
      - dict (already parsed)
      - JSON string (common when passed via frappe.call args)
    Returns:
      - Frappe Document
    """
    # If it's already a Document, keep it
    if isinstance(doc, Document):
        return doc

    # If it's a JSON string, parse it into a dict
    if isinstance(doc, str):
        doc = frappe.parse_json(doc)

    # If it's a dict, try to load/finalize a Document
    if isinstance(doc, dict):
        # Best case: doctype + name -> fetch from DB (authoritative)
        doctype = doc.get("doctype")
        name = doc.get("name")
        if doctype and name:
            return frappe.get_doc(doctype, name)

        # Otherwise, if it's a full doc dict (rare but possible)
        if doctype:
            return frappe.get_doc(doc)

    raise TypeError(f"Unsupported doc type: {type(doc)}")

@frappe.whitelist()
def validate_swiss_tva_on_sales_invoice(doc, method=None):
    """
    Hook this on Sales Invoice validate AND before_submit.

    Rule:
    - If customer country is Switzerland => must have a TVA/VAT line in Taxes.
    - If country cannot be determined => optionally block (STRICT_COUNTRY_REQUIRED).
    """
    doc = _coerce_to_document(doc)
    print(doc.doctype)
    
    if doc.doctype != "Sales Invoice":
        return

    if not doc.customer:
        return

    country = _get_customer_country(doc.customer, doc.customer_address)
    print(country)

    if not country:
        if STRICT_COUNTRY_REQUIRED:
            frappe.msgprint(
                title=_("Customer Country Missing"),
                msg=_(
                    "Cannot determine the customer's country (no Customer Address / linked Address). "
                    "Please set a customer address before validating the Sales Invoice."
                ),
                indicator="red",
                raise_exception=frappe.ValidationError,
            )
        return

    if country != "Switzerland":
        return

    # If you want to allow explicit exemptions, uncomment and implement one:
    # if cint(getattr(doc, "vat_exempt", 0)) == 1:
    #     return

    if not _has_swiss_vat_line(doc):
        frappe.msgprint(
            title=_("Missing Swiss VAT (TVA)"),
            msg=_(
                "Customer country is Switzerland, but no TVA/VAT (MWST) line was found in the Taxes table. "
                "Please add the correct TVA before validating/submitting this Sales Invoice."
            ),
            indicator="red",
            raise_exception=frappe.ValidationError,
        )


# @frappe.whitelist()
# def _get_customer_country(customer: str, customer_address: Optional[str] = None) -> Optional[str]:
#     """
#     Whitelisted helper for the client script (UI) so you can pre-fill / cache country.
#     """
#     return _get_customer_country(customer, customer_address)
