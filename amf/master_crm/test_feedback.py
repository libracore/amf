# -*- coding: utf-8 -*-
"""Run with bench --site <test-site> run-tests --module amf.master_crm.test_feedback.

Database cases always roll back and forbid commits, including email queue work.
"""
import importlib
import json
import re
import secrets
import unittest
from html.parser import HTMLParser
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import frappe

from amf.master_crm import feedback


class FeedbackControls(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.inputs = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == "input":
            self.inputs.append(dict(attrs))


class TestFeedbackValidation(unittest.TestCase):
    def test_vm_testing_is_opt_in_and_limited_to_local_hosts(self):
        from amf.master_crm.feedback_vm import vm_request_allowed
        with patch.object(frappe.local, "request", frappe._dict(host="localhost:8000"), create=True):
            with patch.dict(frappe.conf, {"satisfaction_feedback_vm_enabled": 0}):
                self.assertFalse(vm_request_allowed())
            with patch.dict(frappe.conf, {"satisfaction_feedback_vm_enabled": 1}):
                for host in ("localhost:8000", "127.0.0.1:8000", "[::1]:8000"):
                    frappe.local.request.host = host
                    self.assertTrue(vm_request_allowed())
                for host in ("amf.libracore.ch", "localhost.example.com", "192.168.1.20:8000"):
                    frappe.local.request.host = host
                    self.assertFalse(vm_request_allowed())

    def test_rating_boundaries_include_recommendation_zero(self):
        self.assertEqual(feedback._rating("0", 0, 10, "recommendation"), 0)
        self.assertEqual(feedback._rating("10", 0, 10, "recommendation"), 10)
        self.assertEqual(feedback._rating("1", 1, 5, "satisfaction"), 1)
        self.assertEqual(feedback._rating(5, 1, 5, "satisfaction"), 5)

    def test_invalid_ratings_are_rejected_without_coercion(self):
        with patch.object(frappe, "throw", side_effect=ValueError):
            for value in (None, "", True, False, "1.5", "NaN", " 5", -1, 11, [], {}):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    feedback._rating(value, 0, 10, "recommendation")
            for value in (0, 6):
                with self.assertRaises(ValueError):
                    feedback._rating(value, 1, 5, "satisfaction")

    def test_five_stars_have_distinct_preselection_links(self):
        token = secrets.token_urlsafe(32)
        with patch.object(feedback, "get_url", side_effect=lambda path: "https://erp.example" + path), \
                patch.dict(frappe.conf, {"satisfaction_feedback_base_url": "https://erp.example"}):
            html = feedback.stars_html(frappe._dict(token=token))
        urls = re.findall(r'href="([^"]+)"', html)
        self.assertEqual(len(urls), 5)
        for number, url in enumerate(urls, 1):
            query = parse_qs(urlparse(url.replace("&amp;", "&")).query)
            self.assertEqual(query, {"token": [token], "rating": [str(number)]})

    def test_unrelated_email_operations_use_stock_make(self):
        def stock(doctype=None, email_template=None, send_email=False):
            return {"delegated": True}
        with patch("frappe.core.doctype.communication.email.make", new=stock):
            # Mirror the API's cmd argument; the adapter must remove it.
            self.assertEqual(feedback.make_communication(cmd="original.endpoint", doctype="Issue"),
                             {"delegated": True})

    def test_referrals_do_not_assign_numeric_scores(self):
        from amf.master_crm.doctype.referral_satisfaction_survey.referral_satisfaction_survey import update_contact_csat_nps
        with patch.object(frappe.db, "set_value") as setter:
            update_contact_csat_nps(frappe._dict(referring_contact="test"), "after_insert")
        setter.assert_not_called()

    def test_supplier_internal_and_unclassified_issues_do_not_request_feedback(self):
        for selection in ("Supplier Issue", "Internal Issue", "-", "Supplier", "Internal"):
            doc = frappe._dict(doctype="Issue", input_selection=selection, customer="Customer")
            self.assertIsNone(feedback.source_context(doc))


class TestFeedbackDatabase(unittest.TestCase):
    def setUp(self):
        if not getattr(frappe.local, "site", None):
            self.skipTest("Requires an initialized Frappe test site")
        if not frappe.db.exists("DocType", feedback.REQUEST_DOCTYPE):
            self.skipTest("Run the feedback schema migration first")
        frappe.set_user("Administrator")
        self.commit_guard = patch.object(frappe.db, "commit", side_effect=AssertionError("A feedback test attempted to commit"))
        self.commit_guard.start()
        self.addCleanup(self.commit_guard.stop)
        self.addCleanup(frappe.db.rollback)
        self.source = self._find_source("Sales Order")
        self.context = feedback.source_context(self.source)

    def _find_source(self, doctype):
        filters = {"docstatus": 1} if doctype == "Sales Order" else {}
        for row in frappe.get_all(doctype, filters=filters, fields=["name"], limit_page_length=300):
            if frappe.db.exists(feedback.REQUEST_DOCTYPE, feedback.request_name(doctype, row.name)):
                continue
            doc = frappe.get_doc(doctype, row.name)
            context = feedback.source_context(doc)
            if context and context["contact_person"]:
                return doc
        self.skipTest("Requires a source with a customer contact and email")

    def _request(self):
        feedback._lock_source(self.source.doctype, self.source.name)
        request = feedback._get_or_create_request(self.source, self.context)
        request.db_set("status", "Queued")
        return request

    def test_request_uniqueness_and_guest_permissions(self):
        request = self._request()
        again = feedback._get_or_create_request(self.source, self.context)
        self.assertEqual(request.name, again.name)
        frappe.set_user("Guest")
        self.assertFalse(frappe.has_permission(feedback.REQUEST_DOCTYPE, "read"))
        self.assertFalse(frappe.has_permission("Customer Satisfaction Survey", "create"))
        self.assertEqual(feedback.get_request(request.token).name, request.name)

    def test_star_click_only_preselects_and_never_creates_survey(self):
        request = self._request()
        before = frappe.db.count("Customer Satisfaction Survey")
        frappe.set_user("Guest")
        frappe.local.form_dict = frappe._dict(token=request.token, rating="2")
        context = importlib.import_module("amf.www.satisfaction_feedback").get_context(frappe._dict())
        self.assertEqual(context.rating, 2)
        self.assertFalse(context.responded)
        self.assertEqual(frappe.db.count("Customer Satisfaction Survey"), before)
        self.assertTrue(context.no_cache)

    def test_guest_submission_maps_fields_and_is_idempotent(self):
        request = self._request()
        frappe.set_user("Guest")
        result = feedback.submit_feedback(request.token, "4", "0", '<script>alert("x")</script>\nMore support')
        self.assertEqual(result["message"], feedback.THANK_YOU)
        request.reload()
        survey = frappe.get_doc("Customer Satisfaction Survey", request.survey)
        self.assertEqual(survey.docstatus, 1)
        self.assertEqual(survey.amf_overall, 4)
        self.assertEqual(survey.recommend, "0")
        self.assertEqual(survey.type_interaction, "SO")
        self.assertEqual(survey.customer, self.context["customer"])
        self.assertEqual(survey.contact_person, self.context["contact_person"])
        self.assertEqual(survey.source_name, self.source.name)
        self.assertEqual(survey.date_interaction.isoformat(), frappe.utils.nowdate())
        self.assertNotIn("<script>", survey.comments)
        self.assertIn("More support", survey.comments)
        self.assertEqual(float(frappe.db.get_value("Contact", survey.contact_person, "referral_satisfaction_survey")), 0)
        count = frappe.db.count("Customer Satisfaction Survey")
        feedback.submit_feedback(request.token, "1", "10", "Changed")
        self.assertEqual(frappe.db.count("Customer Satisfaction Survey"), count)
        survey.reload()
        self.assertEqual(survey.amf_overall, 4)

    def test_guest_http_api_accepts_rating_two_and_recommendation_zero(self):
        from werkzeug.test import EnvironBuilder
        from werkzeug.wrappers import Request
        from frappe.app import make_form_dict
        from frappe.api import handle
        request = self._request()
        frappe.set_user("Guest")
        frappe.local.request = Request(EnvironBuilder(
            path="/api/method/amf.master_crm.feedback.submit_feedback", method="POST",
            headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
            data={"token": request.token, "satisfaction": "2", "recommendation": "0", "comment": "More support"},
        ).get_environ())
        make_form_dict(frappe.local.request)
        response = handle()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.get_data(as_text=True))["message"]["message"], feedback.THANK_YOU)
        request.reload()
        survey = frappe.get_doc("Customer Satisfaction Survey", request.survey)
        self.assertEqual(survey.docstatus, 1)
        self.assertEqual(survey.amf_overall, 2)
        self.assertEqual(survey.recommend, "0")
        # A retry goes through the same API and must retain the original response.
        count = frappe.db.count("Customer Satisfaction Survey")
        make_form_dict(frappe.local.request)
        self.assertEqual(handle().status_code, 200)
        self.assertEqual(frappe.db.count("Customer Satisfaction Survey"), count)

    def test_missing_ratings_do_not_create_response(self):
        request = self._request()
        before = frappe.db.count("Customer Satisfaction Survey")
        with self.assertRaises(frappe.ValidationError):
            feedback.submit_feedback(request.token, "4", "")
        self.assertEqual(frappe.db.count("Customer Satisfaction Survey"), before)
        request.reload()
        self.assertFalse(request.survey)

    def test_invalid_and_unsent_tokens_are_rejected(self):
        for token in ("", "bad", secrets.token_urlsafe(32)):
            with self.assertRaises(frappe.PermissionError):
                feedback.get_request(token)
        request = feedback._get_or_create_request(self.source, self.context)
        with self.assertRaises(frappe.PermissionError):
            feedback.get_request(request.token)

    def test_confirmation_queues_once_and_preserves_content_and_attachments(self):
        args = {
            "doctype": "Sales Order", "name": self.source.name, "email_template": "Sales Order",
            "send_email": 1, "recipients": self.context["recipient"],
            "content": "<p>Order confirmation</p><p>We remain at your disposal.</p><p>Madeleine</p>",
            "subject": "Feedback integration test (rolled back)",
            "print_format": "Standard", "print_letterhead": 1,
            "attachments": json.dumps([{"fname": "confirmation-test.txt", "fcontent": "Test attachment"}]),
        }
        result = feedback.make_communication(**args)
        comm = frappe.get_doc("Communication", result["name"])
        self.assertEqual(comm.content.count(feedback.MARKER), 1)
        self.assertIn("Madeleine", comm.content)
        self.assertEqual(len(re.findall('/satisfaction-feedback\\?', comm.content)), 5)
        queued = frappe.get_all("Email Queue", filters={"communication": comm.name}, fields=["name"])
        self.assertEqual(len(queued), 1)
        queue = frappe.get_doc("Email Queue", queued[0].name)
        self.assertIn("confirmation-test.txt", queue.message)
        prints = [a for a in json.loads(queue.attachments) if a.get("print_format_attachment")]
        self.assertEqual(len(prints), 1)
        self.assertEqual(prints[0]["doctype"], "Sales Order")
        self.assertEqual(prints[0]["name"], self.source.name)
        self.assertEqual(prints[0]["print_format"], "Standard")
        self.assertEqual(prints[0]["print_letterhead"], 1)
        again = feedback.make_communication(**args)
        self.assertEqual(result, again)
        self.assertEqual(frappe.db.count("Email Queue", {"communication": comm.name}), 1)

    def test_composer_preview_has_links_but_does_not_send(self):
        before = frappe.db.count("Email Queue")
        result = feedback.get_email_template("Sales Order", self.source.as_dict())
        self.assertEqual(len(re.findall('/satisfaction-feedback\\?', result["message"])), 5)
        self.assertEqual(frappe.db.count("Email Queue"), before)
        request = frappe.get_doc(feedback.REQUEST_DOCTYPE, feedback.request_name("Sales Order", self.source.name))
        self.assertEqual(request.status, "Prepared")
        self.assertEqual(feedback._add_feedback(result["message"], request), result["message"])

    def test_issue_transition_queues_once_even_after_reopening(self):
        issue = self._find_source("Issue")
        issue.status = "Closed"
        issue.get_doc_before_save = lambda: frappe._dict(status="Open")
        before = frappe.db.count("Email Queue", {"reference_doctype": "Issue", "reference_name": issue.name})
        feedback.on_issue_update(issue)
        feedback.on_issue_update(issue)
        self.assertEqual(frappe.db.count("Email Queue", {"reference_doctype": "Issue", "reference_name": issue.name}), before + 1)
        request = frappe.get_doc(feedback.REQUEST_DOCTYPE, feedback.request_name("Issue", issue.name))
        feedback.submit_feedback(request.token, "1", "3")
        self.assertEqual(frappe.db.get_value("Customer Satisfaction Survey", request.survey or
                         frappe.db.get_value(feedback.REQUEST_DOCTYPE, request.name, "survey"), "type_interaction"), "Issue")

    def test_already_closed_and_new_issues_do_not_send(self):
        for previous in (None, frappe._dict(status="Closed")):
            doc = frappe._dict(status="Closed", get_doc_before_save=lambda: previous)
            with patch.object(frappe, "sendmail") as send:
                feedback.on_issue_update(doc)
            send.assert_not_called()

    def test_drafts_do_not_change_contact_scores_and_cancel_restores_them(self):
        contact = self.context["contact_person"]
        before = frappe.db.get_value("Contact", contact, ["customer_satisfaction_survey", "referral_satisfaction_survey"])
        survey = frappe.get_doc({"doctype": "Customer Satisfaction Survey", "contact_person": contact,
                                 "amf_overall": 2, "recommend": "0", "date_interaction": "2099-01-01"})
        survey.insert(ignore_permissions=True)
        self.assertEqual(frappe.db.get_value("Contact", contact, ["customer_satisfaction_survey", "referral_satisfaction_survey"]), before)
        survey.submit()
        self.assertEqual(float(frappe.db.get_value("Contact", contact, "customer_satisfaction_survey")), 40)
        survey.cancel()
        self.assertNotEqual(frappe.db.get_value("Contact", contact, "customer_satisfaction_survey"), "40.0")

    def test_global_snapshot_can_be_repeated_without_changing_formula(self):
        from amf.master_crm.doctype.global_satisfaction_score.global_satisfaction_score import calculate_global_scores
        contacts = frappe.get_all("Contact", fields=["customer_satisfaction_survey", "referral_satisfaction_survey"])
        csat = [float(c.customer_satisfaction_survey) for c in contacts if c.customer_satisfaction_survey not in (None, "")]
        nps = [float(c.referral_satisfaction_survey) for c in contacts if c.referral_satisfaction_survey not in (None, "")]
        calculate_global_scores()
        count = frappe.db.count("Global Satisfaction Score")
        calculate_global_scores()
        self.assertEqual(frappe.db.count("Global Satisfaction Score"), count)
        scores = frappe.get_doc("Global Satisfaction Score", frappe.utils.nowdate())
        self.assertAlmostEqual(float(scores.global_csat_score), sum(csat) / len(csat) / 20)
        self.assertAlmostEqual(float(scores.global_nps_score), round(sum(nps) / len(nps), 1))

    def test_empty_satisfaction_report_returns_zero(self):
        from amf.master_crm.report.customer_satisfaction.customer_satisfaction import execute
        columns, rows = execute({"from_date": "2099-01-01", "to_date": "2099-01-02"})
        self.assertEqual(rows, [{"global_average": 0}])

    def test_legacy_score_migration_is_not_available_to_guests(self):
        from amf.master_crm.doctype.customer_satisfaction_survey.customer_satisfaction_survey import migrate_amf_overall_to_contact
        frappe.set_user("Guest")
        with self.assertRaises(frappe.PermissionError):
            migrate_amf_overall_to_contact()

    def test_guest_page_renders_the_three_questions(self):
        from werkzeug.test import EnvironBuilder
        from werkzeug.wrappers import Request
        from frappe.website.render import render_page
        request = self._request()
        frappe.set_user("Guest")
        frappe.local.form_dict = frappe._dict(token=request.token, rating="3")
        frappe.local.request = Request(EnvironBuilder(path="/satisfaction-feedback").get_environ())
        html = render_page("satisfaction-feedback")
        self.assertIn('name="satisfaction"', html)
        self.assertIn('name="recommendation"', html)
        self.assertIn('name="comment"', html)
        controls = FeedbackControls(html).inputs
        self.assertEqual([item.get("value") for item in controls if item.get("name") == "token"], [request.token])
        checked = [item["value"] for item in controls if item.get("name") == "satisfaction" and "checked" in item]
        self.assertEqual(checked, ["3"])
        self.assertNotIn('name="customer"', html)
        self.assertIn('no-referrer', html)

    def test_guest_page_preselects_every_email_star(self):
        from werkzeug.test import EnvironBuilder
        from werkzeug.wrappers import Request
        from frappe.website.render import render_page
        request = self._request()
        frappe.set_user("Guest")
        before = frappe.db.count("Customer Satisfaction Survey")
        for rating in range(1, 6):
            with self.subTest(rating=rating):
                frappe.local.form_dict = frappe._dict(token=request.token, rating=str(rating))
                frappe.local.request = Request(EnvironBuilder(path="/satisfaction-feedback").get_environ())
                html = render_page("satisfaction-feedback")
                controls = FeedbackControls(html).inputs
                checked = [item["value"] for item in controls if item.get("name") == "satisfaction" and "checked" in item]
                self.assertEqual(checked, [str(rating)])
                self.assertEqual(html.count('amf-rating-choice is-selected'), rating)
                self.assertEqual([item["value"] for item in controls if item.get("name") == "recommendation"],
                                 [str(value) for value in range(11)])
        self.assertEqual(frappe.db.count("Customer Satisfaction Survey"), before)

    def test_public_route_loads_controller_and_cannot_cache_tokens(self):
        from frappe.website.router import get_page_info_from_template
        page = get_page_info_from_template("satisfaction-feedback")
        self.assertEqual(page.controller, "amf.www.satisfaction_feedback")
        self.assertTrue(page.no_cache)

    def test_public_route_without_token_has_no_form(self):
        from werkzeug.test import EnvironBuilder
        from werkzeug.wrappers import Request
        from frappe.website.render import render_page
        frappe.set_user("Guest")
        frappe.local.form_dict = frappe._dict()
        frappe.local.request = Request(EnvironBuilder(path="/satisfaction-feedback").get_environ())
        html = render_page("satisfaction-feedback")
        self.assertIn("This link is unavailable", html)
        self.assertNotIn('id="amf-feedback-form"', html)

    def test_answered_public_route_shows_thanks_without_form(self):
        from werkzeug.test import EnvironBuilder
        from werkzeug.wrappers import Request
        from frappe.website.render import render_page
        request = self._request()
        feedback.submit_feedback(request.token, "2", "0")
        frappe.set_user("Guest")
        frappe.local.form_dict = frappe._dict(token=request.token)
        frappe.local.request = Request(EnvironBuilder(path="/satisfaction-feedback").get_environ())
        html = render_page("satisfaction-feedback")
        self.assertIn("Your response has been saved.", html)
        self.assertNotIn('id="amf-feedback-form"', html)
