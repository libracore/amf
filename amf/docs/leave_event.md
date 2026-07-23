# Leave Application company Event

## Scope

This is step one of the leave calendar integration. It creates and maintains a
native ERPNext `Event`; it does not publish anything to Google Calendar.

## Trigger

The department approval transition moves a Leave Application to
`Pending HR Approval`. At that point the integration creates one Event. The
Event remains active if the Leave Application later reaches `Approved`.

## Event values

- Type: `Public`
- Category: `Out of Office`
- Status: `Open`
- All day: enabled
- Start: `from_date 00:00:00`
- End: `to_date 23:59:59` (ERPNext v12 uses inclusive all-day end dates)
- Subject: `{Employee Name} – {Leave Type}`
- Half day subject: `{Employee Name} – {Leave Type} (half day)`
- Color: a stable distinct color for each configured Leave Type
- Participant: the linked Employee
- Reminder: disabled
- Description: blank
- Google synchronization: disabled

The Leave Application and Event contain read-only links to each other. The Event
is updated instead of duplicated when dates or the employee name change.
Rejection, cancellation, or deletion of the Leave Application removes the
linked Event.

Existing eligible Leave Applications can be processed idempotently with
`amf.amf.utils.leave_event.backfill_leave_events`. Running it again updates
changed Events and does not create duplicates.

## Step two

Google Calendar publication must be implemented separately. The generated Event
currently has `sync_with_google_calendar = 0`, so department approval cannot
contact Google or send an invitation.
