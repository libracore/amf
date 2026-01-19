import frappe
from frappe import _
from frappe.utils import cint


# If True: block when customer country cannot be determined (safer for VAT compliance)
STRICT_COUNTRY_REQUIRED = True


def _get_customer_country(customer: str, customer_address: str | None = None) -> str | None:
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


def validate_swiss_tva_on_sales_invoice(doc, method=None):
    print("On rentre ici Sales Invoice")
    """
    Hook this on Sales Invoice validate AND before_submit.

    Rule:
    - If customer country is Switzerland => must have a TVA/VAT line in Taxes.
    - If country cannot be determined => optionally block (STRICT_COUNTRY_REQUIRED).
    """
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


@frappe.whitelist()
def get_customer_country(customer: str, customer_address: str | None = None) -> str | None:
    """
    Whitelisted helper for the client script (UI) so you can pre-fill / cache country.
    """
    return _get_customer_country(customer, customer_address)
