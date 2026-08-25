# -*- coding: utf-8 -*-
# Copyright (c) 2026, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cstr


class AMFIssueProcess(Document):
	def validate(self):
		self.process_code = cstr(self.process_code).strip().upper()
		self.process_name = cstr(self.process_name).strip()

		if self.primary_owner and self.primary_owner == self.secondary_owner:
			frappe.throw(_("Primary Owner and Secondary Owner must be different users."))

