from __future__ import unicode_literals

from amf.amf.utils.leave_event import (
	reconcile_leave_events,
	setup_leave_event_integration,
)


def execute():
	"""
	Create native Events for department- and HR-approved leave applications.

	The patch is safe to run again: setup is idempotent and reconciliation
	updates the unique linked Event instead of creating duplicates.
	"""
	setup_leave_event_integration()
	return reconcile_leave_events()
