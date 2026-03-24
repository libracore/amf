# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import re

DEFAULT_COST_CENTER = "General - AMF21"

ITEM_CODE_PATTERN = re.compile(r"^GX[A-Z]{2}-(\d+)$")

# Primary mapping by first digit in the numeric suffix (per business rule order).
DIGIT_COST_CENTER_MAP = {
    "1": "4100 - Supply Chain Operations - AMF21",
    "2": "6200 - Research & Development - AMF21",
    "3": "6300 - Marketing - AMF21",
    "4": "6400 - Sales - AMF21",
    "5": "6500 - Management and Administration - AMF21",
}

# Secondary mapping by first two digits of account-like suffixes.
PREFIX2_COST_CENTER_MAP = {
    "41": "4100 - Supply Chain Operations - AMF21",
    "62": "6200 - Research & Development - AMF21",
    "63": "6300 - Marketing - AMF21",
    "64": "6400 - Sales - AMF21",
    "65": "6500 - Management and Administration - AMF21",
}


def _resolve_cost_center_from_item_code(item_code):
    if not item_code:
        return None

    match = ITEM_CODE_PATTERN.match(item_code)
    if not match:
        return None

    numeric_suffix = match.group(1)
    if len(numeric_suffix) >= 2 and numeric_suffix[:2] in PREFIX2_COST_CENTER_MAP:
        return PREFIX2_COST_CENTER_MAP[numeric_suffix[:2]]

    return DIGIT_COST_CENTER_MAP.get(numeric_suffix[0])


def apply_default_cost_center(doc, method=None):
    """
    Set a default cost center on Purchase Invoice and item rows.
    For item rows, resolve from item code pattern GX + 2 letters + '-' + digits.
    Only fills missing values.
    """
    if not getattr(doc, "cost_center", None):
        doc.cost_center = DEFAULT_COST_CENTER

    items = getattr(doc, "items", None) or []
    for row in items:
        if not getattr(row, "cost_center", DEFAULT_COST_CENTER):
            row.cost_center = _resolve_cost_center_from_item_code(
                getattr(row, "item_code", None)
            ) or DEFAULT_COST_CENTER
