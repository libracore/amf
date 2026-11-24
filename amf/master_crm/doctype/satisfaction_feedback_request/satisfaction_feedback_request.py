from frappe.model.document import Document

from amf.master_crm.feedback import request_name


class SatisfactionFeedbackRequest(Document):
    def autoname(self):
        self.name = request_name(self.source_doctype, self.source_name)
