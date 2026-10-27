# -*- coding: utf-8 -*-
"""Allocate the final three characters once for an entire AMF head family.

tabSeries supplies the existing v12 transactional naming registry. A suffix row
is a permanent reservation; a companion row records its source's SHA-256 key.
The allocation mutex and reservation rows use InnoDB locks. No helper commits.
"""
from __future__ import unicode_literals

import hashlib
import itertools
import re
from contextlib import contextmanager

import frappe
from frappe import _


ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
COMPONENT_PREFIXES = ("10", "11", "20", "21", "30")
PRODUCT_GROUPS = ("Product", "Products")
STANDARD_PRODUCT_PREFIXES = tuple("4" + char for char in "123456789ABCD")
SUFFIX_RE = re.compile(r"^[0-9A-Z]{3}$")
ITEM_RE = re.compile(r"^[0-9A-Z]{6}$")
BASE_CODE_RE = re.compile(r"^([0-9A-Z]{6})(?:$|[-. ])")
REGISTRY_PREFIX = "AMF-IC-FAMILY:"
MUTEX_KEY = "AMF-IC-FAMILY-LOCK"
MEMBER_PREFIX = "AMF-IC-MEMBER:"


def normalize_suffix(suffix):
    suffix = str(suffix or "").strip().upper()
    if not SUFFIX_RE.match(suffix) or suffix == "000":
        raise ValueError(_("The shared head suffix must be three letters/digits other than 000."))
    return suffix


def validate_suffix(suffix):
    """Present pure-format validation failures through Frappe's document API."""
    try:
        return normalize_suffix(suffix)
    except ValueError as error:
        frappe.throw(str(error))


def canonical_chain_code(item_code, item_group=None):
    """Retired /xxxxxx and xxxxxx-P aliases still occupy the original suffix."""
    code = str(item_code or "").strip().lstrip("/").upper()
    match = BASE_CODE_RE.match(code)
    if not match:
        return None
    code = match.group(1)
    if code.startswith(COMPONENT_PREFIXES) or code.startswith("4") or item_group in PRODUCT_GROUPS:
        return code
    return None


def occupied_suffixes(existing_items):
    result = set()
    for row in existing_items or []:
        if isinstance(row, str):
            code = canonical_chain_code(row)
        else:
            code = canonical_chain_code(row.get("item_code"), row.get("item_group"))
        if code:
            result.add(code[-3:])
    return result


def iter_suffixes():
    """Retain decimal ordering, then use all remaining uppercase base-36 tokens."""
    for number in range(1, 1000):
        yield str(number).zfill(3)
    for chars in itertools.product(ALPHABET, repeat=3):
        suffix = "".join(chars)
        if not suffix.isdigit():
            yield suffix


def next_available_suffix(existing_items, reservations=None):
    blocked = occupied_suffixes(existing_items) | set(reservations or [])
    for suffix in iter_suffixes():
        if suffix not in blocked:
            return suffix
    raise ValueError(_("All three-character head-family suffixes are occupied or reserved."))


def get_chain_items():
    # No disabled filter: discontinued and renamed identifiers remain occupied.
    return frappe.db.sql(
        """SELECT item_code, item_group FROM `tabItem`
        WHERE item_code REGEXP '^/*(10|11|20|21|30|4)'
            OR item_group IN ('Product', 'Products')""",
        as_dict=True,
    )


def get_reservations(for_update=False):
    # A locking read sees reservations committed after an earlier v12 RR snapshot.
    rows = frappe.db.sql(
        """SELECT name FROM `tabSeries`
        WHERE name LIKE %s AND CHAR_LENGTH(name) = %s"""
        + (" FOR UPDATE" if for_update else ""),
        (REGISTRY_PREFIX + "%", len(REGISTRY_PREFIX) + 3),
    )
    return {row[0][-3:] for row in rows}


def suggest_suffix():
    return next_available_suffix(get_chain_items(), get_reservations())


def _owner_key(suffix, source):
    # Length stays below tabSeries.name's 100-character limit, even for long names.
    import json
    identity = json.dumps(list(source), ensure_ascii=True, separators=(",", ":"))
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return REGISTRY_PREFIX + suffix + ":" + digest


def is_reserved_for(suffix, source):
    return bool(frappe.db.sql("SELECT name FROM `tabSeries` WHERE name = %s", _owner_key(suffix, source)))


def _lock_allocation():
    frappe.db.sql("INSERT IGNORE INTO `tabSeries` (name, current) VALUES (%s, 0)", MUTEX_KEY)
    frappe.db.sql("SELECT name FROM `tabSeries` WHERE name = %s FOR UPDATE", MUTEX_KEY)


def reserve_suffix(suffix, source, continuation=False):
    """Claim a whole family for a saved request or an Item, in its transaction.

    continuation is only supplied after the caller verifies an existing family
    root. It never means that an arbitrary occupied suffix may be allocated anew.
    """
    suffix = validate_suffix(suffix)
    if not source or len(source) != 2 or not all(source):
        raise ValueError(_("A saved source is required to reserve a head-family suffix."))
    _lock_allocation()
    key, owner = REGISTRY_PREFIX + suffix, _owner_key(suffix, source)
    claims = frappe.db.sql(
        "SELECT name FROM `tabSeries` WHERE name IN (%s, %s) FOR UPDATE", (key, owner)
    )
    names = {row[0] for row in claims}
    if owner in names:
        return suffix
    if key in names and not continuation:
        frappe.throw(_("Head suffix {0} is reserved by another creation request. Refresh the suggestion.").format(suffix))
    if not continuation:
        # Reservations use a current read, even when the caller already read an
        # Item in a repeatable-read transaction before waiting for the mutex.
        if suffix in occupied_suffixes(get_chain_items()) or suffix in get_reservations(for_update=True):
            frappe.throw(_("Head suffix {0} is already used in the Product/component chain. Refresh the suggestion.").format(suffix))
    frappe.db.sql("INSERT IGNORE INTO `tabSeries` (name, current) VALUES (%s, 0)", key)
    frappe.db.sql("INSERT IGNORE INTO `tabSeries` (name, current) VALUES (%s, 0)", owner)
    return suffix


@contextmanager
def family_creation(source, suffix):
    previous = getattr(frappe.local, "amf_item_code_family", None)
    previous_state = getattr(frappe.local, "amf_item_code_family_state", None)
    frappe.local.amf_item_code_family = (tuple(source), normalize_suffix(suffix))
    frappe.local.amf_item_code_family_state = dict(verified=False, codes=None)
    try:
        yield
    finally:
        frappe.local.amf_item_code_family = previous
        frappe.local.amf_item_code_family_state = previous_state


def _existing_component_source(doc, code):
    if code[:2] not in ("11", "21"):
        return None
    component_code = code[0] + "0" + code[2:]
    values = frappe.db.get_value("Item", component_code,
        ["item_group", "item_name", "reference_code", "tag_raw_mat", "disabled"], as_dict=True)
    if not values or values.disabled or values.item_group != doc.get("item_group"):
        return None
    reference = (doc.get("reference_code") or "").strip()
    expected_reference = (values.reference_code or "").strip() + ".ASM"
    if (doc.get("item_name") != values.item_name or not values.reference_code
            or reference != expected_reference
            or (doc.get("tag_raw_mat") or "").strip() not in ("", (values.tag_raw_mat or "").strip())):
        frappe.throw(_("Sub-assembly {0} does not match component {1}. Review the existing family before reuse.").format(code, component_code))
    return ("Item", component_code)


def validate_existing_head_family(head_code):
    head = frappe.get_doc("Item", head_code)
    if not head.default_bom:
        frappe.throw(_("Head {0} needs a reviewed, submitted default BOM before creating Products.").format(head_code))
    pending, visited = [(head_code, head.default_bom)], set()
    while pending:
        code, bom_name = pending.pop()
        if (code, bom_name) in visited:
            continue
        visited.add((code, bom_name))
        bom = frappe.get_doc("BOM", bom_name)
        if bom.item != code or bom.docstatus != 1 or not bom.is_active:
            frappe.throw(_("Family Item {0} has no valid active submitted BOM. A reviewed replacement is required.").format(code))
        for row in bom.items:
            component = canonical_chain_code(row.item_code) or ""
            if not component.startswith(COMPONENT_PREFIXES):
                continue
            if component[-3:] != head_code[-3:]:
                frappe.throw(_("Family BOM {0} uses component {1} from another suffix. A reviewed replacement is required.").format(bom.name, row.item_code))
            child = frappe.get_doc("Item", row.item_code)
            if child.disabled:
                frappe.throw(_("Family component {0} is disabled. A reviewed replacement is required.").format(row.item_code))
            child_bom = row.get("bom_no") or child.default_bom
            if child_bom:
                pending.append((row.item_code, child_bom))


def _product_head_source(doc, code):
    if code[:2] not in STANDARD_PRODUCT_PREFIXES and doc.get("item_group") not in PRODUCT_GROUPS:
        return None
    references = re.findall(r"30[0-9A-Z]{4}", (doc.get("reference_code") or "").upper())
    if len(references) != 1 or references[0][-3:] != code[-3:]:
        frappe.throw(_("Product {0} must explicitly reference a head with shared suffix {1}.").format(code, code[-3:]))
    head = references[0]
    values = frappe.db.get_value("Item", head, ["item_group", "disabled"], as_dict=True)
    if not values or values.item_group != "Valve Head" or values.disabled:
        frappe.throw(_("Save an enabled Valve Head {0} before creating its Product variants.").format(head))
    validate_existing_head_family(head)
    return ("Item", head)


def validate_new_item_family(doc, method=None):
    """Server guard for normal Item insertion, including the separate Item form."""
    code = (doc.get("item_code") or "").strip().upper()
    canonical = canonical_chain_code(code, doc.get("item_group"))
    if not canonical:
        return
    if not ITEM_RE.match(code):
        frappe.throw(_("New managed Item codes must contain exactly six letters/digits. Historical aliases remain reserved."))
    doc.item_code = code
    suffix = validate_suffix(code[-3:])
    context = getattr(frappe.local, "amf_item_code_family", None)
    if context:
        source, expected_suffix = context
        if suffix != expected_suffix:
            frappe.throw(_("Item {0} must use the source request's shared head suffix {1}.").format(code, expected_suffix))
        state = getattr(frappe.local, "amf_item_code_family_state", None)
        if state is None or not state["verified"]:
            reserve_suffix(suffix, source)
            if state is not None:
                state["verified"] = True
                state["codes"] = {canonical_chain_code(row.get("item_code"), row.get("item_group"))
                                  for row in get_chain_items()}
        _reserve_member_code(code, state["codes"] if state is not None else None)
        return
    source = _existing_component_source(doc, code) or _product_head_source(doc, code)
    reserve_suffix(suffix, source or ("Item", code), continuation=bool(source))
    _reserve_member_code(code)


def _reserve_member_code(code, known_codes=None):
    # Retain exact code history too: deletion must not permit recreating an old
    # component or variant under an otherwise valid existing family owner.
    key = MEMBER_PREFIX + code
    retired_or_existing = code in known_codes if known_codes is not None else any(
        canonical_chain_code(row.get("item_code"), row.get("item_group")) == code for row in get_chain_items())
    if retired_or_existing or frappe.db.sql("SELECT name FROM `tabSeries` WHERE name = %s FOR UPDATE", key):
        frappe.throw(_("Item code {0} was already allocated. Its reservation is retained after deletion.").format(code))
    frappe.db.sql("INSERT INTO `tabSeries` (name, current) VALUES (%s, 0)", key)
    if known_codes is not None:
        known_codes.add(code)


def validate_new_bom_family(doc, method=None):
    """Check draft definitions and submission, preserving submitted revisions."""
    if not doc.get("__islocal") and doc.get("docstatus") != 0 and method != "before_submit":
        return
    code = doc.get("item") or ""
    if not ITEM_RE.match(code):
        return
    if code.startswith(COMPONENT_PREFIXES):
        for row in doc.items or []:
            part = canonical_chain_code(row.item_code) or ""
            if part.startswith(COMPONENT_PREFIXES) and part[-3:] != code[-3:]:
                frappe.throw(_("BOM for {0} uses component {1} from another head suffix. A reviewed replacement is required.").format(code, part))
    elif code.startswith("4") or frappe.db.get_value("Item", code, "item_group") in PRODUCT_GROUPS:
        heads = [canonical_chain_code(row.item_code) for row in doc.items or []
                 if (canonical_chain_code(row.item_code) or "").startswith("30")]
        if len(heads) != 1 or heads[0][-3:] != code[-3:]:
            frappe.throw(_("Product {0} must use exactly one head with suffix {1}.").format(code, code[-3:]))


@contextmanager
def atomic_family_creation():
    """Let the Frappe request own the transaction; hooks propagate failures.

    The flag suppresses implicit parent propagation and selects commit-free
    Item/BOM hooks. Database commit/rollback methods are never replaced.
    """
    previous = getattr(frappe.local, "amf_atomic_family_creation", False)
    frappe.local.amf_atomic_family_creation = True
    try:
        yield
    finally:
        frappe.local.amf_atomic_family_creation = previous
