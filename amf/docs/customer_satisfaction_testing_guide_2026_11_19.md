# Customer satisfaction — changes, previews and acceptance tests

## VM testing — 23 November 2026

The live VM entry point is **http://localhost:8000/satisfaction-feedback-vm**.
It runs on the normal Frappe server on port 8000 and uses the same branded form
and real submission API as the production implementation.

The VM setup now provides:

- Feedback base URL `http://localhost:8000` on `site1.local`.
- An opt-in VM test page available under localhost / loopback hostnames only.
- A dedicated Customer **AMF VM Satisfaction Test (LOCAL ONLY)** and Contact
  **VM Feedback Tester**, using `vm-feedback@example.invalid`.
- One submitted, zero-value, non-stock test Sales Order and one Customer Issue,
  each with a fresh active feedback request.
- Five working star links and the actual email-body preview for each source.
- Real survey persistence on Submit; the VM page links to the saved Survey afterward.
- VM-wide `mute_emails=1`, so queued mail cannot be delivered through SMTP.
  Fixture setup itself dispatches no email.

Open the VM page, click star 2 for either source, select recommendation 0 (or any
0–10 score), optionally add a comment, and Submit. Refresh the VM page to inspect
its response link. The test forms work without login; Desk record links require
an ERP login. Both initial requests were deliberately left unanswered for testing.

To create a new pair after answering the first two:

```sh
cd /home/libracore/frappe-bench
env/bin/python apps/amf/tools/setup_satisfaction_feedback_vm.py --site site1.local --new-round
```

Default setup is idempotent and reuses the current pair:

```sh
env/bin/python apps/amf/tools/setup_satisfaction_feedback_vm.py --site site1.local
```

To turn off VM mode and restore its prior feedback URL/mail settings:

```sh
env/bin/python apps/amf/tools/setup_satisfaction_feedback_vm.py --site site1.local --disable
```

The backup is `sites/site1.local/private/feedback-vm-settings-before.json`.
Disabling VM mode retains the clearly identified test documents and responses.
Production sites remain unaffected unless they explicitly enable the VM setting.
The regression suite now includes the opt-in / local-host access check (26 tests).


## Update — 20 November 2026

The public route must use the Frappe V12 controller filename
`www/satisfaction_feedback.py` (underscores), paired with
`www/satisfaction-feedback.html` (hyphenated URL). The original controller naming
mismatch could render a form without its token and initial rating. Regression
checks now exercise the actual route resolver and HTTP handler, including every
initial star value and a guest POST with satisfaction 2 / recommendation 0.

The page now uses the official AMF logo and Supreme webfont from the supplied
2023 branding folder. Styling follows Brand Guidelines v1.1: Majorelle blue
`#2b47d9`, anthracite `#1c1d20`, white, and lime `#d2ff28` accents. Assets are
self-hosted under the AMF app; no third-party font request is needed. The new
stylesheet is `amf/public/css/satisfaction_feedback.css`.

The form shows a clear selected star and recommendation value, disables duplicate
in-flight submissions, retains answers on failure, and distinguishes an unavailable
link, expired session, connection failure and server error. Its HTTP request asks
Frappe V12 for JSON responses and supplies a CSRF header when a session token exists.

Source branding:

- Folder: https://drive.google.com/drive/folders/16P8DYXTh1iMr1Iy7Wv87eO1jZXdyTzOZ
- Brand guide: https://drive.google.com/file/d/1T6QFL3bnApLwl8GNp7NzbKTB2O5lrYdW/view
- Supplied logo: https://drive.google.com/file/d/1D6AuTkS5RbF4w1JkaHUxMF0UoPpJMsqh/view
- Supplied Supreme font: https://drive.google.com/file/d/171TZ-fIPvNSrfqS97T_5EPk0zbzYkfOb/view

A new full-browser check runs the real Frappe WSGI page/API in a temporary loopback
service. It substitutes rollback for every commit, disables unrelated website chat
in that isolated service, and verifies that record counts are unchanged. Firefox,
Selenium and geckodriver are test-only prerequisites, separate from app dependencies:

```sh
env/bin/python apps/amf/tools/test_satisfaction_feedback_browser.py --site site1.local
```

It covers initial ratings 1–5, required recommendation, rating 2 with recommendation
0, the thank-you state, changing a rating, responsive widths 320/375/768/1440, loaded
logo/font, and invalid-token recovery. Screenshots/results are written under
`previews/customer-satisfaction/branded/`. No customer email is sent.

The sections below retain the original implementation/audit details from
19 November. The current regression suite contains 25 checks.

Final verification on 20 November: all 25 regression checks passed with no skips.
Firefox also passed the real guest HTTP submission (2 stars / recommendation 0),
all five email preselection values, exact 320/375/768/1440 CSS-pixel layouts,
visible selection of recommendation 10 at every width, and invalid-token recovery.
All test writes were rolled back and no emails were sent. Local caches were cleared.
The public host still returned HTTP 404 for the route and needs deployment.


## Follow-up corrections — 20 November 2026

Both reported form bugs had the same cause: Frappe V12 converts hyphens to
underscores when locating a page's Python controller. The controller is now
`amf/www/satisfaction_feedback.py`; the public URL remains
`/satisfaction-feedback`. Previously the controller never ran, leaving both the
initial rating and the hidden submission token empty. The earlier rendering test
only checked that inputs existed, so it missed this failure.

The route now resolves the controller, validates the token, preselects the email
rating, and shows the appropriate invalid-link or already-answered state. It is
excluded from website caches and the sitemap. The after-migrate setup clears the
route's old cached metadata, and that route cache was cleared on the local site.

The page has a new responsive layout, large numbered star controls with explicit
selection text, a 0–10 radio scale, an optional comment, and accessible error and
thank-you states. The form requests JSON responses, includes the session CSRF
token when present, prevents concurrent submissions, and preserves answers after
errors. Connection, expired-session, invalid-link and service errors are shown
separately instead of blaming both ratings for every failure.

The local preview now runs the **production form script**, with only `fetch`
simulated. Its Submission selector can demonstrate success, connection failure,
expired sessions, service errors and invalid links. It cannot send ERP requests.
Regenerate it with the existing preview command below.

The expanded backend suite passes **25 tests, with no skips**, including actual
guest API dispatch with satisfaction **2** and recommendation **0**, all five
server-rendered email ratings, the hidden token, controller discovery, cache
exclusion, invalid links and answered links. Counts before / after rollback:

| DocType | Before | After |
| --- | ---: | ---: |
| Customer Satisfaction Survey | 81 | 81 |
| Satisfaction Feedback Request | 1 | 1 |
| Communication | 4,723 | 4,723 |
| Email Queue | 16,531 | 16,531 |

Headless Firefox checks exercise the production script for selections, required
answers, failures and retries, the exact POST values and CSRF header, duplicate
clicks and the thank-you state. Preview submissions are simulated; real API tests
are rolled back. No customer email was sent or survey response persisted.

Deploy the corrected controller filename together with the template and setup
changes. On the target installation run the deployment commands below, including
`clear-website-cache`, and reload the web/worker processes through the existing
service manager. This follow-up was applied and verified locally; it does not
deploy to the public installation.

## Original installation results — 19 November 2026

The AMF app implementation and targeted local schema migration are complete on
`site1.local`. The site setting `satisfaction_feedback_base_url` is
`https://amf.libracore.ch`. The public feedback URL still returned HTTP 404 when
rechecked for this guide; the public installation needs the matching code and
migration before it can accept customer responses.

The repeatable test runner completed **20 tests, with no skips**. It forbids
commits and rolls back its database work. Counts before and after that run:

| DocType | Before | After |
| --- | ---: | ---: |
| Customer Satisfaction Survey | 81 | 81 |
| Satisfaction Feedback Request | 0 | 0 |
| Communication | 4,723 | 4,723 |
| Email Queue | 16,531 | 16,531 |

No customer email was delivered. Of the 81 existing surveys, 73 were submitted,
one was a draft and seven were cancelled.

## Exactly what changed

### 1. Existing Sales Order confirmation email

The existing Email Template is named **Sales Order**. It is still sent from the
normal document email composer. The new path applies to a **submitted** Sales
Order when that exact template is selected.

- Rendering the template adds five separate feedback links to its current body.
- Existing confirmation wording, shipping text, signature and attachments are
  retained. The live Email Template record itself was not replaced.
- A private request can be created during composition, with status **Prepared**.
  This sends no email and creates no Customer Satisfaction Survey.
- Sending creates the Communication, feedback request state and Email Queue entry
  in one transaction. PDF print-format instructions and additional attachments
  remain attached to the queued message.
- The request becomes **Queued**, meaning it has been prepared for delivery;
  actual delivery status is tracked by Email Queue.
- Sending the same SO/template again returns the original Communication instead
  of creating another confirmation. An intentional delivery retry uses Email
  Queue's existing controls.
- SO submission alone does **not** send a new email.
- Other email templates use the existing Frappe implementation.

Customer and Contact come from the order. If Contact is missing, the code only
infers it from an email when exactly one matching Contact belongs to that Customer.
If no unambiguous match exists, the Contact link stays blank. The user can send
to a purchasing alias without changing the order's Contact attribution.

### 2. Issue closure email

Saving an existing Issue as **Closed** offers to email the related Customer or
Supplier. Choose **No** to leave the Issue closed, or **Yes** to review an editable
draft in the standard email composer. The email is queued when you click **Send**.
Use **Closure email** on a closed Issue to prepare the draft later. For bulk closure,
Desk offers a choice of closed Issue to review.

Customer drafts use the related Contact and may include a fresh set of five
feedback links. Supplier drafts use the Issue's supplier email or the Supplier's
default linked Contact. If no address can be resolved, the composer starts with an
empty recipient field. The migration disables the old **Issue Closed** notification.

### 3. Public form and saved survey

The route is `/satisfaction-feedback?token=…&rating=1..5`. No login is required.

1. Clicking an email star opens the form and preselects satisfaction.
2. The user can change that rating, must select recommendation, and may add a comment.
3. Only pressing **Submit** sends a response to the backend.
4. A **submitted** Customer Satisfaction Survey is created, then the requested
   thank-you message appears. A second submission returns the thank-you result
   without creating another response or modifying the original answers.

| Requested data | Existing/new field | Value |
| --- | --- | --- |
| A-1 Satisfaction | `amf_overall` | Integer 1–5; required |
| A-2 Recommendation | `recommend` | Select value 0–10; required; zero accepted |
| D-3 Comment | Existing `comments` | Optional; new future-needs question label |
| Date Interaction | `date_interaction` | Submission date in the ERP timezone |
| Type Interaction | `type_interaction` | `SO` or `Issue` |
| Organization | `customer` | Linked Customer from the source |
| Contact | `contact_person` | Linked source Contact or an unambiguous inferred match |
| Source type | New `source_doctype` | `Sales Order` or `Issue` |
| Source reference | New `source_name` | Dynamic link to the exact source |
| Request reference | New `feedback_request` | Unique link to the private request |

The server also populates display names and the survey title. The form always
shows the same three questions, and accepts an optional comment of up to 10,000
characters. Comments are escaped before storing them in the existing rich-text
field. No new question field was created for D-3.

### 4. Request tracking and duplicate prevention

New internal DocType: **Satisfaction Feedback Request**.

It stores source type/reference, Organization, Contact, recipient, status,
confirmation Communication (for SO), response Survey and an unguessable token.
Its lifecycle is **Prepared → Queued → Responded**. A token from an unsent,
Prepared request cannot open a usable response form.

There is one request per source document. Database locks serialize request and
response creation, and the Survey's request link is unique. System Manager has
read access to request records; ordinary users do not create, edit or delete them
through Desk. Guest submissions go through the token-protected endpoint and do
not receive ordinary Survey create permission.

### 5. Scoring and report corrections

- Contact scores now come from the latest submitted survey, ordered by interaction
  date, then creation and name. A draft does not update them. Cancellation
  restores the latest remaining submitted response or clears the values.
- Referral Satisfaction Survey previously assigned fabricated 100/100 values.
  That hook was removed. Recording a referral alone now supplies no numeric score.
- Global Satisfaction Score can be calculated twice in one day; it updates that
  day's snapshot instead of failing on its date-based name.
- An empty Customer Satisfaction report date range now returns zero.
- The legacy bulk score migration helper is restricted to System Manager and
  was not run.

Per the user's decision, formulas remain:

| Stored/displayed score | Formula |
| --- | --- |
| Contact CSAT | A-1 × 20 |
| Contact score labelled NPS | A-2 × 10 |
| Global CSAT | Mean populated Contact CSAT ÷ 20 |
| Global score labelled NPS | Mean populated Contact recommendation score, rounded to one decimal |

The current NPS label therefore still represents an average on a 0–100 scale.
Contact values update on survey submit/cancel. Organization CSAT retains its
nightly aggregation, and global snapshots retain their weekly schedule. Existing
historical scores and snapshots were not rebuilt.

### 6. Contact Country

The field did not have an explicit Switzerland default; Frappe V12 inherited it
from global/user Country settings. A targeted browser default resolver now leaves
**Contact.country** blank when creating a Contact, including Quick Entry. It
preserves a country explicitly supplied by a user/caller and existing Contacts.

The older client-script line that cleared Country on form load was replaced,
because it missed Quick Entry and could erase a supplied value. Other DocTypes'
Country defaults remain configured. This correction applies to Desk creation;
server-side code calling `frappe.new_doc` still uses Frappe's default machinery.

## Visual previews

The companion interactive walkthrough uses invented data and simulates the email,
form and resulting field values without accessing ERP endpoints.

For a preview rendered from the **actual app form and email templates**, open:

`previews/customer-satisfaction/index.html`

Select a trigger, click an email star, change the rating, select recommendation,
submit, and inspect the example ERP field table beneath the form. The demonstration
uses a deliberately invalid placeholder token and a local submission handler.
Reloading resets it. It sends no email and writes no ERP records.

Both the actual-template preview and the companion walkthrough passed DOM
interaction checks for star preselection, required recommendation, a zero answer,
the thank-you state, source mapping and replay protection. Those interactions
made zero network requests.

Regenerate the actual-template preview after any template change:

```sh
cd /home/libracore/frappe-bench
env/bin/python apps/amf/tools/preview_satisfaction_feedback.py --site site1.local
```

If your browser needs an HTTP URL instead of a local file, serve only the preview
directory on the machine where you are opening the browser:

```sh
env/bin/python -m http.server 8765 --bind 127.0.0.1 --directory previews/customer-satisfaction
```

Then open `http://127.0.0.1:8765/`. Stop the preview server with Ctrl+C.

## Repeat the automated checks

```sh
cd /home/libracore/frappe-bench
env/bin/python apps/amf/tools/test_satisfaction_feedback.py --site site1.local
```

The runner prints individual tests, results and before/after database counts.
It does not apply schema migrations. It requires the feedback schema and suitable
source Sales Orders/Issues with customer Contacts and email addresses. If those
fixtures are missing, applicable checks are reported as skipped.

The equivalent Frappe suite is `amf.master_crm.test_feedback`; the dedicated runner
adds an outer commit guard and makes its non-persistent behavior explicit.

## Browser acceptance test on an isolated test site

Use a new test Customer/Contact whose email address belongs to you, a fresh test
SO and a fresh Customer Issue. Use the **same test host and database** for email
generation and response submission. Set its feedback base URL to that test host.
Changing only a URL's host cannot make a token from one database work in another.

### A. Sales Order and form

1. Create and submit a test SO linked to that Customer and Contact.
2. Open its email composer and select **Sales Order**.
3. Confirm five linked stars, existing signature and selected confirmation PDF.
   Preparing the email should create at most one **Prepared** request and no Survey.
4. Send the confirmation to your own test mailbox. Confirm one Email Queue entry
   and request status **Queued**.
5. Open star **2** in a private/incognito window. Verify no login request, two stars
   selected, all three questions visible, and no new Customer Satisfaction Survey.
6. Try submitting without recommendation: the form must require a choice.
7. Change satisfaction to **4**, select recommendation **0**, leave comment blank
   or enter a sample future need, and submit.
8. Verify the exact thank-you message. In Desk, find one submitted Survey with A-1
   **4**, A-2 **0**, the comment, today's interaction date, `SO`, correct Customer
   and Contact, source SO link and request link. Request status should be Responded.
9. Refresh/reopen the link and try a repeated submission. Survey count must stay one.
10. Attempt the same confirmation send again: the existing Communication is reused;
    no extra confirmation email or feedback request should be created.

### B. Issue

1. Create a fresh Issue with **Input Selection = Customer Issue**, the test
   Organization and Contact, and status Open.
2. Set status to **Closed**, save, and choose **No**. Check that the status is Closed
   and no closure email was added to Email Queue.
3. Click **Closure email**. Verify the related recipient and five links. Review the
   draft and click **Send** to queue it.
4. Open a star, submit both ratings, and check that the Survey links to that Issue.
5. Reopen and close the Issue. An optional closure email is available, and the
   existing feedback request remains the only one for that Issue.
6. Close a Supplier Issue and choose **Yes**. Verify the supplier is the recipient
   and the message explains the closure. Close an Internal Issue to confirm the
   external email prompt is skipped.

### C. Country, scoring and report

1. Refresh Desk to load the new script. Open **Contact → New**: Country should be
   blank. Repeat through a Contact link's **Create new Contact / Quick Entry** path;
   if Country is not shown there, open the full form before saving to inspect it.
2. Select a country manually and save. Reopen the Contact: that value should remain.
3. For a fresh test Contact, submit a manual Survey with A-1 **4**, A-2 **8**.
   Contact CSAT should become **80**, and its current NPS-labelled score **80**.
4. Save a second survey as Draft with different answers: scores must remain unchanged.
   Submit it, then cancel it: scores should return to the previous submitted response.
5. Record a Referral Satisfaction Survey: it should not assign perfect numeric scores.
6. Run Customer Satisfaction report for a date range with no submitted surveys:
   it should return zero without an error.

Use Desk search to open **Customer Satisfaction Survey**, **Satisfaction Feedback
Request** (System Manager), **Communication**, **Email Queue**, **Contact**, and
**Global Satisfaction Score**. The new Survey source fields are near the bottom.

## Changed application files

| File under `apps/amf/` | Purpose |
| --- | --- |
| `amf/master_crm/feedback.py` | Source context, template adapter, confirmation queueing, Issue hook, token validation and response submission |
| `amf/master_crm/feedback_setup.py` | Idempotent schema/customization setup |
| `amf/master_crm/doctype/satisfaction_feedback_request/` | New private tracking DocType/controller |
| `amf/master_crm/doctype/customer_satisfaction_survey/customer_satisfaction_survey.json` | Source fields, SO/Issue options, required ratings and D-3 label |
| `amf/master_crm/doctype/customer_satisfaction_survey/customer_satisfaction_survey.py` | Display names/title, submitted score synchronization and migration-helper restriction |
| `amf/master_crm/doctype/referral_satisfaction_survey/referral_satisfaction_survey.py` | Remove fabricated numeric score assignment |
| `amf/master_crm/doctype/global_satisfaction_score/global_satisfaction_score.py` | Repeatable daily-named snapshot and caller-owned transaction |
| `amf/master_crm/report/customer_satisfaction/customer_satisfaction.py` | Empty AVG handling |
| `amf/hooks.py` | Register adapters, Issue/survey hooks, Country asset and after-migrate setup |
| `amf/public/js/contact_country_default.js` | Contact-only browser default resolver |
| `amf/templates/emails/issue_feedback.html` | Customer closure message |
| `amf/www/satisfaction-feedback.html` / `amf/www/satisfaction_feedback.py` | Public form and correctly discovered V12 page controller |
| `amf/patches/v12_0/install_satisfaction_feedback_2026_11_19.py` / `amf/patches.txt` | Versioned deployment migration |
| `amf/master_crm/test_feedback.py` | Twenty-five functional, route and API checks |
| `amf/docs/customer_satisfaction_feedback_audit_2026_11_19.md` | Audit findings and implementation record |

The local setup updated DocType metadata, relevant Property Setters, the old
Contact client-script workaround, the site URL override, Patch Log and site
caches. Setup definitions from before these changes are backed up at
`/tmp/amf_feedback_setup_before.json`.

This walkthrough also adds local preview assets under `previews/customer-satisfaction/`
and four helper scripts under `apps/amf/tools/`. The helpers and preview source are versioned with the app; generated previews remain local.

## Deploy to the public installation

After deploying the changed AMF app files there, use that installation's site name:

```sh
bench --site <production-site> migrate
bench --site <production-site> set-config satisfaction_feedback_base_url https://amf.libracore.ch
bench --site <production-site> clear-cache
bench --site <production-site> clear-website-cache
```

Reload its web/worker processes using the normal service manager, then refresh Desk.
Opening `/satisfaction-feedback` without a token should show the invalid-link
message rather than 404. A real form requires a token generated and queued on
that same installation. The deployment patch itself sends no emails and creates
no historical requests.
