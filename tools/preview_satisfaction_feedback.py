#!/usr/bin/env python3
"""Render actual AMF email/form templates with invented data and local-only submission."""
import argparse
import base64
import importlib
import mimetypes
import re
from html import escape, unescape
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import frappe


def local_links(html):
    def replace(match):
        url = urlparse(unescape(match.group(1)))
        if url.path == "/satisfaction-feedback":
            rating = parse_qs(url.query).get("rating", [""])[0]
            return 'href="#feedback-form" data-preview-rating="{0}"'.format(rating)
        return match.group(0)
    return re.sub(r'href="([^"]+)"', replace, html)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", required=True)
    args = parser.parse_args()
    bench = Path(__file__).resolve().parents[3]
    destination = bench / "previews" / "customer-satisfaction"
    destination.mkdir(parents=True, exist_ok=True)
    def asset_data(path):
        relative = path.split("?", 1)[0].removeprefix("/assets/amf/")
        asset = bench / "apps/amf/amf/public" / relative
        mime = mimetypes.guess_type(str(asset))[0] or "application/octet-stream"
        return "data:{0};base64,{1}".format(mime, base64.b64encode(asset.read_bytes()).decode("ascii"))

    def standalone_assets(html):
        def stylesheet(match):
            asset = bench / "apps/amf/amf/public" / match.group(1).split("?", 1)[0].removeprefix("/assets/amf/")
            css = re.sub(r'url\(["\']?(/assets/amf/[^\)"\']+)["\']?\)',
                         lambda url: 'url("' + asset_data(url.group(1)) + '")', asset.read_text())
            return "<style>" + css + "</style>"
        html = re.sub(r'<link rel="stylesheet" href="(/assets/amf/[^"]+)">', stylesheet, html)
        return re.sub(r'src="(/assets/amf/[^"]+)"', lambda match: 'src="' + asset_data(match.group(1)) + '"', html)
    frappe.init(site=args.site, sites_path=str(bench / "sites"))
    frappe.connect()
    try:
        feedback = importlib.import_module("amf.master_crm.feedback")
        from amf.master_crm.email_templates import SALES_ORDER_TEMPLATE
        from amf.master_crm.issue_closure import render_closure_email

        request = frappe._dict(token="preview-only-not-a-valid-erp-token")
        order = frappe._dict(name="SO-DEMO-001", customer_name="Example Laboratory", po_no="PO-DEMO-001")
        original = frappe.get_doc("Email Template", SALES_ORDER_TEMPLATE)
        so = feedback._add_feedback(frappe.render_template(original.response, order), request)
        issue = render_closure_email({"name": "ISS-DEMO-001"}, "Alex Example", feedback.stars_html(request))
        source = (bench / "apps/amf/amf/www/satisfaction-feedback.html").read_text()
        def block(name):
            match = re.search(r'{% block ' + re.escape(name) + r' %}(.*?){% endblock %}', source, re.S)
            return frappe.render_template(match.group(1), {
                "token": request.token, "rating": 3, "responded": False, "invalid_link": False,
            })
        shell = (Path(__file__).resolve().parent / "satisfaction_feedback_preview.html").read_text()
        for key, value in {
            "__AMF_FORM_HEAD__": block("head_include"), "__AMF_FORM__": block("page_content"),
            "__AMF_FORM_SCRIPT__": block("script"),
            "__AMF_SO_EMAIL__": local_links(so), "__AMF_ISSUE_EMAIL__": local_links(issue["message"]),
            "__AMF_SO_SUBJECT__": escape(frappe.render_template(original.subject, order), quote=True),
            "__AMF_ISSUE_SUBJECT__": escape(issue["subject"], quote=True),
        }.items():
            shell = shell.replace(key, value)
        (destination / "index.html").write_text(standalone_assets(shell))
        print("Preview: " + str(destination / "index.html"))
        print("Invented recipients and references; no email sent; no ERP record created.")
    finally:
        frappe.db.rollback()
        frappe.destroy()


if __name__ == "__main__":
    main()
