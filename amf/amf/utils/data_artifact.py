"""Private, immutable CSV/JSON data stored in the site database.

Artifact names are identifiers, never filesystem paths. Callers own transactions.
"""

import csv
import hashlib
import io
import json
import re
from contextlib import contextmanager
from uuid import uuid4

import frappe
from werkzeug.wrappers import Response


DOCTYPE = "AMF Data Artifact"
SELECTED_REFS = "bom_cost_old_vs_new_2026-10-12_updated.csv"
SELECTED_PROPOSAL = "bom_selected_61_recursive_reprice_proposal_2026-10-12.json"
MATERIAL_SNAPSHOT = "bom_material_reprice_proposal_2026-10-09.json"
MAX_BYTES = 16 * 1024 * 1024


def validate_name(name):
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,139}", name):
        raise ValueError("Use a database artifact name (up to 140 letters, digits, dots, dashes or underscores), not a path")
    if not name.endswith((".csv", ".json", ".txt")):
        raise ValueError("Data artifacts must be CSV, JSON or text")
    return name


def new_name(prefix, extension="csv"):
    return validate_name("{}-{}.{}".format(prefix, uuid4().hex[:12], extension))


def content_bytes(content):
    payload = content.encode("utf-8") if isinstance(content, str) else content
    if not isinstance(payload, bytes) or not payload or len(payload) > MAX_BYTES:
        raise ValueError("Artifact content must be nonempty UTF-8 text of at most 16 MiB")
    payload.decode("utf-8")  # reject unsupported encodings without modifying bytes
    return payload


def get_bytes(name, expected_sha256=None):
    validate_name(name)
    frappe.only_for("System Manager")
    doc = frappe.get_doc(DOCTYPE, name)
    doc.check_permission("read")
    payload = content_bytes(doc.content)
    digest = hashlib.sha256(payload).hexdigest()
    if digest != doc.sha256 or len(payload) != doc.byte_length:
        raise ValueError("Database artifact integrity check failed: {}".format(name))
    if expected_sha256 and digest != expected_sha256:
        raise ValueError("Reviewed artifact checksum differs: {}".format(name))
    return payload


def get_json(name, expected_sha256=None):
    return json.loads(get_bytes(name, expected_sha256).decode("utf-8-sig"))


def put(name, content, expected_sha256=None):
    """Create once, or verify an identical existing artifact; never overwrite."""
    validate_name(name)
    frappe.only_for("System Manager")
    payload = content_bytes(content)
    digest = hashlib.sha256(payload).hexdigest()
    if expected_sha256 and digest != expected_sha256:
        raise ValueError("Import checksum differs: {}".format(name))
    if frappe.db.exists(DOCTYPE, name):
        if get_bytes(name) != payload:
            raise ValueError("Artifact already exists with different content; use a new name: {}".format(name))
        return name
    frappe.get_doc({
        "doctype": DOCTYPE, "artifact_name": name,
        "content": payload.decode("utf-8"), "source_site": frappe.local.site,
    }).insert()
    # Check the persisted representation as well as the submitted content.
    get_bytes(name, digest)
    return name


@contextmanager
def csv_output(name, bom=False):
    """In-memory CSV output, persisted only after the entire write succeeds."""
    validate_name(name)
    frappe.only_for("System Manager")
    with io.StringIO(newline="") as output:
        if bom:
            output.write("\ufeff")
        yield output
        put(name, output.getvalue())


def put_csv(name, fields, rows):
    with csv_output(name) as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return name


@frappe.whitelist()
def download(name):
    """Authenticated download; no File record or public asset is created."""
    payload = get_bytes(name)
    response = Response(payload, content_type="application/octet-stream")
    response.headers["Content-Disposition"] = 'attachment; filename="{}"'.format(name)
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def download_url(name):
    validate_name(name)
    return "/api/method/amf.amf.utils.data_artifact.download?name=" + name
