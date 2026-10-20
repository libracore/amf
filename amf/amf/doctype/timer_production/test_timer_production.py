# -*- coding: utf-8 -*-
# Copyright (c) 2025, libracore AG and Contributors
# See license.txt
from __future__ import unicode_literals

import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from frappe import _dict
from amf.amf.doctype.timer_production import timer_production
from amf.amf.doctype.timer_production.timer_production import (
	build_timer_production_assembly_cost_row,
	calculate_timer_production_cost_per_part,
	calculate_timer_production_time_per_part_minutes,
	calculate_timer_production_total_cost,
)


class TestTimerProduction(unittest.TestCase):
	def setUp(self):
		self.rounding_settings = patch.object(timer_production.frappe, 'get_system_settings', return_value=None)
		self.rounding_settings.start()
		self.addCleanup(self.rounding_settings.stop)

	def test_calculate_timer_production_total_cost_converts_seconds_to_hours(self):
		self.assertEqual(
			calculate_timer_production_total_cost(total_duration=5400),
			97.5,
		)

	def test_calculate_timer_production_cost_per_part_uses_produced_quantity(self):
		self.assertEqual(
			calculate_timer_production_cost_per_part(total_cost=97.5, quantity=15),
			6.5,
		)

	def test_calculate_timer_production_time_per_part_minutes_converts_seconds(self):
		self.assertEqual(
			calculate_timer_production_time_per_part_minutes(total_duration=5400, quantity=15),
			6.0,
		)

	def test_build_timer_production_assembly_cost_row_maps_item_and_costs(self):
		row = build_timer_production_assembly_cost_row({
			'item_code': '300041',
			'quantity': '15',
			'total_duration': 5400,
		})

		self.assertEqual(row['item_code'], '300041')
		self.assertEqual(row['total_cost'], 97.5)
		self.assertEqual(row['time_per_part_minutes'], 6.0)
		self.assertEqual(row['cost_per_part'], 6.5)

	def test_alert_checks_each_open_session_at_four_hours(self):
		now = datetime(2026, 10, 6, 14, 0)
		sessions = [_dict(name='SESSION-1'), _dict(name='SESSION-2')]
		with patch.object(timer_production, 'now_datetime', return_value=now), patch.object(
			timer_production.frappe, 'get_all', return_value=sessions
		) as get_all, patch.object(
			timer_production, '_send_timer_session_alert', side_effect=[True, True]
		) as alert_session:
			result = timer_production.send_timer_alert()

		self.assertEqual(result, {'checked': 2, 'alerted': 2})
		self.assertEqual(get_all.call_args.kwargs['filters']['start_time'],
			['<=', now - timedelta(hours=4)])
		self.assertEqual(alert_session.call_count, 2)
		alert_session.assert_any_call('SESSION-1', now, now - timedelta(hours=4))
		alert_session.assert_any_call('SESSION-2', now, now - timedelta(hours=4))

	def test_alert_is_routed_to_session_operator_and_recorded_once(self):
		now = datetime(2026, 10, 6, 14, 0)
		session = _dict(name='SESSION-1', parent='TIMER/OF-00001', operator='MCH',
			start_time=now - timedelta(hours=4), stop_time=None)
		timer = _dict(name=session.parent, work_order='OF-00001', status='IN PROCESS')
		user = _dict(name='marc@example.com', email='marc@example.com')
		todo = MagicMock()
		todo.name = 'TODO-1'
		todo.insert.return_value = todo
		alert = MagicMock()
		alert.name = session.name
		alert.insert.return_value = alert

		def get_value(doctype, *args, **kwargs):
			return {'Timer Production': timer, 'Work Order': 'In Process', 'User': user}[doctype]

		db = MagicMock()
		with patch.dict(timer_production.frappe.__dict__, {
			'db': db, 'session': _dict(user='Administrator'), 'conf': _dict()
		}), patch.object(
			timer_production.frappe, 'get_doc', side_effect=[todo, alert]
		) as get_doc, patch.object(
			timer_production.frappe, 'sendmail'
		) as sendmail, patch.object(
			timer_production, 'get_url', return_value='https://example.com/production-timer'
		), patch.object(
			timer_production, 'get_url_to_form', return_value='https://example.com/desk'
		), patch.object(
			timer_production, 'nowdate', return_value='2026-10-06'
		):
			db.sql.return_value = [session]
			db.exists.return_value = False
			db.get_value.side_effect = get_value
			result = timer_production._send_timer_session_alert(
				session.name, now, now - timedelta(hours=4))

		self.assertTrue(result)
		self.assertEqual(get_doc.call_args_list[0].args[0]['owner'], user.name)
		self.assertEqual(get_doc.call_args_list[1].args[0]['session_id'], session.name)
		self.assertEqual(get_doc.call_args_list[1].args[0]['todo'], todo.name)
		self.assertEqual(sendmail.call_args.kwargs['recipients'], [user.email])
		todo.insert.assert_called_once_with(ignore_permissions=True)
		alert.insert.assert_called_once_with(ignore_permissions=True)

	def test_existing_session_alert_is_not_sent_again(self):
		now = datetime(2026, 10, 6, 14, 0)
		session = _dict(name='SESSION-1', parent='TIMER/OF-00001', operator='MCH',
			start_time=now - timedelta(hours=5), stop_time=None)
		db = MagicMock()
		with patch.dict(timer_production.frappe.__dict__, {'db': db}), patch.object(
			timer_production.frappe, 'sendmail'
		) as sendmail:
			db.sql.return_value = [session]
			db.exists.return_value = session.name
			result = timer_production._send_timer_session_alert(
				session.name, now, now - timedelta(hours=4))

		self.assertFalse(result)
		sendmail.assert_not_called()

	def test_operator_without_email_uses_configured_fallback(self):
		db = MagicMock()
		db.get_value.return_value = _dict(name='operator@example.com', email=None)
		with patch.dict(timer_production.frappe.__dict__, {
			'db': db,
			'conf': _dict(timer_production_alert_recipients='supervisor@example.com'),
		}):
			user, recipients = timer_production._timer_alert_delivery('MCH')

		self.assertEqual(user.name, 'operator@example.com')
		self.assertEqual(recipients, ['supervisor@example.com'])

	def test_stopped_session_does_not_send_alert(self):
		now = datetime(2026, 10, 6, 14, 0)
		session = _dict(name='SESSION-1', parent='TIMER/OF-00001', operator='MCH',
			start_time=now - timedelta(hours=5), stop_time=now)
		db = MagicMock()
		db.sql.return_value = [session]
		with patch.dict(timer_production.frappe.__dict__, {'db': db}), patch.object(
			timer_production.frappe, 'sendmail'
		) as sendmail:
			result = timer_production._send_timer_session_alert(
				session.name, now, now - timedelta(hours=4))

		self.assertFalse(result)
		db.exists.assert_not_called()
		sendmail.assert_not_called()

	def test_closed_session_alert_closes_its_todo_only(self):
		timer = _dict(name='TIMER/OF-00001', status='IN PROCESS', sessions_list=[
			_dict(name='SESSION-1', stop_time='2026-10-06 14:00:00'),
			_dict(name='SESSION-2', stop_time=None),
		])
		alerts = [
			_dict(name='SESSION-1', session_id='SESSION-1', todo='TODO-1'),
			_dict(name='SESSION-2', session_id='SESSION-2', todo='TODO-2'),
		]
		todo = MagicMock()
		db = MagicMock()
		with patch.dict(timer_production.frappe.__dict__, {'db': db}), patch.object(
			timer_production.frappe, 'get_all', return_value=alerts
		), patch.object(
			timer_production.frappe, 'get_doc', return_value=todo
		) as get_doc, patch.object(
			timer_production, 'now_datetime', return_value=datetime(2026, 10, 6, 14, 0)
		):
			db.get_value.return_value = 'Open'
			timer_production.close_timer_alerts(timer)

		get_doc.assert_called_once_with('ToDo', 'TODO-1')
		self.assertEqual(todo.status, 'Closed')
		todo.save.assert_called_once_with(ignore_permissions=True)
		self.assertEqual(db.set_value.call_args.args[:2], ('Timer Production Alert', 'SESSION-1'))
