"""Resolve Frappe v12 document visibility before loading reporting facts."""

from collections import defaultdict

import frappe
from frappe.model.document import Document
from frappe.permissions import get_role_permissions, get_user_permissions

from .definitions import COMPANY


class Access:
    def __init__(self):
        self.user = frappe.session.user
        self.roles = set(frappe.get_roles())
        self.user_permissions = get_user_permissions(self.user)
        self.names_cache = {}
        self.field_cache = {}
        if self.user == "Guest" or not frappe.has_permission("Company", doc=COMPANY):
            raise frappe.PermissionError("Sales Analytics requires access to the reporting company.")

    def can_read(self, doctype, fields, child_fields=None):
        child_fields = child_fields or {}
        key = (doctype, fields, tuple(child_fields.items()))
        if key not in self.field_cache:
            self.field_cache[key] = frappe.has_permission(doctype, "read") and all(
                self._field_access(doctype, table, table_fields)
                for table, table_fields in [(doctype, fields), *child_fields.items()]
            )
        return self.field_cache[key]

    def _field_access(self, parent, doctype, fields):
        if self.user == "Administrator":
            return True
        levels = {0}
        for perm in frappe.get_meta(parent).permissions:
            if perm.role in self.roles and perm.read and not perm.if_owner:
                levels.add(perm.permlevel)
        meta = frappe.get_meta(doctype)
        for field in fields:
            definition = meta.get_field(field)
            if definition and (definition.permlevel or 0) not in levels:
                return False
        return True

    def _restricted_fields(self, meta):
        return [
            field.fieldname for field in meta.get_link_fields()
            if field.options in self.user_permissions and not field.ignore_user_permissions
        ]

    def _permission_links(self, doctype, company_scoped):
        meta = frappe.get_meta(doctype)
        fields = self._restricted_fields(meta)
        children = {}
        for table in meta.get_table_fields():
            links = self._restricted_fields(frappe.get_meta(table.options))
            if links:
                children[table.fieldname] = (table.options, links)
        restricted_parent = any(field != "company" or not company_scoped for field in fields)
        return fields, children, restricted_parent or bool(children) or doctype in self.user_permissions

    def _needs_document_check(self, doctype, company_scoped):
        if self.user == "Administrator":
            return False
        return bool(
            frappe.get_hooks("has_permission").get(doctype)
            or (self.user_permissions and self._permission_links(doctype, company_scoped)[2])
        )

    def _check_documents(self, doctype, names, company_scoped):
        if not names or not self._needs_document_check(doctype, company_scoped):
            return names
        if frappe.get_hooks("has_permission").get(doctype):
            return [name for name in names if frappe.has_permission(doctype, "read", doc=name)]

        # v12 list permissions omit child-link checks. Load only the fields the native
        # document permission checker needs and run it on each candidate.
        fields, children, _ = self._permission_links(doctype, company_scoped)
        parents = frappe.db.get_values(doctype, {"name": ["in", names]}, ["name", "owner", *fields], as_dict=True)
        available = {row.name: row for row in parents}
        for fieldname, (child, links) in children.items():
            rows = frappe.db.get_values(child, {
                "parent": ["in", names], "parenttype": doctype, "parentfield": fieldname,
            }, ["name", "idx", "parent", *links], as_dict=True)
            grouped = defaultdict(list)
            for row in rows:
                grouped[row.parent].append(row)
            for name, parent in available.items():
                parent[fieldname] = grouped[name]

        verified = []
        for name in names:
            if name in available:
                document = Document(dict(available[name], doctype=doctype))
                if frappe.has_permission(doctype, "read", doc=document):
                    verified.append(name)
        return verified

    def complete(self, doctype):
        """A conservative, filter-independent check for complete company visibility."""
        if self.user == "Administrator":
            return True
        perms = get_role_permissions(doctype)
        return bool(
            perms.get("read") and not perms.get("if_owner", {}).get("read")
            and not frappe.get_hooks("permission_query_conditions").get(doctype)
            and not self._needs_document_check(doctype, company_scoped=True)
        )

    def visible_names(self, doctype, filters):
        key = (doctype, tuple(filters))
        if key in self.names_cache:
            return self.names_cache[key]
        scoped = any(filter_[0] == "company" for filter_ in filters)
        names = []
        last_name = ""
        while True:
            rows = frappe.get_list(
                doctype, fields=["name"], filters=[list(value) for value in filters] + [["name", ">", last_name]],
                order_by="name asc", limit_page_length=500,
            )
            if not rows:
                break
            names.extend(self._check_documents(doctype, [row.name for row in rows], company_scoped=scoped))
            last_name = rows[-1].name
            if len(rows) < 500:
                break
        self.names_cache[key] = names
        return names

    def search_items(self, text, limit):
        fields = ("item_code", "item_name", "reference_code", "item_group", "disabled")
        if not self.can_read("Item", fields):
            raise frappe.PermissionError("Item search requires access to the Item fields.")
        return self._item_search(fields, text, limit)

    def _item_search(self, fields, text, limit):
        # Frappe applies its v12 permission query conditions and sharing rules here.
        pattern = "%" + text.replace("%", r"\%").replace("_", r"\_") + "%"
        rows = []
        last_name = ""
        while len(rows) < limit:
            page = frappe.get_list(
                "Item", fields=["name", *fields], filters=[["name", ">", last_name]],
                or_filters=[[field, "like", pattern] for field in fields[:4]],
                order_by="name asc", limit_page_length=100,
            )
            allowed = set(self._check_documents("Item", [row.name for row in page], company_scoped=False))
            rows.extend(row for row in page if row.name in allowed)
            if len(page) < 100:
                break
            last_name = page[-1].name
        rows.sort(key=lambda row: (row.item_code.casefold() != text.casefold(), row.item_code))
        return rows[:limit]
