from frappe.model.document import Document
from amf.amf.utils import monthly_inventory


class MonthlyInventoryCheck(Document):
    def autoname(self):
        self.name = monthly_inventory.check_name(self.company, self.period)

    def validate(self):
        monthly_inventory.validate_check(self)

    def on_trash(self):
        monthly_inventory.trash_check(self)
