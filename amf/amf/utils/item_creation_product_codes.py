"""Pure, deterministic Product-code suggestions within configuration prefixes."""
from amf.amf.utils import item_code_family as families


def occupied_product_codes(inventory, reservations, planned=()):
    return {families.canonical_chain_code(row.get("item_code") or row.get("name"), row.get("item_group"))
            for row in inventory} | set(reservations) | set(planned)


def suggest_product_code(expected, prefix, inventory, reservations, planned):
    preferred = expected["item_code"]
    # The unique engineering reference identifies body/head/syringe. Preserve
    # an existing Product's display name instead of guessing a missing head R&D label.
    same_identity = lambda row: (not row.get("disabled") and row.get("item_group") in families.PRODUCT_GROUPS
        and (row.get("reference_code") or "").strip().upper() == (expected.get("reference_code") or "").strip().upper())
    matches = sorted(row.get("item_code") or row.get("name") for row in inventory
                     if (row.get("item_code") or row.get("name") or "").startswith(prefix)
                     and same_identity(row) and families.ITEM_RE.fullmatch(row.get("item_code") or row.get("name") or ""))
    for code in [preferred] + matches:
        if code in matches and code not in planned:
            return code, "Reuse matching Product"
    occupied = occupied_product_codes(inventory, reservations, planned)
    if preferred not in occupied:
        return preferred, "Configuration prefix + head suffix"
    for suffix in families.iter_suffixes():
        code = prefix + suffix
        if code not in occupied:
            return code, "Next free code in configuration prefix; preferred code is occupied or retired"
    raise ValueError("No free Product codes remain in configuration prefix {0}.".format(prefix))
