# Assignment alerts for manually registered machining Work Orders

Implemented 2026-11-03 for Frappe / ERPNext V12. Recipient:
`martin.barraud@amf.ch`.

## Result

On the first successful save of a manually created Work Order for a six-character
`10xxxx` or `20xxxx` Item, add an **Open ToDo assignment** for Martin using
`frappe.desk.form.assign_to.add` with `notify=1`. The task contains the Work Order,
Item, quantity and creator and asks Martin to review and plan machining. Frappe's
standard assignment email includes a clickable Work Order link. The assignment
also appears in the Work Order sidebar, Martin's ToDo list and the document's
assignment history.

This happens when the new draft is saved, rather than waiting for submission.
Subsequent edits or submission do not create another task or another email.
Existing assignees are preserved; no assignment rule is created or cleared.
Existing Work Orders are not assigned retrospectively.

The existing uppercase alphanumeric suffix rule is retained: `100040`, `200040`,
`100ABC` and `20AB34` qualify. `110040`, `210040`, other families, longer codes,
lowercase suffixes, whitespace and invalid suffixes do not qualify.

Native V12 assignment behavior applies:

- The assignee is `ToDo.owner`; this version does not use `allocated_to`.
- Notification mail is queued through the site's outgoing mail settings, not sent
  immediately in the insert hook. Delivery depends on the email queue and SMTP.
- V12 suppresses assignment emails for self-assignment. If Martin creates the
  Work Order himself, his Open ToDo is still created and shown in the sidebar.
- Native assignment follows the document and can share read access with Martin
  if necessary. This does not grant manufacturing write/submit permissions.
- If Martin already has any ToDo referencing the Work Order, including one that
  is Closed or Cancelled, the hook does not create/reopen it or resend an alert.
- The configured recipient must remain an enabled System User. If this validation
  fails, the Work Order save fails with an explanatory message; it does not
  silently create an unassigned order. Disable the hook with the switch below
  while correcting the account if needed. Native V12 can retain the ToDo when
  outgoing email is unavailable; the assignment remains the primary alert.

## What counts as manual creation

Manual creation is determined from the actual request action. Relying only on
`owner` or `auto_gen` is inaccurate here: schedulers run as Administrator, legacy
automatic orders may lack `auto_gen`, and a user can duplicate an automated draft
in Desk while retaining that field.

Included entry points:

| User action | Request path |
| --- | --- |
| First Save of a Work Order in Desk, including Duplicate/Amend | `frappe.desk.form.save.savedocs`; the request document must itself be a Work Order for the same production Item |
| Existing AMF Sales Order Create Work Orders dialog | `amf.amf.utils.work_order_creation.make_work_orders` |
| Explicit AMF sub-assembly Work Order creation | `amf.amf.utils.work_order_creation.create_work_orders` |
| Standard ERPNext Sales Order Create Work Orders | `erpnext.selling.doctype.sales_order.sales_order.make_work_orders` |
| User starts a new Work Order from the existing planning page | `amf.www.planification.planification.start_planning` |
| Production Plan Make Work Order action | V12 `runserverobj` (including its dotted aliases), method `make_work_order`, with a Production Plan request document |

Excluded: scheduled stock/reorder/Sales Order planners, the legacy stock-shortage
API, recursive automatic Sales Order generation, imports, patches, installation,
migrations, Guests and generic API/integration inserts. Saving another DocType
does not classify a nested Work Order insertion as manual. New custom manual
creation actions should be added explicitly to `MANUAL_CREATION_COMMANDS` with
a regression test; unknown entry points do not send alerts accidentally.

## Implementation and validation

- `amf/amf/utils/manual_work_order_assignment.py`: server-only, non-whitelisted
  insert handler, request classification and assignment creation.
- `amf/hooks.py`: retains QR generation as the first Work Order `after_insert`
  handler and adds the assignment handler second. The native ToDo updates
  `_assign` directly; the handler reloads the Work Order so the initial response
  immediately shows Martin without another Work Order save.
- `amf/amf/utils/test_manual_work_order_assignment.py`: 19 new unit tests covering
  first-save assignment/notification, both families, exact/alphanumeric codes,
  supported manual actions, automatic/unknown paths, nested inserts, imports and
  other maintenance contexts, duplicated planner drafts, duplicate prevention,
  recipient validation, HTML escaping, hook order and the disable switch.

No schema migration, Custom Field, scheduled task, backfill or framework/core
edit is needed. The committed magnet-stock planning implementation and its
rollback package are unchanged.

The site's recipient was verified enabled and of type System User. There are
three enabled outgoing accounts and no enabled Work Order Assignment Rules at
verification time. Credentials were not exported or modified.

**50 unit tests passed**: the 19 new tests, 27 stock-coverage regressions and four
existing estimated-time tests. Three integration cases used actual V12 Work
Order inserts and native ToDo/comment/follow behavior: manual `100040`, manual
`200040`, and automatic `100040`. Each manual case produced one task and one
intercepted native email call. Another save and replay of the hook produced no
duplicate. The automatic case produced neither task nor email.

Integration commits were blocked and every temporary document was rolled back.
QR file creation and realtime publication were mocked, and **all outgoing email
was intercepted**. No test messages were delivered and no test Work Orders or
assignments remain. The normal mail transport was not tested by sending to Martin.

Reproduce the site-free checks from the bench root:

```sh
env/bin/python -m unittest amf.amf.utils.test_manual_work_order_assignment amf.amf.utils.test_work_order_creation -v
```

Detailed local evidence, baseline hooks, manifest and the rollback-only native
integration harness are in:

```text
/home/libracore/frappe-bench/reports/manual_machining_assignment_2026-11-03/
```

The running bench uses the development `bench serve --port 8000` process with
automatic reload and `developer_mode=1`. Its web child restarted after both
runtime source files changed, so the new hook is loaded for subsequent requests.
No scheduler/worker restart or manual run of either stock planner was performed.

## Disable or undo

Disable future assignments without removing source:

```sh
cd /home/libracore/frappe-bench
bench --site site1.local set-config manual_machining_work_order_alerts_enabled 0
```

The default is enabled when this key is absent; setting it to `1` enables the
hook again. Use the normal web reload procedure for the deployment if needed.
This configuration was not changed during implementation or testing.

For a source rollback, remove only the
`amf.amf.utils.manual_work_order_assignment.assign_manual_machining_work_order`
entry from the Work Order `after_insert` list in `amf/hooks.py`, preserving QR
generation and any later unrelated hook edits. Reload the web application and
refresh hook caches according to the deployment's normal procedure. The new
helper/test/documentation files can remain inactive for review. The original
hooks file is saved as `hooks.py.before` in the evidence directory; restore that
whole file only after checking that no subsequent unrelated hook edits would be
lost.

Disabling/removing the hook leaves existing assignments and queued/sent emails
intact. Close or cancel an assignment using the normal Work Order/ToDo UI if
necessary; do not delete Work Orders to undo this notification feature.
