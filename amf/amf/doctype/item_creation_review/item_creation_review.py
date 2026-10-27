import frappe
from frappe import _
from frappe.model.document import Document


class ItemCreationReview(Document):
    def validate(self):
        if not getattr(frappe.local, "amf_item_creation_workflow_write", False):
            frappe.throw(_("Engineering review records can only be created through the review action and cannot be edited directly."))

    def on_trash(self):
        frappe.throw(_("Engineering review records cannot be deleted."))
