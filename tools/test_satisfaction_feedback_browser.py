#!/usr/bin/env python3
"""Real Firefox + Frappe HTTP regression check, with all DB writes rolled back.

Requires Selenium and geckodriver outside the application environment. The
temporary WSGI service accepts only the feedback route/API and static assets.
No email is queued or sent and the service binds to loopback only.
"""
import argparse
import json
import secrets
import sys
import threading
from pathlib import Path
from unittest.mock import patch

import frappe
import frappe.app
from frappe.database.database import Database
from werkzeug.middleware.shared_data import SharedDataMiddleware
from werkzeug.serving import WSGIRequestHandler, make_server
from werkzeug.wrappers import Request, Response


class QuietHandler(WSGIRequestHandler):
    def log(self, kind, message, *args):
        pass  # Do not print token-bearing URLs.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", required=True)
    parser.add_argument("--browser-packages", default="/tmp/amf-feedback-browser-qa")
    parser.add_argument("--geckodriver", default="/tmp/geckodriver")
    args = parser.parse_args()
    bench = Path(__file__).resolve().parents[3]
    output = bench / "previews/customer-satisfaction/branded"
    output.mkdir(parents=True, exist_ok=True)
    sites = str(bench / "sites")
    tables = ("Customer Satisfaction Survey", "Satisfaction Feedback Request", "Communication", "Email Queue")
    frappe.init(site=args.site, sites_path=sites)
    frappe.connect()
    try:
        from amf.master_crm import feedback
        before = {name: frappe.db.count(name) for name in tables}
        fixture = None
        for row in frappe.get_all("Sales Order", filters={"docstatus": 1}, fields=["name"], limit_page_length=300):
            if frappe.db.exists(feedback.REQUEST_DOCTYPE, feedback.request_name("Sales Order", row.name)):
                continue
            doc = frappe.get_doc("Sales Order", row.name)
            context = feedback.source_context(doc)
            if context and context.get("contact_person"):
                fixture = {"source_name": row.name, "context": context}
                break
        if not fixture:
            raise RuntimeError("A submitted test source with a customer Contact/email is required.")
    finally:
        frappe.db.rollback()
        frappe.destroy()

    token = secrets.token_urlsafe(32)
    observations = {"posts": 0, "saved": [], "commit_attempts": 0}
    original_init = frappe.app.init_request
    frappe.app._site = args.site
    frappe.app._sites_path = sites

    def init_with_fixture(request):
        original_init(request)
        if request.path not in ("/satisfaction-feedback", "/api/method/amf.master_crm.feedback.submit_feedback"):
            return
        if request.method == "POST":
            observations["posts"] += 1
        doc = frappe.get_doc("Sales Order", fixture["source_name"])
        metadata = feedback._get_or_create_request(doc, fixture["context"])
        metadata.db_set({"token": token, "status": "Queued"})
        frappe.flags.feedback_qa_request = metadata.name

    def rollback_commit(db):
        observations["commit_attempts"] += 1
        name = getattr(frappe.flags, "feedback_qa_request", None)
        survey = db.get_value(feedback.REQUEST_DOCTYPE, name, "survey") if name else None
        if survey:
            observations["saved"].append(db.get_value("Customer Satisfaction Survey", survey,
                ["docstatus", "amf_overall", "recommend", "comments", "type_interaction"], as_dict=True))
        db.rollback()

    def allowed_application(environ, start_response):
        path = environ.get("PATH_INFO", "")
        if path == "/_qa/viewport":
            width = int(Request(environ).args.get("width", "375"))
            if width not in (320, 375, 768):
                return Response("Invalid viewport", status=400)(environ, start_response)
            # Firefox's desktop window has a platform minimum width. A genuine
            # browsing context at this width exercises the actual media queries.
            html = ('<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">'
                    '<title>AMF viewport test</title><style>body{{margin:0}}iframe{{display:block;border:0}}</style>'
                    '</head><body><iframe id="feedback-viewport" width="{0}" height="1600" '
                    'src="/satisfaction-feedback?token={1}&amp;rating=2"></iframe></body></html>').format(width, token)
            return Response(html, mimetype="text/html")(environ, start_response)
        # The standard website bundle probes chat on page load. Keep this
        # unrelated widget disabled in the isolated test instead of returning
        # 404, which would open Frappe's global error modal over the form.
        chat_method = "frappe.website.doctype.website_settings.website_settings.is_chat_enabled"
        if path == "/api/method/" + chat_method or (
            path == "/" and Request(environ).form.get("cmd") == chat_method
        ):
            return Response('{"message":false}', mimetype="application/json")(environ, start_response)
        if path not in ("/satisfaction-feedback", "/api/method/amf.master_crm.feedback.submit_feedback"):
            return Response("Not found", status=404)(environ, start_response)
        return frappe.app.application(environ, start_response)

    application = SharedDataMiddleware(allowed_application, {"/assets": str(bench / "sites/assets")})
    server = make_server("127.0.0.1", 0, application, request_handler=QuietHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    sys.path.insert(0, args.browser_packages)
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.firefox.service import Service
    from selenium.webdriver.support.ui import WebDriverWait

    options = webdriver.FirefoxOptions()
    options.add_argument("-headless")
    options.binary_location = "/usr/bin/firefox-esr"
    result = {"browser": "Firefox", "passed": [], "before": before, "viewports": []}
    driver = None
    try:
        with patch.object(frappe.app, "init_request", init_with_fixture), patch.object(Database, "commit", rollback_commit):
            thread.start()
            driver = webdriver.Firefox(service=Service(args.geckodriver, log_output="/tmp/amf-feedback-browser-driver.log"), options=options)
            wait = WebDriverWait(driver, 20)
            url = "http://127.0.0.1:{0}/satisfaction-feedback?token={1}&rating=".format(server.server_port, token)
            driver.set_window_size(1440, 1180)
            for rating in range(1, 6):
                driver.get(url + str(rating))
                wait.until(lambda d: d.find_element(By.ID, "satisfaction-" + str(rating)).is_selected())
                assert driver.find_element(By.CSS_SELECTOR, '[name="token"]').get_attribute("value") == token
                assert len(driver.find_elements(By.CSS_SELECTOR, ".amf-stars .is-selected")) == rating
            result["passed"].append("Every email rating is preselected by the real Frappe route")

            driver.get(url + "2")
            wait.until(lambda d: d.find_element(By.ID, "satisfaction-2").is_selected())
            driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]').click()
            assert observations["posts"] == 0
            result["passed"].append("Missing recommendation prevents submission")
            driver.find_element(By.ID, "recommendation-0").click()
            driver.find_element(By.ID, "comment").send_keys("More technical documentation, please.")
            driver.execute_async_script("var done=arguments[0]; document.fonts.load('16px \"AMF Supreme\"').then(function(){done(true);},function(){done(false);});")
            assert driver.execute_script("return document.fonts.check('16px \"AMF Supreme\"')")
            assert driver.execute_script("var logo=document.querySelector('.amf-feedback-logo');return logo.complete&&logo.naturalWidth>0")
            driver.get_full_page_screenshot_as_file(str(output / "desktop.png"))
            driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]').click()
            wait.until(lambda d: d.find_element(By.ID, "feedback-thanks").is_displayed())
            assert observations["saved"] and observations["saved"][-1].amf_overall == 2
            assert observations["saved"][-1].recommend == "0"
            assert observations["saved"][-1].docstatus == 1
            assert observations["saved"][-1].type_interaction == "SO"
            driver.get_full_page_screenshot_as_file(str(output / "thank-you.png"))
            result["passed"].append("Guest browser POST creates a submitted survey with rating 2 and recommendation 0, then rolls back")

            for width in (320, 375, 768, 1440):
                driver.switch_to.default_content()
                driver.set_window_size(max(width, 600), 1100)
                if width < 1440:
                    driver.get("http://127.0.0.1:{0}/_qa/viewport?width={1}".format(server.server_port, width))
                    driver.switch_to.frame(driver.find_element(By.ID, "feedback-viewport"))
                else:
                    driver.get(url + "2")
                wait.until(lambda d: d.find_element(By.ID, "satisfaction-2").is_selected())
                actual_width = driver.execute_script("return window.innerWidth")
                assert actual_width == width, "Incorrect browser viewport: " + str(actual_width)
                result["viewports"].append(actual_width)
                assert driver.execute_script("return document.documentElement.scrollWidth <= window.innerWidth"), "Overflow at " + str(width)
                driver.execute_script("window.qaClicks=[];document.addEventListener('click',function(e){window.qaClicks.push({tag:e.target.tagName,id:e.target.id});},true)")
                driver.find_element(By.ID, "satisfaction-4").click()
                assert driver.find_element(By.ID, "satisfaction-4").is_selected()
                recommendation = driver.find_element(By.ID, "recommendation-10")
                driver.execute_script("if(window.frameElement){var r=arguments[0].getBoundingClientRect();window.parent.scrollTo(0,window.frameElement.offsetTop+r.top-window.parent.innerHeight/2);}", recommendation)
                recommendation.click()
                wait.until(lambda d: d.find_element(By.ID, "recommendation-10").is_selected())
                wait.until(lambda d: "10 / 10" in d.find_element(By.ID, "recommendation-selection").text)
                if width == 375:
                    height = driver.execute_script("return document.documentElement.scrollHeight")
                    driver.switch_to.default_content()
                    frame = driver.find_element(By.ID, "feedback-viewport")
                    driver.execute_script("arguments[0].style.height=arguments[1]+'px'", frame, height)
                    frame.screenshot(str(output / "mobile.png"))
            result["passed"].append("No horizontal overflow and usable controls at 320, 375, 768 and 1440 pixels")

            driver.execute_script("document.querySelector('[name=token]').value='A'.repeat(43)")
            driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]').click()
            wait.until(lambda d: d.find_element(By.ID, "feedback-error").is_displayed())
            assert "original link" in driver.find_element(By.ID, "feedback-error").text
            assert driver.find_element(By.ID, "satisfaction-4").is_selected()
            assert not driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]').get_attribute("disabled")
            result["passed"].append("Invalid-token HTTP error is explained and preserves answers")
    except Exception:
        if driver:
            try:
                print("Control diagnostic:", driver.execute_script("var input=document.getElementById('recommendation-10');return {width:innerWidth,clicks:window.qaClicks,checked:input&&input.checked,rect:input&&input.getBoundingClientRect().toJSON(),selected:Array.from(document.querySelectorAll('[name=recommendation]:checked')).map(function(e){return e.value})}"))
            except Exception:
                pass
            Path("/tmp/amf-feedback-browser-failure.html").write_text(driver.page_source)
            driver.save_screenshot("/tmp/amf-feedback-browser-failure.png")
            print("Browser failure page:", driver.title)
        raise
    finally:
        if driver:
            driver.quit()
        server.shutdown()
        server.server_close()
        if thread.is_alive():
            thread.join(timeout=5)
        frappe.init(site=args.site, sites_path=sites)
        frappe.connect()
        try:
            after = {name: frappe.db.count(name) for name in tables}
            assert before == after, "Browser test persisted records"
            result["after"] = after
            result["post_requests"] = observations["posts"]
        finally:
            frappe.db.rollback()
            frappe.destroy()
    (output / "browser-results.json").write_text(json.dumps(result, indent=2))
    for message in result["passed"]:
        print("PASS: " + message)
    print("Database counts unchanged; no email sent. Screenshots: " + str(output))


if __name__ == "__main__":
    main()
