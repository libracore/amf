"""Read-only manufacturing plans shared by Item Creation preview and execution.

No function in this module inserts, saves, reserves a number, or commits.
The same dependency snapshot and recipe comparison are hashed for review and
rebuilt under row locks before submission.
"""
import hashlib
import json
import math
from collections import defaultdict

import frappe
from frappe.utils import cint

from amf.amf.utils import item_code_family as families
from amf.amf.utils import item_creation_compatibility as compatibility
from amf.amf.utils.item_learned_defaults import build_item_description
from amf.amf.utils.item_creation_recipes import component_definition, product_definition, standard_product_reference


PLAN_VERSION = 5
INPUT_FIELDS = (
    "head_check", "head_item", "head_code", "head_name", "head_rnd", "head_description",
    "plug_check", "plug_item", "plug_code", "plug_name", "plug_rnd",
    "plug_mat", "plug_acc", "plug_drawing", "seat_check", "seat_item", "seat_code", "seat_name",
    "seat_rnd", "seat_mat", "seat_pin_item", "seat_acc", "seat_drawing", "screw_type", "screw_quantity", "cap_type",
    "rvm_check", "pump_check", "pump_hv_check", "company", "default_warehouse",
    "plug_raw_material", "plug_raw_qty", "plug_raw_uom", "seat_raw_material", "seat_raw_qty",
    "seat_raw_uom", "replace_boms", "product_only",
)
ITEM_FIELDS = ("name", "item_name", "item_group", "reference_code", "description", "tag_raw_mat",
               "disabled", "default_bom", "stock_uom", "include_item_in_manufacturing", "modified")
BOM_FIELDS = ("name", "item", "docstatus", "is_active", "is_default", "company", "quantity", "uom",
              "with_operations", "modified")
MATERIAL_FIELDS = ("parent", "idx", "item_code", "qty", "uom", "stock_uom", "stock_qty",
                   "conversion_factor", "bom_no", "include_item_in_manufacturing")
SCRAP_FIELDS = ("parent", "idx", "item_code", "stock_qty", "stock_uom")


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def digest(value):
    return hashlib.sha256(encode(value).encode("utf-8")).hexdigest()


def inputs(doc):
    numeric = {"screw_quantity", "plug_acc", "seat_acc", "plug_raw_qty", "seat_raw_qty"}
    checks = {"rvm_check", "pump_check", "pump_hv_check", "replace_boms", "product_only"}
    values = {field: number(doc.get(field)) if field in numeric else cint(doc.get(field))
              if field in checks else str(doc.get(field) or "").strip() for field in INPUT_FIELDS}
    values["product_variants"] = sorted(
        [{"body": row.get("body"), "syringe": row.get("syringe") or "",
          "product_code": (row.get("product_code") or "").strip().upper(),
          "product_reference": (row.get("product_reference") or "").strip()}
         for row in doc.get("product_variants") or [] if cint(row.get("selected"))],
        key=lambda row: (row["body"] or "", row["syringe"]),
    )
    # Keep existing, non-amendment approvals stable when adding lifecycle metadata.
    if doc.get("amended_from"):
        values.update(amended_from=doc.amended_from, amendment_reason=(doc.get("amendment_reason") or "").strip())
    return values


def input_hash(doc):
    return digest(inputs(doc))


def number(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return 0.0
    return round(result, 9) if math.isfinite(result) else 0.0


class Catalogue:
    """Bulk dependency reads, cached only for the lifetime of one plan."""
    def __init__(self, lock=False):
        self.lock = lock
        self.items, self.boms = {}, {}
        self.materials, self.scraps = defaultdict(list), defaultdict(list)
        self.operations = defaultdict(list)
        self.other_boms = defaultdict(list)
        self._item_reads, self._bom_reads = set(), set()

    def rvm_bodies(self):
        return frappe.db.sql("""SELECT name, item_code, item_group, reference_code FROM `tabItem`
            WHERE item_group = 'Body' AND item_code REGEXP '^(511|521)[0-9A-Z]{3}$'"""
            + (" FOR UPDATE" if self.lock else ""), as_dict=True)

    def product_code_inventory(self, references=()):
        condition = " OR reference_code IN %s" if references else ""
        return frappe.db.sql("""SELECT name, item_code, item_group, item_name, reference_code, disabled
            FROM `tabItem` WHERE item_code REGEXP '^/*4' OR item_group IN ('Product', 'Products')"""
            + condition + (" FOR UPDATE" if self.lock else ""),
            (tuple(sorted(references)),) if references else None, as_dict=True)

    def reserved_product_codes(self):
        rows = frappe.db.sql("SELECT name FROM `tabSeries` WHERE name LIKE %s" + (" FOR UPDATE" if self.lock else ""),
                             families.MEMBER_PREFIX + "4%")
        return {row[0][len(families.MEMBER_PREFIX):] for row in rows}

    def rows(self, doctype, fields, key, names):
        if not names:
            return []
        # Identifiers are internal constants; values always use SQL parameters.
        return frappe.db.sql("SELECT {0} FROM `tab{1}` WHERE `{2}` IN %s{3}".format(
            ", ".join("`" + field + "`" for field in fields), doctype, key,
            " FOR UPDATE" if self.lock else ""), (tuple(sorted(names)),), as_dict=True)

    def load_items(self, names):
        names = set(filter(None, names)) - self._item_reads
        self._item_reads.update(names)
        for row in self.rows("Item", ITEM_FIELDS, "name", names):
            self.items[row.name] = dict(row)

    def load_boms(self, names):
        names = set(filter(None, names)) - self._bom_reads
        self._bom_reads.update(names)
        for row in self.rows("BOM", BOM_FIELDS, "name", names):
            self.boms[row.name] = dict(row)
        for row in self.rows("BOM Item", MATERIAL_FIELDS, "parent", names):
            self.materials[row.parent].append(dict(row))
        for row in self.rows("BOM Scrap Item", SCRAP_FIELDS, "parent", names):
            self.scraps[row.parent].append(dict(row))
        for row in self.rows("BOM Operation", ("parent", "idx", "operation", "workstation", "time_in_mins"), "parent", names):
            self.operations[row.parent].append(dict(row))

    def load_dependencies(self, names):
        self.load_items(names)
        pending = {self.items[name].get("default_bom") for name in names if name in self.items} - {None, ""}
        while pending:
            self.load_boms(pending)
            materials = [row for name in pending for row in self.materials[name]]
            self.load_items([row["item_code"] for row in materials] +
                            [row["item_code"] for name in pending for row in self.scraps[name]])
            children = {row["item_code"] for row in materials
                        if (families.canonical_chain_code(row["item_code"]) or "").startswith(families.COMPONENT_PREFIXES)}
            pending = ({self.items[name].get("default_bom") for name in children if name in self.items}
                       | {row.get("bom_no") for row in materials if row["item_code"] in children})
            pending -= self._bom_reads | {None, ""}
            if len(self._bom_reads) > 1000:
                raise ValueError("The dependency graph is too large; review the selected head BOMs.")
        existing = self.rows("BOM", ("name", "item", "docstatus"), "item", names)
        for row in existing:
            if row.docstatus < 2:
                self.other_boms[row.item].append(row.name)

    def parents(self, bom_names):
        rows = self.rows("BOM Item", ("parent", "item_code", "bom_no"), "bom_no", bom_names)
        headers = {row.name: row for row in self.rows("BOM", BOM_FIELDS, "name", {r.parent for r in rows})}
        return sorted([dict(bom=row.parent, item=headers[row.parent].item, child=row.item_code,
                            child_bom=row.bom_no, docstatus=headers[row.parent].docstatus)
                       for row in rows if row.parent in headers and headers[row.parent].docstatus < 2],
                      key=lambda row: (row["bom"], row["child"]))

    def raw_candidates(self, tags):
        if not tags:
            return []
        return frappe.db.sql("""SELECT name, item_name, tag_raw_mat, stock_uom
            FROM `tabItem` WHERE item_group = 'Raw Material' AND disabled = 0
            AND tag_raw_mat IN %s ORDER BY name""", (tuple(sorted(tags)),), as_dict=True)


def stock_row(item, qty, bom_no=None):
    return dict(item_code=item["name"], qty=number(qty), uom=item["stock_uom"],
                stock_uom=item["stock_uom"], stock_qty=number(qty), conversion_factor=1,
                bom_no=bom_no or "", include_item_in_manufacturing=cint(item.get("include_item_in_manufacturing", 1)))


def recipe_rows(rows, quantity=1, scrap=False):
    output = []
    for row in rows:
        if scrap:
            output.append(dict(item_code=row["item_code"], stock_qty=number(number(row.get("stock_qty")) / quantity),
                               stock_uom=row.get("stock_uom") or ""))
        else:
            output.append(dict(item_code=row["item_code"], qty=number(number(row.get("qty")) / quantity),
                uom=row.get("uom") or "", stock_uom=row.get("stock_uom") or "",
                stock_qty=number(number(row.get("stock_qty")) / quantity),
                conversion_factor=number(row.get("conversion_factor")), bom_no=row.get("bom_no") or "",
                include_item_in_manufacturing=cint(row.get("include_item_in_manufacturing", 1))))
    return sorted(output, key=encode)


def current_recipe(catalogue, name):
    header = catalogue.boms.get(name)
    if not header or number(header.get("quantity")) <= 0:
        return None
    quantity = number(header["quantity"])
    return dict(company=header["company"], uom=header["uom"],
                materials=recipe_rows(catalogue.materials[name], quantity),
                scraps=recipe_rows(catalogue.scraps[name], quantity, scrap=True),
                operations=sorted(catalogue.operations[name], key=encode))


def recipe_diff(before, after):
    """Keep all quantities/UOMs/links visible; no name-based recipe inference."""
    if before is None:
        return dict(before=None, after=after)
    return {field: {"before": before.get(field), "after": after.get(field)}
            for field in ("company", "uom", "materials", "scraps", "operations")
            if before.get(field) != after.get(field)}


class Planner:
    def __init__(self, doc, catalogue=None, lock=False):
        # Work on explicit inputs only; preview must not mutate its source Doc.
        self.doc = frappe._dict({field: doc.get(field) for field in INPUT_FIELDS})
        self.doc.update(dict(amended_from=doc.get("amended_from"), amendment_reason=doc.get("amendment_reason")))
        self.doc.product_variants = doc.get("product_variants") or []
        self.catalogue = catalogue or Catalogue(lock=lock)
        self.errors, self.warnings, self.actions = [], [], []
        self.by_code = {}
        self._validated_chains = set()
        self._legacy_components = set()
        self.product_suggestions = []
        self.suffix = (doc.get("head_code") or "")[-3:]

    def error(self, message, field=None, **details):
        self.errors.append(dict(message=message, field=field or "", **details))

    def enabled(self, code, group=None):
        row = self.catalogue.items.get(code)
        if not row or cint(row.get("disabled")):
            self.error("Item {0} is missing or disabled.".format(code))
            return None
        if group and row["item_group"] != group:
            self.error("Item {0} must belong to {1}.".format(code, group))
            return None
        return row

    def bom_valid(self, code, name):
        bom = self.catalogue.boms.get(name)
        if (not bom or bom["item"] != code or cint(bom["docstatus"]) != 1
                or not cint(bom["is_active"]) or number(bom.get("quantity")) <= 0
                or bom["company"] != self.doc.get("company")):
            self.error("Item {0} needs an active submitted BOM for the selected company ({1}).".format(code, name or "none"))
            return False
        return True

    def validate_existing_chain(self, code, path=(), bom_name=None):
        if code in path:
            self.error("BOM cycle: {0}.".format(" -> ".join(path + (code,))))
            return
        item = self.enabled(code)
        if not item:
            return
        canonical = families.canonical_chain_code(code, item["item_group"]) or ""
        if canonical[-3:] != self.suffix and self.doc.get("head_check") == "Yes":
            self.error("Component {0} does not share head suffix {1}; define a reviewed replacement.".format(code, self.suffix))
            return
        if canonical[-3:] != self.suffix:
            self._legacy_components.add(code)
        name = bom_name or item.get("default_bom")
        if (code, name) in self._validated_chains:
            return
        if not self.bom_valid(code, name):
            return
        for row in self.catalogue.materials[name]:
            child = self.enabled(row["item_code"])
            if child:
                if (number(row.get("qty")) <= 0 or number(row.get("stock_qty")) <= 0
                        or number(row.get("conversion_factor")) <= 0):
                    self.error("BOM {0} has invalid quantities for {1}; propose a reviewed replacement.".format(name, child["name"]))
                elif row.get("stock_uom") != child.get("stock_uom"):
                    if (self.doc.get("head_check") == "No" and row.get("uom") == child.get("stock_uom")
                            and number(row.get("conversion_factor")) == 1
                            and number(row.get("stock_qty")) == number(row.get("qty"))):
                        self.warnings.append("Preserved BOM {0} records an old stock-UOM label for {1}. Its quantity is already in current stock UOM {2}; review the pinned revision. No historical BOM will be rewritten.".format(name, child["name"], child["stock_uom"]))
                    else:
                        self.error("BOM {0} has an inconsistent stock UOM for {1}; propose a reviewed replacement.".format(name, child["name"]))
            if child and (families.canonical_chain_code(child["name"], child["item_group"]) or "").startswith(families.COMPONENT_PREFIXES):
                self.validate_existing_chain(child["name"], path + (code,), row.get("bom_no"))
        self._validated_chains.add((code, name))

    def add(self, data, materials=None, scraps=None, preserve=False):
        code = data["item_code"]
        for field in ("item_code", "item_name", "reference_code", "reference_name", "tag_raw_mat"):
            if len(str(data.get(field) or "")) > 140:
                self.error("{0} on Item {1} exceeds the v12 field length of 140 characters.".format(field, code))
        if code in self.by_code:
            self.error("The plan contains duplicate Item {0}.".format(code))
            return
        existing = self.catalogue.items.get(code)
        action = dict(item=data, item_action="reuse" if existing else "create", bom_action="none",
                      materials=[], scraps=[], existing_bom="", diff={})
        if existing:
            if cint(existing["disabled"]) or any((existing.get(key) or "") != (data.get(key) or "")
                    for key in ("item_group", "item_name", "reference_code", "tag_raw_mat", "stock_uom") if key in data):
                self.error("Item {0} has a different identity or is disabled. Review its Item master separately.".format(code))
        default = (existing or {}).get("default_bom")
        if preserve:
            self.validate_existing_chain(code)
            action.update(bom_action="reuse", existing_bom=default,
                          proposed=current_recipe(self.catalogue, default),
                          materials=recipe_rows(self.catalogue.materials[default]),
                          scraps=recipe_rows(self.catalogue.scraps[default], scrap=True))
        elif materials is not None:
            prepared = []
            for row in materials:
                child_code = row.get("item_code")
                child_action = self.by_code.get(child_code)
                child = self.catalogue.items.get(child_code)
                if not child and child_action:
                    child = dict(name=child_code, stock_uom=child_action["item"].get("stock_uom", "Nos"))
                elif child:
                    child = self.enabled(child_code)
                if not child:
                    self.error("Required material {0} is missing for {1}.".format(child_code or "(empty)", code))
                    continue
                if number(row.get("qty")) <= 0:
                    self.error("Set a positive quantity for {0} in {1}.".format(child_code, code))
                bom_no = ""
                if child_action and child_action["bom_action"] in ("create", "replace"):
                    bom_no = "@new:" + child_code
                elif child_action:
                    bom_no = child_action["existing_bom"] or ""
                elif child.get("default_bom"):
                    bom_no = child["default_bom"]
                    self.bom_valid(child_code, bom_no)
                    if (families.canonical_chain_code(child_code, child.get("item_group")) or "").startswith(families.COMPONENT_PREFIXES):
                        self.validate_existing_chain(child_code)
                elif child_code.startswith(families.COMPONENT_PREFIXES):
                    self.error("Manufactured component {0} has no submitted production BOM.".format(child_code))
                prepared.append(stock_row(child, row.get("qty"), bom_no))
            prepared_scraps = []
            for row in scraps or []:
                child = self.enabled(row.get("item_code"))
                if child:
                    if number(row.get("qty")) <= 0:
                        self.error("Scrap quantity must be positive for {0}.".format(code))
                    prepared_scraps.append(dict(item_code=child["name"], stock_qty=number(row["qty"]), stock_uom=child["stock_uom"]))
            proposed = dict(company=self.doc.get("company"), uom=data.get("stock_uom", "Nos"),
                            materials=recipe_rows(prepared), scraps=recipe_rows(prepared_scraps, scrap=True), operations=[])
            before = current_recipe(self.catalogue, default) if default else None
            difference = recipe_diff(before, proposed)
            action.update(materials=proposed["materials"], scraps=proposed["scraps"], proposed=proposed,
                          existing_bom=default or "", diff=difference,
                          bom_action="replace" if default and difference else "reuse" if default else "create")
            if default:
                self.bom_valid(code, default)
                if difference and not cint(self.doc.get("replace_boms")):
                    self.error("BOM {0} differs. Enable reviewed BOM replacements and review the complete changes.".format(default), "replace_boms")
            elif self.catalogue.other_boms.get(code):
                self.error("Item {0} has existing BOMs but no selected default. Select its reviewed default first.".format(code))
        self.actions.append(action)
        self.by_code[code] = action

    def component(self, group):
        if self.doc.get(group + "_check") != "Yes":
            code = self.doc.get(group + "_item") or self.doc.get(group + "_code")
            item = self.enabled(code, "Plug" if group == "plug" else "Valve Seat")
            if item:
                if (not code.startswith(("10", "11") if group == "plug" else ("20", "21"))
                        or (self.doc.get("head_check") == "Yes" and code[-3:] != self.suffix)):
                    self.error("Selected {0} must share head suffix {1}.".format(group, self.suffix))
            return code
        if not all(self.doc.get(group + suffix) for suffix in ("_name", "_code", "_rnd", "_mat")):
            self.error("Set the {0} name, R&D reference and material tag.".format(group))
            return None
        if number(self.doc.get(group + "_acc")) < 0:
            self.error("The {0} accessory quantity cannot be negative; enter zero explicitly for a design without this accessory.".format(group))
        if group == "seat" and number(self.doc.get("seat_acc")) > 0 and not self.doc.get("seat_pin_item"):
            self.error("Select the pin Item for the seat sub-assembly.", "seat_pin_item")
        data, assembly, upper_materials = component_definition(self.doc, group)
        raw_code = self.doc.get(group + "_raw_material")
        raw = self.enabled(raw_code, "Raw Material") if raw_code else None
        if not raw_code:
            self.error("Select the exact {0} raw-material stock Item.".format(group), group + "_raw_material")
        qty = number(self.doc.get(group + "_raw_qty"))
        if qty <= 0:
            self.error("Enter a positive {0} raw-material quantity per component.".format(group), group + "_raw_qty")
        elif round(qty, 6) != qty or qty >= 1e12:
            self.error("The {0} stock quantity must fit the v12 BOM field: at most six decimal places and less than 1e12.".format(group), group + "_raw_qty")
        if raw:
            if raw.get("tag_raw_mat") != self.doc.get(group + "_mat"):
                self.error("Raw stock {0} does not match the {1} material tag.".format(raw_code, group))
            if not raw.get("stock_uom") or self.doc.get(group + "_raw_uom") != raw["stock_uom"]:
                self.error("Use the current stock UOM {0} for {1}; convert the input quantity explicitly.".format(raw.get("stock_uom"), raw_code), group + "_raw_uom")
        for item in (data, assembly):
            item.pop("valuation_rate", None)
            item.update(stock_uom="Nos", item_defaults=[dict(company=self.doc.get("company"),
                        default_warehouse=self.doc.get("default_warehouse"))])
            item["description"] = build_item_description(item["item_code"], item["item_name"], item["item_group"],
                                                          item["item_type"], item.get("reference_code"))
            if not item.get("item_name") or not item.get("reference_code") or not self.doc.get(group + "_mat"):
                self.error("Set the {0} name, R&D reference and material tag.".format(group))
        self.add(data, [dict(item_code=raw_code, qty=qty)])
        self.add(assembly, upper_materials)
        return assembly["item_code"]

    def build(self):
        product_only = cint(self.doc.get("product_only"))
        code = (self.doc.get("head_item") if self.doc.get("head_check") == "No" else self.doc.get("head_code")) or ""
        code = code.strip().upper()
        self.doc["head_code"] = code
        self.suffix = code[-3:]
        rules = compatibility.configurations(self.catalogue.rvm_bodies() if cint(self.doc.get("rvm_check")) else ())
        by_key = {row["key"]: row for row in rules}
        # Collect only explicitly selected supported configurations before IO.
        selections = [dict(by_key[compatibility.selection_key(row)],
                           product_code=(row.get("product_code") or "").strip().upper())
                      for row in self.doc.get("product_variants") or []
                      if cint(row.get("selected")) and compatibility.selection_key(row) in by_key]
        valid_code = bool(families.ITEM_RE.match(code) and code.startswith("30") and code[-3:] != "000")
        if not valid_code:
            self.error("Select or define a six-character Valve Head code starting with 30, with a nonzero shared suffix.", "head_code")
        needed = {code, self.doc.get("head_item")}
        if selections:
            needed.add(self.doc.get("screw_type"))
        if any(row["family"] == "RVM" for row in selections):
            needed.add(self.doc.get("cap_type"))
        if any(row["family"] != "RVM" for row in selections):
            needed.add("RVM.1204")
        if any(row["motor"] in ("7", "B", "8", "C") for row in selections):
            needed.update(["C100", "C101"])
        if any(row["motor"] in ("7", "B") for row in selections):
            needed.add("T100")
        for group, prefix in (() if product_only else (("plug", "10"), ("seat", "20"))):
            needed.update([self.doc.get(group + "_item"), self.doc.get(group + "_code"), self.doc.get(group + "_raw_material")])
            if valid_code:
                needed.update([prefix + code[2:], prefix[0] + "1" + code[2:]])
                if self.doc.get(group + "_check") == "Yes":
                    self.doc[group + "_code"] = prefix + code[2:]
                    if number(self.doc.get(group + "_acc")) > 0:
                        needed.add("SPL.3013" if group == "plug" else self.doc.get("seat_pin_item"))
        for row in selections:
            needed.update([row["body"], row["syringe"], row.get("product_code") or row["prefix"] + self.suffix])
        self.catalogue.load_dependencies(set(filter(None, needed)))
        head = self.catalogue.items.get(self.doc.get("head_item"))
        if self.doc.get("head_check") == "No" and head:
            for target, source in (("head_code", "name"), ("head_name", "item_name"),
                                   ("head_rnd", "reference_code"), ("head_description", "description")):
                self.doc[target] = head.get(source)
            if head["name"] != code or head["item_group"] != "Valve Head" or head["disabled"]:
                self.error("Select an enabled Valve Head and refresh its definition.")
        selections, selection_errors = compatibility.validate_selections(self.doc, rules)
        for error in selection_errors:
            self.error(error, "product_variants")
        if self.doc.get("head_check") not in ("Yes", "No"):
            self.error("Choose whether to create or reuse the Valve Head.", "head_check")
        if product_only:
            if self.doc.get("head_check") != "No" or any(self.doc.get(group + "_check") == "Yes" for group in ("plug", "seat")):
                self.error("Create Products Only requires an existing head and cannot create a seat or plug.", "product_only")
            if not selections:
                self.error("Select at least one Product configuration.", "product_variants")
        if not self.doc.get("company") or not self.doc.get("default_warehouse"):
            self.error("Select a company and manufacturing warehouse.", "company")
        else:
            warehouse = frappe.db.get_value("Warehouse", self.doc.get("default_warehouse"), ["company", "is_group", "disabled"], as_dict=True)
            if not warehouse or warehouse.company != self.doc.get("company") or warehouse.is_group or warehouse.disabled:
                self.error("Select an enabled stock warehouse belonging to the selected company.", "default_warehouse")
        if valid_code:
            if product_only:
                if head:
                    self.validate_existing_chain(code)
                else:
                    self.error("Select the existing Valve Head Item.", "head_item")
            elif self.doc.get("head_check") == "Yes" or cint(self.doc.get("replace_boms")):
                plug, seat = self.component("plug"), self.component("seat")
                head_data = dict(item_code=code, item_name=self.doc.get("head_name"), item_group="Valve Head",
                    item_type="Sub-Assembly", reference_code=self.doc.get("head_rnd"), stock_uom="Nos",
                    description=self.doc.get("head_description") or build_item_description(code, self.doc.get("head_name"), "Valve Head"),
                    is_purchase_item=0, is_sales_item=1, country_of_origin="Switzerland",
                    item_defaults=[dict(company=self.doc.get("company"), default_warehouse=self.doc.get("default_warehouse"))])
                if not head_data["item_name"] or (self.doc.get("head_check") == "Yes" and not head_data["reference_code"]):
                    self.error("Set the head name and R&D reference.")
                self.add(head_data, [dict(item_code=plug, qty=1), dict(item_code=seat, qty=1)])
            elif head:
                if any(self.doc.get(group + "_check") == "Yes" for group in ("plug", "seat")):
                    self.error("Enable reviewed BOM replacements before defining new parts for an existing head.", "replace_boms")
                for group, item_group in (("plug", "Plug"), ("seat", "Valve Seat")):
                    selected = self.doc.get(group + "_item")
                    actual = {row["item_code"] for row in self.catalogue.materials.get(head.get("default_bom"), [])
                              if self.catalogue.items.get(row["item_code"], {}).get("item_group") == item_group}
                    if selected and selected not in actual:
                        self.error("Selected {0} {1} differs from the existing head BOM. Enable Propose Replacement BOMs to review that change, or use Create Products Only to preserve the head.".format(group, selected), "replace_boms")
                self.add(dict(item_code=code, item_name=head["item_name"], item_group=head["item_group"],
                              reference_code=head.get("reference_code"), stock_uom=head["stock_uom"]), preserve=True)
            else:
                self.error("Select the existing Valve Head Item.", "head_item")
            # Variants can share a Product prefix even in a new head family.
            suggest_codes = self.doc.get("head_check") == "No" or len({row["prefix"] for row in selections}) < len(selections)
            check_codes = selections and (suggest_codes or any(row.get("product_code") or row.get("product_reference") for row in selections))
            expected_references = {row.get("product_reference") or standard_product_reference(self.doc["head_code"], row["body_label"],
                compatibility.SYRINGE_REFERENCES[row["token"]] if row["syringe"] else "", row)
                for row in selections}
            inventory = self.catalogue.product_code_inventory(expected_references) if check_codes else []
            reservations = self.catalogue.reserved_product_codes() if check_codes else set()
            from amf.amf.utils.item_creation_product_codes import occupied_product_codes, suggest_product_code
            occupied_codes = occupied_product_codes(inventory, reservations)
            planned_codes = set()
            planned_references = {}
            entered_codes = {row["product_code"] for row in selections if row.get("product_code")}
            prepared_products = []
            for row in selections:
                body, syringe = self.enabled(row["body"], "Body"), None
                if row["syringe"]:
                    syringe = self.enabled(row["syringe"], "Syringe")
                if not body or (row["syringe"] and not syringe):
                    continue
                if (body.get("reference_code") or "").strip() != row["body_label"]:
                    self.error("Body {0} no longer matches configuration reference {1}; review the compatibility rule.".format(row["body"], row["body_label"]))
                    continue
                if syringe:
                    reference = syringe.get("reference_code") or ""
                    if reference != compatibility.SYRINGE_REFERENCES[row["token"]]:
                        self.error("Syringe {0} no longer matches the approved volume/material reference {1}.".format(
                            syringe["name"], compatibility.SYRINGE_REFERENCES[row["token"]]))
                        continue
                data, materials, scraps = product_definition(self.doc, row, body, syringe)
                default_reference = standard_product_reference(self.doc["head_code"], row["body_label"],
                    syringe["reference_code"] if syringe else "", row)
                reason = "Entered Product code" if row.get("product_code") else "Configuration prefix + head suffix"
                if suggest_codes and not row.get("product_code"):
                    try:
                        code_suggestion, reason = suggest_product_code(data, row["prefix"], inventory, reservations,
                            planned_codes | entered_codes, legacy_prefixes=row.get("legacy_prefixes", ()))
                    except ValueError as error:
                        self.error(str(error), "product_variants")
                        continue
                    data["item_code"] = code_suggestion
                    data["reference_name"] = code_suggestion + ": " + data["item_name"]
                planned_codes.add(data["item_code"])
                prepared_products.append((row, data, materials, scraps, default_reference, reason))
            # Load newly selected existing Products and their BOM graphs in one batch.
            self.catalogue.load_dependencies({data["item_code"] for _, data, _, _, _, _ in prepared_products})
            for row, data, materials, scraps, default_reference, reason in prepared_products:
                if (row.get("product_code") and data["item_code"] in occupied_codes
                        and data["item_code"] not in self.catalogue.items):
                    self.error("Product code {0} is retired or reserved. Leave the override blank for an available suggestion.".format(data["item_code"]), "product_variants")
                existing_product = self.catalogue.items.get(data["item_code"])
                if (existing_product and existing_product.get("item_group") in families.PRODUCT_GROUPS
                        and (existing_product.get("reference_code") or "").strip().upper()
                        == (data.get("reference_code") or "").strip().upper()):
                    data["item_group"] = existing_product["item_group"]
                    data["item_name"] = existing_product["item_name"]
                    data["reference_code"] = existing_product["reference_code"]
                    data["reference_name"] = data["item_code"] + ": " + data["item_name"]
                reference_owners = [item.get("name") or item.get("item_code") for item in inventory
                    if (item.get("reference_code") or "").strip().upper() == (data.get("reference_code") or "").strip().upper()
                    and (item.get("name") or item.get("item_code")) != data["item_code"]]
                if reference_owners:
                    self.error("Product reference {0} already belongs to {1}. Enter a different Product Reference for this configuration, or review that Item master.".format(
                        data["reference_code"], ", ".join(sorted(reference_owners))), "product_variants",
                        reference_conflict=dict(configuration=row["key"], reference=data["reference_code"], owners=sorted(reference_owners)))
                reference_key = data["reference_code"].strip().upper()
                if reference_key in planned_references:
                    self.error("Product reference {0} is also used by another selected configuration ({1}). Enter a different Product Reference.".format(
                        data["reference_code"], planned_references[reference_key]), "product_variants",
                        reference_conflict=dict(configuration=row["key"], reference=data["reference_code"], owners=[]))
                planned_references[reference_key] = row["key"]
                if row.get("product_reference") and row["product_reference"] != default_reference:
                    self.warnings.append("Product {0} uses entered reference {1}; generated configuration reference is {2}.".format(
                        data["item_code"], data["reference_code"], default_reference))
                if row.get("review_note"):
                    self.warnings.append("{0}: {1}".format(data["item_code"], row["review_note"]))
                self.product_suggestions.append(dict(body=row["body"], syringe=row["syringe"],
                    product_code=data["item_code"], reason=reason,
                    product_reference=data["reference_code"], default_reference=default_reference))
                self.add(data, materials, scraps)
        if not self.actions:
            self.error("The request has no Items to create or verify.")
        replacements = {action["existing_bom"] for action in self.actions if action["bom_action"] == "replace"}
        parents = self.catalogue.parents(replacements)
        if replacements:
            self.warnings.append("Replacement BOMs become the selected defaults. Existing parent BOM revisions retain their original child links.")
        if self._legacy_components:
            self.warnings.append("Existing head {0} reuses independently numbered components: {1}. Submitted component revisions are preserved.".format(
                self.doc.get("head_code"), ", ".join(sorted(self._legacy_components))))
        dependencies = dict(items=sorted(self.catalogue.items.values(), key=lambda row: row["name"]),
                            boms=sorted(self.catalogue.boms.values(), key=lambda row: row["name"]))
        plan = dict(version=PLAN_VERSION, rule_version=compatibility.RULE_VERSION, inputs=inputs(self.doc),
                    product_only=bool(product_only), actions=self.actions, errors=self.errors, warnings=self.warnings, product_suggestions=self.product_suggestions,
                    affected_parents=parents, dependencies=dependencies,
                    dependency_recipes={name: current_recipe(self.catalogue, name) for name in sorted(self.catalogue.boms)})
        plan["fingerprint"] = digest(plan)
        plan["input_hash"] = input_hash(self.doc)
        plan["ready"] = not bool(self.errors)
        plan["summary"] = dict(items=len(self.actions),
            new_items=sum(row["item_action"] == "create" for row in self.actions),
            new_boms=sum(row["bom_action"] == "create" for row in self.actions),
            replacement_boms=sum(row["bom_action"] == "replace" for row in self.actions),
            reused_boms=sum(row["bom_action"] == "reuse" for row in self.actions))
        shown = {action["existing_bom"] for action in self.actions}
        plan["dependency_boms"] = [dict(name=name, item=header["item"], recipe=current_recipe(self.catalogue, name))
                                   for name, header in sorted(self.catalogue.boms.items()) if name not in shown]
        tags = {self.doc.get(group + "_mat") for group in ("plug", "seat")} - {None, ""}
        plan["raw_material_candidates"] = [] if product_only else [dict(row) for row in self.catalogue.raw_candidates(tags)]
        return plan


def build_plan(doc, lock=False, catalogue=None):
    return Planner(doc, catalogue=catalogue, lock=lock).build()
