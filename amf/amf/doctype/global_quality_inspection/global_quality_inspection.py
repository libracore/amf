# -*- coding: utf-8 -*-
# Copyright (c) 2025, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from erpnext.stock.doctype.quality_inspection_template.quality_inspection_template \
	import get_template_details

class GlobalQualityInspection(Document):
    def get_item_specification_details(self):
        if not self.quality_inspection_template:
            self.quality_inspection_template = frappe.db.get_value('Item',
                                                                   self.item_code, 'quality_inspection_template')

        if not self.quality_inspection_template:
            return

        self.set('readings', [])
        parameters = get_template_details(self.quality_inspection_template)
        for d in parameters:
            child = self.append('readings', {})
            child.specification = d.specification
            child.value = d.value
            child.status = "Accepted"

    def get_quality_inspection_template(self):
        template = ''
        if self.bom_no:
            template = frappe.db.get_value(
                'BOM', self.bom_no, 'quality_inspection_template')

        if not template:
            template = frappe.db.get_value(
                'BOM', self.item_code, 'quality_inspection_template')

        self.quality_inspection_template = template
        self.get_item_specification_details()
