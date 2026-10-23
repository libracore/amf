from frappe.model.document import Document
from amf.amf.utils.monthly_inventory import validate_settings


class MonthlyInventorySettings(Document):
    def validate(self):
        validate_settings(self)
