from frappe import _

from amf.amf.utils.item_creation_traceability import result_history


def execute(filters=None):
    columns = [
        ("request", "Request", "Item Creation", 180),
        ("status", "Request Status", None, 105),
        ("amended_from", "Amended From", "Item Creation", 180),
        ("head_code", "Head", "Item", 100),
        ("item_code", "Item", "Item", 120),
        ("item_action", "Item Action", None, 90),
        ("bom", "BOM Revision", "BOM", 180),
        ("bom_action", "BOM Action", None, 90),
        ("replaced_bom", "Previous BOM Revision", "BOM", 180),
        ("reviewed_by", "Reviewed By", "User", 150),
    ]
    columns = [dict(fieldname=field, label=_(label), fieldtype="Link" if target else "Data",
                    options=target, width=width) for field, label, target, width in columns]
    columns.append(dict(fieldname="completed_at", label=_("Completed At"), fieldtype="Datetime", width=160))
    return columns, result_history(filters)
