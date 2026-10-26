"""Import the reviewed manufacturing inputs once, before the costing patch.

Only this migration reads packaged seed resources. Runtime tools use the DB.
Existing artifacts must match; edited data is never silently overwritten.
"""

import json
from pkgutil import get_data

import frappe

from amf.amf.utils import data_artifact as artifacts


RESOURCE_ROOT = "patches/data/private_bom_inputs/"


def execute():
    frappe.reload_doc("amf", "doctype", "amf_data_artifact", force=True)
    if frappe.local.site != "site1.local":
        return
    manifest = json.loads(get_data("amf", RESOURCE_ROOT + "manifest.json").decode("utf-8"))
    required = {artifacts.SELECTED_REFS, artifacts.SELECTED_PROPOSAL, artifacts.MATERIAL_SNAPSHOT}
    if len(manifest) != len(required) or {row["name"] for row in manifest} != required:
        raise ValueError("Reviewed BOM input manifest is incomplete")
    for entry in manifest:
        name = artifacts.validate_name(entry["name"])
        if frappe.db.exists(artifacts.DOCTYPE, name):
            payload = artifacts.get_bytes(name, entry["sha256"])
        else:
            payload = get_data("amf", RESOURCE_ROOT + name)
            artifacts.put(name, payload, expected_sha256=entry["sha256"])
        if len(payload) != entry["bytes"]:
            raise ValueError("Reviewed BOM input length differs: {}".format(name))
    # Validate the selector and its relationship to the reviewed proposal now.
    from amf.amf.report.bom_cost_breakdown.selected_bom_reprice import selected_refs
    if artifacts.get_json(artifacts.SELECTED_PROPOSAL)["selected_finished_items"] != selected_refs():
        raise ValueError("Reviewed proposal and selected Item list disagree")
    # Patch runner owns the transaction and Patch Log; no commit here.
