# Customer satisfaction audit and implementation — 19 November 2026

Scope: AMF custom app on ERPNext/Frappe V12, Master CRM. The local `site1.local`
schema and configured templates/notifications were inspected as well as source.

Follow-up, 20 November 2026: the original hyphenated page controller filename was
not discovered by V12, so the rendered page lacked its token and selected rating.
The controller is now `amf/www/satisfaction_feedback.py`. The form was redesigned,
the preview now executes the production form script, and route/API coverage was
expanded to 25 passing tests. See the follow-up section of
`customer_satisfaction_testing_guide_2026_11_19.md` for the correction, validation
results and deployment steps. The findings below record the original audit.

## Audit findings

| Area | Finding | Resolution |
| --- | --- | --- |
| Customer Satisfaction Survey | 73 submitted responses, one draft, seven cancelled responses. A-1 is `amf_overall` (integer Rating, 1–5); A-2 is `recommend` (Select, 0–10). | Reuse this DocType and these fields for automatic responses. |
| D-3 | The live site's D-3 is the existing Text Editor field `comments`, labelled “Additional Comments or Observations”. The repository's uncustomized definition does not include the live question numbering. | Reuse `comments`, update its label to the requested future-needs question, preserve existing content and local customizations. Escape public comments before storing HTML. |
| Contact scores | `after_insert` updated scores from drafts. Subsequent submissions, edits and cancellations did not reliably refresh them. | Update from the most recent submitted survey on submit/cancel, ordered by interaction date then creation. Drafts have no effect. No retrospective score rebuild was performed. |
| Legacy migration helper | An authenticated API exposed a site-wide historical score rewrite without a role check. | Restrict it to System Manager. It was not executed as part of this work. |
| Referral Satisfaction Survey | No existing records. This captures referral parties/context, not numeric answers. Its hook fabricated 100/100 ratings for the referring Contact. An unused branch also referenced the nonexistent “Global Satisfaction Survey”. | Remove that hook; keep referral records and their workflow. A referral alone no longer changes numeric satisfaction scores. |
| Existing survey permissions | Both survey DocTypes grant broad create/read/write/submit/delete permissions to the `All` role. | Preserve current staff access; public responses use the token endpoint and do not receive these document permissions. A separate role review is available if needed. |
| Global Satisfaction Score | 75 snapshots. Weekly job averages populated Contact score fields. Date-based names collide on a second run on the same day. | Keep calculations; update today's snapshot on rerun. Let the calling job manage commits. |
| Customer Satisfaction report | Multiplying an empty SQL AVG (`None`) raised an exception. | Empty date ranges return zero. |
| SO email | No automatic SO submission notification exists. Staff send the `Sales Order` Email Template from the normal composer, with the confirmation attachment. | Extend that existing template-render/send path. Do not add a second email on SO submission. Preserve current wording, shipping information, signature and attachment choices. |
| Issue email | `Issue Closed` sent a staff notification on closure. The original feedback hook also queued a customer email on closure. | Disable both automatic closure emails. Offer an editable customer or supplier email from Desk after closure. |
| Contact Country | The live Country field has no explicit default. Frappe V12 inherits the global/user Country default. An existing client script cleared Country on full-form load, which missed Quick Entry and cleared explicitly supplied values. | Suppress default resolution only for Contact.country before new forms are created; preserve explicit values and other DocTypes' Country defaults. Remove the old load-time workaround. |

## Scoring decision

The user explicitly requested keeping the existing formulas for now:

- Contact CSAT = A-1 × 20, on a 0–100 scale.
- Contact score labelled NPS = A-2 × 10, on a 0–100 scale; zero remains a valid answer.
- Global CSAT = average populated Contact CSAT ÷ 20, on a 1–5 scale.
- Global “NPS” = average populated Contact recommendation scores, rounded to one decimal.
- Organization CSAT continues its existing nightly Contact-based aggregation.

The current “NPS” is **not** standard Net Promoter Score. Global snapshots weight
Contacts equally, rather than individual survey responses, and do not apply a
time window. Historical Contact values and existing snapshots were not rewritten.
These choices remain available for a later scoring change.

## Resulting workflow

### Sales Order

1. A submitted SO's existing `Sales Order` template shows five separately linked
   stars in the normal email composer. Preparing the template creates private
   request metadata; it sends no email and creates no survey.
2. Sending that confirmation queues the original message with its selected
   attachments and feedback links, and marks the request Queued in the same
   transaction. Other email templates continue through Frappe's implementation.
3. Repeating the send for that SO/template returns the existing Communication.
   It creates neither a second confirmation nor a second feedback request. Use
   the existing Email Queue retry/resend controls for failed delivery.
4. The SO's Contact and Customer are retained. An explicitly chosen purchasing
   alias is permitted as an email recipient. A missing Contact can be inferred
   only from a unique email match linked to the Customer; it otherwise stays blank.

### Issue

1. An existing Issue transitions to Closed. Desk offers to prepare an email
   when the Issue has a related Customer or Supplier. **No** keeps the Issue
   closed. **Yes** opens the standard email composer for review and editing.
2. For customers, the draft uses the related Contact and includes the Issue
   reference and five rating links if a feedback request can still be sent.
   Supplier drafts use the Issue's supplier email or its linked Contact.
3. The composer requires the user to click **Send**. Customer feedback links
   become active when the email is queued. A feedback request can be sent once.
4. The migration disables the existing **Issue Closed** staff notification.
   For bulk closure, Desk offers a choice of Issue to review. Users can also
   open **Closure email** from a closed Issue later.

### Public response

- Route: `/satisfaction-feedback?token=<opaque-token>&rating=1..5`.
- No login; no customer identity or internal document names appear on the page.
- Five-star satisfaction control with the clicked value preselected and editable;
  recommendation Select with 0–10 inclusive; one optional future-needs comment.
- Exactly the same three questions for every initial rating. Both ratings are
  required. Comment limit: 10,000 characters.
- Only the explicit POST submission creates and submits a Customer Satisfaction
  Survey. It maps A-1, A-2 and D-3 directly, records the submission date, SO/Issue
  interaction type, Customer, Contact, source reference and request reference.
- Successful submission shows the requested thank-you text. Revisiting an
  answered link shows that message. Duplicate POSTs return success without
  creating or modifying another response.

## Integrity and access

`Satisfaction Feedback Request` stores an unguessable 256-bit token and a snapshot
of the source/recipient context. Its deterministic source-based primary key permits
one request per SO or Issue. Source-row locks serialize concurrent email creation;
request-row locks serialize concurrent response submissions. The survey's
`feedback_request` Link is unique as an additional duplicate constraint.

Only System Manager can read request records through Desk; no role has ordinary
create/write/delete permission on them. Guest cannot read these records or create
surveys through ordinary document APIs. The public endpoint validates the token,
accepts POST only, validates both rating ranges, rejects oversized comments, and
escapes comments. It returns the thank-you text without disclosing internal IDs.
Prepared links become usable only after the request is Queued. Page rendering is
uncached, with no-referrer and noindex metadata.

## Setup and deployment

The versioned patch `amf.patches.v12_0.install_satisfaction_feedback_2026_11_19`
installs the private request DocType, synchronizes the existing survey's source
fields, and merges SO/Issue interaction options. `after_migrate` keeps the field
customizations and Country correction synchronized. Setup sends no email and
does not backfill requests for existing SOs or Issues.

The targeted schema setup was applied to the **local** site. Definitions and
Contact client scripts from before setup are backed up at
`/tmp/amf_feedback_setup_before.json`. A normal target-site deployment uses:

```sh
bench --site <site> migrate
bench --site <site> clear-cache
```

Reload the target web/worker processes using that installation's normal service
manager and refresh open Desk sessions. The Country resolver is served directly
from the app asset path and requires no bundle rebuild.

By default links use Frappe's configured site URL. This development site's URL is
`http://site1.local:8000`, which is unsuitable for customer emails. A dedicated
override is supported without changing other site URLs:

```sh
bench --site <site> set-config satisfaction_feedback_base_url https://<public-erp-host>
```

The user confirmed `https://amf.libracore.ch`; that feedback base URL has been
configured on the local site. Retain this configuration when deploying there.

The public host must run this same app version and have HTTPS and the feedback
route available. No remote deployment or real customer email was performed during
development. The original `Sales Order` template itself remains editable in ERP.

A direct check of `https://amf.libracore.ch/satisfaction-feedback` returned HTTP
404 at completion. The public installation therefore still needs this app version
and migration before customer feedback links can be used.

## Verification

The integration suite is `amf.master_crm.test_feedback`. It runs against an
initialized site with the schema and source SO/Issue fixtures; database cases
skip when those fixtures are unavailable. Each database case forbids commits and
rolls back all created surveys, Communications, requests and Email Queue records.
No SMTP delivery is invoked.

Checks cover rating boundaries (including recommendation zero), invalid input and
tokens, five distinct links, Guest permissions, read-only star clicks, page
rendering, field mapping, escaped comments, repeated submissions, composer
preview, attachment retention, duplicate confirmation suppression, Issue closure
and reopening, excluded Issue types, draft/cancel score behavior, repeatable
global snapshots and empty reporting ranges. Python/JavaScript syntax and the
Contact default resolver are also checked.

Final result: **20 tests passed**, plus the V12 JavaScript default-resolution check
and syntax checks. Survey counts remain one draft, 73 submitted and seven cancelled;
zero feedback request records persisted from testing. The local patch is recorded
in Patch Log and site caches have been cleared.
