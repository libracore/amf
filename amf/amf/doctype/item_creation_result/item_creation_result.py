import frappe
from frappe import _
from frappe.model.document import Document


class ItemCreationResult(Document):
    def validate(self):
        if not getattr(frappe.local, "amf_item_creation_workflow_write", False):
            frappe.throw(_("Execution result links can only be written by Item Creation and cannot be edited directly."))

    def on_trash(self):
        frappe.throw(_("Execution result links cannot be deleted."))

    def before_update_after_submit(self):
        self.validate()

    def before_cancel(self):
        frappe.throw(_("Execution result links follow their request and cannot be cancelled independently."))
