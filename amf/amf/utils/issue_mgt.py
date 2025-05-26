# my_app/api.py
import frappe
from frappe.utils import now_datetime

from amf.amf.utils.utilities import (
    _create_log_entry,
    _update_log_entry
)

@frappe.whitelist()
def run_issue_closing_date_batch():
    """
    One-time batch to set Issue.closing_date = Issue.resolution_date
    for all Closed Issues where closing_date is empty.
    Returns: { total, updated, log_id }
    """
    # 1) start a new log entry for this batch
    reference = f"[{now_datetime()}] Batch: Set Issue closing_date"
    start_msg = f"[{now_datetime()}] Batch started"
    log_id = _create_log_entry(start_msg, "Batch", reference)

    # 2) find all closed issues missing closing_date
    issues = frappe.get_all(
        "Issue",
        filters={
            "status": "Closed"
        },
        fields=["name", "resolution_date"]
    )

    total = len(issues)
    updated = 0

    # 3) process each
    for issue in issues:
        name = issue["name"]
        res_date = issue["resolution_date"]

        if res_date:
            frappe.db.set_value("Issue", name, "closing_date", res_date)
            msg = f"[{now_datetime()}] Issue {name}: closing_date set to {res_date}"
            updated += 1
        else:
            msg = f"[{now_datetime()}] Issue {name}: skipped (no resolution_date)"

        # 4) append to our batch log
        _update_log_entry(log_id, msg)

    # 5) commit once and write final summary
    frappe.db.commit()
    end_msg = (
        f"[{now_datetime()}] Batch completed. "
        f"Processed {total}, updated {updated}."
    )
    _update_log_entry(log_id, end_msg)

    return {
        "message": frappe._("Batch completed"),
        "total": total,
        "updated": updated,
        "log_id": log_id
    }
