from __future__ import unicode_literals

import random
import re
import string

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import cstr


TOKEN_LENGTH = 6
INTERNAL_SUFFIX = "AMF"
SUPPLIER_FALLBACK_SUFFIX = "SUP"
TOKEN_CHARS = string.ascii_uppercase + string.digits
_random = random.SystemRandom()


def sync_supplier_batch_custom_fields():
    create_custom_fields(
        {
            "Purchase Receipt Item": [
                {
                    "fieldname": "supplier_batch",
                    "fieldtype": "Data",
                    "label": "Supplier Batch",
                    "insert_after": "batch_no",
                    "allow_on_submit": 1,
                    "no_copy": 1,
                    "in_list_view": 1,
                    "columns": 2,
                }
            ],
            "Batch": [
                {
                    "fieldname": "supplier_batch",
                    "fieldtype": "Data",
                    "label": "Supplier Batch",
                    "insert_after": "supplier",
                    "allow_on_submit": 1,
                    "no_copy": 1,
                    "in_standard_filter": 1,
                }
            ],
            "Stock Entry Detail": [
                {
                    "fieldname": "auto_batch_no_generation",
                    "fieldtype": "Check",
                    "label": "Auto Batch No Generation",
                    "insert_after": "batch_no",
                    "default": "1",
                    "columns": 1,
                }
            ],
        },
        update=True,
    )


def make_internal_production_batch_id():
    return make_batch_id(suffix=INTERNAL_SUFFIX)


def make_supplier_receipt_batch_id(supplier=None):
    return make_batch_id(suffix=get_supplier_suffix(supplier))


def apply_amf_batch_autoname(doc, method=None):
    suffix = None

    if doc.get("reference_doctype") in ("Purchase Receipt", "Purchase Invoice"):
        suffix = get_supplier_suffix(doc.get("supplier"))
    elif doc.get("reference_doctype") == "Stock Entry":
        suffix = INTERNAL_SUFFIX

    if not suffix:
        return

    if _batch_id_has_suffix(doc.get("batch_id"), suffix):
        doc.name = doc.batch_id
        return

    doc.batch_id = make_batch_id(suffix=suffix)
    doc.name = doc.batch_id


def make_batch_id(suffix=None):
    suffix = sanitize_batch_suffix(suffix) or INTERNAL_SUFFIX
    for _attempt in range(50):
        batch_id = "{0} {1}".format(_random_token(), suffix)
        if not frappe.db.exists("Batch", batch_id):
            return batch_id

    frappe.throw("Unable to generate a unique Batch ID.")


def get_supplier_suffix(supplier=None):
    if not supplier:
        return SUPPLIER_FALLBACK_SUFFIX

    supplier_name = frappe.db.get_value("Supplier", supplier, "supplier_name") or supplier
    return sanitize_supplier_suffix(supplier_name) or SUPPLIER_FALLBACK_SUFFIX


def sanitize_supplier_suffix(value):
    letters = re.sub(r"[^A-Za-z]", "", cstr(value)).upper()
    if len(letters) >= 3:
        return letters[:3]

    return sanitize_batch_suffix(value)


def sanitize_batch_suffix(value):
    cleaned = re.sub(r"[^A-Za-z0-9]", "", cstr(value)).upper()
    return cleaned[:3]


def _random_token():
    return "".join(_random.choice(TOKEN_CHARS) for _idx in range(TOKEN_LENGTH))


def _batch_id_has_suffix(batch_id, suffix):
    batch_id = cstr(batch_id).strip().upper()
    suffix = sanitize_batch_suffix(suffix)
    if not batch_id or not suffix:
        return False

    parts = batch_id.split(" ")
    return len(parts) == 2 and len(parts[0]) == TOKEN_LENGTH and parts[1] == suffix


@frappe.whitelist()
def make_internal_production_batch_id_api():
    return make_internal_production_batch_id()


@frappe.whitelist()
def make_supplier_receipt_batch_id_api(supplier=None):
    return make_supplier_receipt_batch_id(supplier=supplier)


def patch_active_batch_custom_scripts():
    """Update site-level Custom Scripts that create batches in the browser."""
    patches = [
        (
            "Purchase Receipt-Client",
            "const uniqueSuffix = getFormattedDate();\n"
            "\t\t\tconst batchId = `${uniqueSuffix} ${row.item_code} ${frm.doc.supplier} ${frm.doc.purchase_order_ || \"\"}`.trim();",
            "const batchId = await getSupplierReceiptBatchId(frm.doc.supplier);",
            "getSupplierReceiptBatchId",
            "\nasync function getSupplierReceiptBatchId(supplier) {\n"
            "\tconst response = await frappe.call({\n"
            "\t\tmethod: \"amf.amf.utils.batch_naming.make_supplier_receipt_batch_id_api\",\n"
            "\t\targs: { supplier: supplier || \"\" }\n"
            "\t});\n"
            "\treturn response && response.message;\n"
            "}\n",
        ),
        (
            "Stock Entry-Client",
            "const uniqueSuffix = getFormattedDate();\n"
            "    const batchId = `${uniqueSuffix} ${row.item_code} AMF`;",
            "const batchId = await getInternalProductionBatchId();",
            "getInternalProductionBatchId",
            "\nasync function getInternalProductionBatchId() {\n"
            "\tconst response = await frappe.call({\n"
            "\t\tmethod: \"amf.amf.utils.batch_naming.make_internal_production_batch_id_api\"\n"
            "\t});\n"
            "\treturn response && response.message;\n"
            "}\n",
        ),
    ]

    updated = []
    skipped = []
    for script_name, old, new, helper_name, helper in patches:
        if not frappe.db.exists("Custom Script", script_name):
            skipped.append(script_name)
            continue

        doc = frappe.get_doc("Custom Script", script_name)
        script = doc.script or ""
        changed = False

        if old in script:
            script = script.replace(old, new)
            changed = True

        if helper_name not in script:
            script = script.replace("\nasync function createBatchNo", helper + "\nasync function createBatchNo")
            changed = True

        if script_name == "Purchase Receipt-Client":
            purchase_receipt_replacements = [
                (
                    "\t\t// If we already created a batch for this item_code, reuse that\n"
                    "\t\tif (createdBatches[row.item_code]) {\n"
                    "\t\t\trow.batch_no = createdBatches[row.item_code];\n"
                    "\t\t\tcontinue;\n"
                    "\t\t}",
                    "\t\tconst supplierBatch = (row.supplier_batch || \"\").trim();\n"
                    "\t\tconst batchKey = [row.item_code, supplierBatch].join(\"::\");\n\n"
                    "\t\t// If we already created a batch for this item + supplier batch, reuse that\n"
                    "\t\tif (createdBatches[batchKey]) {\n"
                    "\t\t\trow.batch_no = createdBatches[batchKey];\n"
                    "\t\t\tcontinue;\n"
                    "\t\t}",
                ),
                (
                    "const newBatch = await createBatchNo(row.item_code, batchId);",
                    "const newBatch = await createBatchNo(row.item_code, batchId, frm.doc.supplier, supplierBatch, frm.doc.doctype, frm.doc.name);",
                ),
                (
                    "createdBatches[row.item_code] = newBatchName;",
                    "createdBatches[batchKey] = newBatchName;",
                ),
                (
                    "async function createBatchNo(item_code, batch_id) {",
                    "async function createBatchNo(item_code, batch_id, supplier, supplier_batch, reference_doctype, reference_name) {",
                ),
                (
                    "\t\t\t\tdoctype: \"Batch\",\n"
                    "\t\t\t\titem: item_code,\n"
                    "\t\t\t\tbatch_id: batch_id\n"
                    "\t\t\t}",
                    "\t\t\t\tdoctype: \"Batch\",\n"
                    "\t\t\t\titem: item_code,\n"
                    "\t\t\t\tbatch_id: batch_id,\n"
                    "\t\t\t\tsupplier: supplier || \"\",\n"
                    "\t\t\t\tsupplier_batch: supplier_batch || \"\",\n"
                    "\t\t\t\treference_doctype: reference_doctype || \"Purchase Receipt\",\n"
                    "\t\t\t\treference_name: reference_name || \"\"\n"
                    "\t\t\t}",
                ),
            ]
            for old_text, new_text in purchase_receipt_replacements:
                if old_text in script and new_text not in script:
                    script = script.replace(old_text, new_text)
                    changed = True

        if script_name == "Stock Entry-Client":
            stock_entry_replacements = [
                (
                    "row.auto_batch_no_generation !== 1",
                    "Number(row.auto_batch_no_generation) !== 1",
                ),
                (
                    "    if (row.auto_batch_no_generation !== 1) {\n"
                    "        return;\n"
                    "    }",
                    "    if (row.auto_batch_no_generation !== 1) {\n"
                    "        return;\n"
                    "    }\n"
                    "    if (!row.t_warehouse || row.s_warehouse) {\n"
                    "        return;\n"
                    "    }",
                ),
                (
                    "    if (Number(row.auto_batch_no_generation) !== 1) {\n"
                    "        return;\n"
                    "    }",
                    "    if (Number(row.auto_batch_no_generation) !== 1) {\n"
                    "        return;\n"
                    "    }\n"
                    "    if (!row.t_warehouse || row.s_warehouse) {\n"
                    "        return;\n"
                    "    }",
                ),
                (
                    "const newBatch = await createBatchNo(row.item_code, batchId);",
                    "const newBatch = await createBatchNo(row.item_code, batchId, frm.doc.doctype, frm.doc.name);",
                ),
                (
                    "async function createBatchNo(item_code, batch_id) {",
                    "async function createBatchNo(item_code, batch_id, reference_doctype, reference_name) {",
                ),
                (
                    "                doctype: \"Batch\",\n"
                    "                item: item_code,\n"
                    "                batch_id: batch_id,\n"
                    "            }",
                    "                doctype: \"Batch\",\n"
                    "                item: item_code,\n"
                    "                batch_id: batch_id,\n"
                    "                reference_doctype: reference_doctype || \"Stock Entry\",\n"
                    "                reference_name: reference_name || \"\",\n"
                    "            }",
                ),
            ]
            for old_text, new_text in stock_entry_replacements:
                if old_text in script and new_text not in script:
                    script = script.replace(old_text, new_text)
                    changed = True

        if changed:
            doc.script = script
            doc.save(ignore_permissions=True)
            updated.append(script_name)
        else:
            skipped.append(script_name)

    if updated:
        frappe.db.commit()

    return {"updated": updated, "skipped": skipped}
