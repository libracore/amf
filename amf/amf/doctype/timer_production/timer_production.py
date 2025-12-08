# -*- coding: utf-8 -*-
# Copyright (c) 2025, libracore AG and contributors
# For license information, please see license.txt


from __future__ import unicode_literals
# import frappe
from frappe.model.document import Document

class TimerProduction(Document):
	pass


import frappe
from frappe.utils import get_datetime, now_datetime, time_diff_in_hours


# ==================================================
#  send mail alert for timers running more than 4 hours
# ==================================================
def send_timer_alert():
	timers = frappe.get_all("Timer Production",
		filters={
			"status": "IN PROCESS",
		},
		fields=["name", "work_order", "operator"]
	)

	

	for t in timers:
		
		already = frappe.db.exists("ToDo", {
			"reference_type": "Timer Production",
			"reference_name": t.name,
			"status": "Open"
		})
		if already:
			continue

		session = frappe.db.get_value(
            "Work Order Timer Table",
            {
                "parent": t.name,
                "stop_time": ["is", "not set"]
            },
            ["start_time"],
            as_dict=True
        )

		if not session or not session.start_time:
			continue
		hours_running = time_diff_in_hours(now_datetime(), session.start_time)
		if hours_running > 4:
			frappe.sendmail(
				recipients=frappe.db.get_value("User", {"username": t.operator}, "email"),
				subject="Timer de production en cours depuis plus de 4 heures",
				message=f"""
					<p>Bonjour {t.operator},</p>
					<p>La minuterie de production <b>{t.name}</b> pour l'ordre de fabrication <b>{t.work_order}</b> fonctionne depuis plus de 4 heures.</p>

					<p>Veuillez vérifier que tout va bien.</p>

					<a href="https://amf.libracore.ch/production-timer?param={t.work_order}"
						style="font-size:16px; font-weight:bold; color:#1a73e8;">
					Ouvrir le timer dans la webpage
					</a><br><br>

					<a href="https://amf.libracore.ch/desk#Form/Timer%20Production/{t.name}"
						style="font-size:16px; font-weight:bold; color:#1a73e8;">
					Ouvrir le timer dans le système ERP
					</a><br><br>
					
					<p>Cordialement,<br/>Votre système ERP</p>
				"""
			)

			# create ToDo
			frappe.get_doc({
				"doctype": "ToDo",
				"owner": t.operator,
				"date": frappe.utils.nowdate(),
				"description": f"Le timer de production {t.name} pour l'ordre de fabrication {t.work_order} fonctionne depuis plus de 4 heures. Veuillez vérifier que tout va bien.",
				"reference_type": "Timer Production",
				"reference_name": t.name,
			}).insert(ignore_permissions=True)


def timer_before_save(timer, method = None):
	timer.total_duration = 0
	for sess in timer.sessions_list:
		if sess.start_time and sess.stop_time:
			start = get_datetime(sess.start_time)
			stop = get_datetime(sess.stop_time)
			
			delta = (stop - start).total_seconds()
			sess.duration = delta
			timer.total_duration = (timer.total_duration or 0) + delta
	
	if timer.status == "FINISHED":
		    # insérer la durée totale dans la doctype de l'OF
			work_order = timer.work_order
			if not work_order:
				frappe.logger().error(f"Timer {timer.name} finished but no Work Order linked.")
				return

			wo_doc = frappe.get_doc("Work Order", work_order)

			# vérifier que l'OF n'est pas annulée
			if wo_doc.docstatus == 2:
				frappe.logger().info(
					f"Timer {timer.name} finished but Work Order {wo_doc.name} is cancelled – skipped update"
				)
				return


			wo_doc.total_duration = timer.total_duration
			
			# obtenir la durée totale par opérateur ayant travaillé sur cette OF
			operator_durations = {}

			for sess in timer.sessions_list:
				operator = sess.operator or "Inconnu"
				operator_durations[operator] = operator_durations.get(operator, 0) + (sess.duration or 0)
			
			wo_doc.duration_table = []
			for operator, dur in operator_durations.items():
				wo_doc.append("duration_table", {
					"operator": operator,
					"duration": dur
				})

			wo_doc.save(ignore_permissions=True)