# Leave Application company Event

## Scope

This is step one of the leave calendar integration. It creates and maintains a
native ERPNext `Event`; it does not publish anything to Google Calendar.

## Trigger

Employee submission moves a Leave Application to `Pending Dept Approval`. At
that point the integration creates one provisional Event. The same Event
remains linked and is updated when the application reaches
`Pending HR Approval` or `Approved`.

## Event values

- Type: `Public`
- Category: `Out of Office`
- Status: `Open`
- All day: enabled
- Start: `from_date 00:00:00`
- End: `to_date 23:59:59` for full-day leave; `to_date 12:00:00`
  for half-day leave
- Subject: `{Employee Name} – {Leave Type}`
- Half day subject: `{Employee Name} – {Leave Type} (½ day)`
- Color: a stable distinct color for each configured Leave Type
- Participant: the linked Employee
- Reminder: disabled
- Description: blank for full days; `Half day on YYYY-MM-DD.` for half days
- Google synchronization: disabled

For `Jour de maladie`, the public subject is privacy-safe:
`{Employee Name} - OoO`. When the Leave Application has `half_day` checked,
the subject becomes `{Employee Name} - OoO (½ day)` and the description
states the `half_day_date`. A neutral color shared with another generic absence
is used so the Event does not disclose sickness.

`Pending Dept Approval` Events retain their Leave Type color. Pending and
approved Events use ERPNext's native calendar rendering without custom
patterns or borders. Half-day applications are identified by the `½ day` title
and exact `half_day_date` description.

The Leave Application and Event contain read-only links to each other. The Event
is updated instead of duplicated when dates or the employee name change.
Rejection, cancellation, or deletion of the Leave Application removes the
linked Event.

Existing eligible Leave Applications can be processed idempotently with
`amf.amf.utils.leave_event.backfill_leave_events`. Running it again updates
changed Events and does not create duplicates.

On deployment, `bench migrate` runs
`amf.patches.v12_0.create_leave_events_retroactively` from `patches.txt`. The
patch first installs the required custom fields/category, then reconciles every
`Pending Dept Approval`, `Pending HR Approval`, and `Approved` Leave
Application. It is safe to execute again because each Leave Application has one
unique linked Event.

## Step two

Google Calendar publication must be implemented separately. The generated Event
currently has `sync_with_google_calendar = 0`, so department approval cannot
contact Google or send an invitation.
