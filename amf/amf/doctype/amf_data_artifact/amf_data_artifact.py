"""Immutable private data; keep the exact reviewed UTF-8 representation."""

import hashlib
import json

import frappe
from frappe.model.document import Document

from amf.amf.utils.data_artifact import content_bytes, validate_name


class AMFDataArtifact(Document):
    def validate(self):
        validate_name(self.artifact_name)
        payload = content_bytes(self.content)
        if self.artifact_name.endswith(".json"):
            json.loads(payload.decode("utf-8-sig"))
        if not self.is_new():
            previous = frappe.get_doc(self.doctype, self.name)
            if any(self.get(field) != previous.get(field)
                   for field in ("artifact_name", "content", "source_site")):
                raise frappe.ValidationError("Data artifacts are immutable; create a new named version")
        self.sha256 = hashlib.sha256(payload).hexdigest()
        self.byte_length = len(payload)
        self.source_site = self.source_site or frappe.local.site
