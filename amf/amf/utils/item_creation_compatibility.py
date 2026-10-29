"""Versioned, explicit configurations supported by the Item Creation recipes.

The catalogue is evidence for these standard variants, not permission to infer
new combinations from the existence of a Body or Syringe Item.
"""
import re


RULE_VERSION = "2026-10-28.1"
LV_SYRINGES = ("2", "3", "4", "5", "8", "9", "D")
HV_SYRINGES = ("E", "F")
SYRINGE_REFERENCES = {"2": "S-50-P", "3": "S-100-P", "4": "S-100-U", "5": "S-250-P",
                      "8": "S-500-P", "9": "S-500-U",
                      "D": "S-1000-P", "E": "S-2500-P", "F": "S-5000-P"}
BODY_RULES = (
    ("511000", "RVM", "1", ("0",), "P200-O"),
    ("521000", "RVM", "2", ("0",), "P201-O"),
    ("551000", "LV", "5", LV_SYRINGES, "P100-O"),
    ("571000", "LV", "7", LV_SYRINGES, "P100-L"),
    ("591000", "LV", "9", LV_SYRINGES, "P110-O"),
    ("5B1000", "LV", "B", LV_SYRINGES, "P110-L"),
    ("561000", "HV", "6", HV_SYRINGES, "P101-O"),
    ("581000", "HV", "8", HV_SYRINGES, "P101-L"),
    ("5A1000", "HV", "A", HV_SYRINGES, "P111-O"),
    ("5C1000", "HV", "C", HV_SYRINGES, "P111-L"),
)
FAMILY_FLAGS = {"RVM": "rvm_check", "LV": "pump_check", "HV": "pump_hv_check"}
HEAD_TYPES = {
    "RVM": {"D", "DS", "O", "OS", "S", "B", "DA", "SA", "SL", "T", "SPLIT", "SPLITS"},
    "LV": {"D", "DS"},
    "HV": {"D", "DS"},
}


def has_hv_marker(head_name):
    return bool(re.search(r"(?:^|[-\s])HV(?:$|[-\s])", (head_name or "").upper()))


def configurations():
    result = []
    for body, family, motor, syringes, label in BODY_RULES:
        for token in syringes:
            syringe = "70" + token + "000" if family != "RVM" else ""
            result.append(dict(key=body + ":" + syringe, body=body, syringe=syringe,
                               family=family, motor=motor, token=token,
                               prefix="4" + motor + token, body_label=label))
    return result


CONFIGURATIONS = configurations()
BY_KEY = {row["key"]: row for row in CONFIGURATIONS}


def selection_key(row):
    return (row.get("body") or "").strip().upper() + ":" + (row.get("syringe") or "").strip().upper()


def checked(value):
    try:
        return int(value or 0) == 1
    except (TypeError, ValueError):
        return False


def allowed_families(head_name):
    return {"HV"} if has_hv_marker(head_name) else {"RVM", "LV"}


def head_requirement_error(head_name, rule):
    if rule["family"] not in allowed_families(head_name):
        return "{0} needs {1} head geometry; check the -HV designation.".format(
            rule["key"], "high-volume" if rule["family"] == "HV" else "standard")
    parts = (head_name or "").upper().split("-")
    head_type = parts[1] if len(parts) > 1 else ""
    if head_type not in HEAD_TYPES[rule["family"]]:
        return "Head type {0} has no standard {1} compatibility rule; define a reviewed engineering rule first.".format(
            head_type or "(custom)", rule["family"])
    return ""


def configuration_label(rule, syringe_reference=""):
    drive = " / HD" if rule["motor"] in ("9", "B", "A", "C") else ""
    label = rule["body_label"] + " (" + rule["family"] + drive + ")"
    return label + (" / " + syringe_reference if syringe_reference else "")


def validate_selections(doc):
    """Return explicit supported selections and field errors, without DB work."""
    selected, errors, seen = [], [], set()
    rows = doc.get("product_variants") or []
    if len(rows) > len(CONFIGURATIONS):
        return [], ["Too many product variants; select only supported configurations."]
    for row in rows:
        if not checked(row.get("selected")):
            continue
        key = selection_key(row)
        rule = BY_KEY.get(key)
        head_error = head_requirement_error(doc.get("head_name"), rule) if rule else ""
        if not rule:
            errors.append("Unsupported body/syringe combination: {0}.".format(key))
        elif key in seen:
            errors.append("Duplicate product configuration: {0}.".format(key))
        elif head_error:
            errors.append(head_error)
        elif not checked(doc.get(FAMILY_FLAGS[rule["family"]])):
            errors.append("Enable the {0} product family for {1}.".format(rule["family"], key))
        else:
            product_code = (row.get("product_code") or "").strip().upper()
            product_reference = (row.get("product_reference") or "").strip()
            if product_code and (not re.fullmatch(r"[0-9A-Z]{6}", product_code)
                                 or not product_code.startswith(rule["prefix"]) or product_code[-3:] == "000"):
                errors.append("Product code {0} must start with {1} and have three letters/digits other than 000.".format(
                    product_code, rule["prefix"]))
            elif product_reference and (len(product_reference) > 140 or re.search(r"[\x00-\x1f\x7f]", product_reference)):
                errors.append("Product Reference for {0} must be a single line of at most 140 characters.".format(key))
            elif product_reference and re.findall(r"30[0-9A-Z]{4}", product_reference.upper()) != [doc.get("head_code")]:
                errors.append("Product Reference for {0} must contain selected head code {1} exactly once and no other head code.".format(
                    key, doc.get("head_code") or "(select a head)"))
            else:
                selected.append(dict(rule, product_code=product_code, product_reference=product_reference))
        seen.add(key)
    for family, flag in FAMILY_FLAGS.items():
        if checked(doc.get(flag)) and not any(row["family"] == family for row in selected):
            errors.append("Select at least one supported {0} variant, or clear that family.".format(family))
    return selected, errors
