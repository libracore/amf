#!/usr/bin/env python3
"""Drive an FFTest Web Page manually; run on the computer running the browser.

Only the ERP Web Page submits stock. This loopback-only helper builds its input
URL and receives its /run_test result redirect. Preview opens the read-only ERP
endpoint directly. No ERP credentials, hardware connection, or extra packages
are needed; log into the selected ERP site in the browser first.
"""

import argparse
import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlencode, urlsplit


PREVIEW_METHOD = "amf.www.fftest_master_debug_4d.debug_stock_entry_flow"


def validate_route(route):
    """Accept a Web Page route, catching accidental use of this script's name."""
    route = route.strip().strip("/")
    parsed = urlsplit(route)
    if not route or parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or any(
        char.isspace() or char in "?#" for char in route
    ):
        raise ValueError("--route must be a Web Page route without a site URL or query parameters.")
    if route.lower().endswith(".py"):
        raise ValueError(
            "--route must be the ERP Web Page's Route field, such as "
            "fftest_stock_entry_test, not the Python helper filename."
        )
    return route


def launch_url(erp_url, route, fields):
    """Validate a submission and build either the preview or Web Page URL."""
    work_order = fields.get("of", "").strip()
    serial = fields.get("sn", "").strip()
    if not work_order or not serial:
        raise ValueError("Work Order and Serial No are required.")
    batches = json.loads(fields.get("batch_list", "[]") or "[]")
    if not isinstance(batches, list) or any(
        not isinstance(row, dict) or not str(row.get("batch_no") or "").strip()
        for row in batches
    ):
        raise ValueError('Batches must be an array such as [{"batch_no":"BATCH-001"}].')
    batch_json = json.dumps(batches, separators=(",", ":"))
    action = fields.get("action", "preview")
    if action == "preview":
        path = "/api/method/" + PREVIEW_METHOD
        arguments = {
            "source_work_order_id": work_order,
            "serial_no_id": serial,
            "batch_no_id": batch_json,
        }
    elif action == "run":
        path = "/" + validate_route(route)
        arguments = {
            "of": work_order,
            "sn": serial,
            "id": fields.get("id", "MANUAL-TEST"),
            "com": fields.get("com", "SIMULATED"),
            "batch_list": batch_json,
        }
    else:
        raise ValueError("Unknown action.")
    # The existing Web Page uses decodeURIComponent, which does not decode '+'
    # as a space. Encode spaces as %20 instead.
    return erp_url + path + "?" + urlencode(arguments, quote_via=quote)


def page(title, content):
    return """<!doctype html><html lang="en"><meta charset="utf-8">
<title>{title}</title><style>
body {{font:16px system-ui,sans-serif;max-width:760px;margin:40px auto;padding:0 20px}}
label {{display:block;margin:18px 0}} input,textarea {{display:block;width:100%;
box-sizing:border-box;padding:9px;margin-top:5px;font:inherit}}
button {{padding:10px 16px;margin:8px 8px 8px 0;cursor:pointer}}
pre {{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f4f6;padding:16px}}
</style><h1>{title}</h1>{content}</html>""".format(
        title=html.escape(title), content=content
    )


class Handler(BaseHTTPRequestHandler):
    def send_page(self, title, content, status=200):
        data = page(title, content).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.headers.get("Host") not in ("127.0.0.1:5001", "localhost:5001"):
            self.send_error(403)
            return
        request = urlsplit(self.path)
        if request.path == "/":
            destination = html.escape(self.server.erp_url + "/" + self.server.erp_route)
            self.send_page("Manual FFTest flow", """
<p>Destination: <code>{destination}</code></p>
<p>Log into this ERP site first. Preview reads the plan; Run opens the Web Page
and creates real stock transactions in the selected ERP site.</p>
<form method="post" action="/launch">
<label>4D Work Order<input name="of" required placeholder="Your submitted Work Order"></label>
<label>Manually entered Serial No<input name="sn" required placeholder="Existing received 5D0000 serial"></label>
<label>Batch selections (JSON)<textarea name="batch_list" rows="4">[]</textarea></label>
<label>Test ID<input name="id" value="MANUAL-TEST"></label>
<label>COM label (no hardware is opened)<input name="com" value="SIMULATED"></label>
<button name="action" value="preview" formtarget="_blank">Open read-only preview</button>
<button name="action" value="run">Run through ERP Web Page</button>
</form>""".format(destination=destination))
        elif request.path == "/run_test":
            values = parse_qs(request.query, keep_blank_values=True)
            error = values.get("erreur", [""])[0]
            title = "ERP reported an error" if error else "ERP reported success"
            details = json.dumps({key: value[0] for key, value in values.items()}, indent=2)
            self.send_page(title, """
<pre>{details}</pre><p>Check the generated Work Orders, Stock Entries and serial
history in ERP. This screen displays the Web Page's redirect result.</p>
<p><a href="/">Return to the test form</a></p>""".format(details=html.escape(details)))
        elif request.path == "/get_erp_username":
            self.send_page("ERP login required", "<p>Log into ERP in another tab, then restart the test from the form.</p>", 401)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.headers.get("Host") not in ("127.0.0.1:5001", "localhost:5001") or self.headers.get("Origin") not in (
            None, "http://127.0.0.1:5001", "http://localhost:5001"
        ):
            self.send_error(403)
            return
        if urlsplit(self.path).path != "/launch":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        if length < 1 or length > 65536:
            self.send_error(413)
            return
        try:
            data = self.rfile.read(length).decode("utf-8")
            fields = {key: value[0] for key, value in parse_qs(data, keep_blank_values=True).items()}
            destination = launch_url(self.server.erp_url, self.server.erp_route, fields)
        except (ValueError, UnicodeError) as exc:
            self.send_page("Check the test inputs", "<p>{}</p><p><a href='/'>Back</a></p>".format(html.escape(str(exc))), 400)
            return
        self.send_response(303)
        self.send_header("Location", destination)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.end_headers()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--erp-url", required=True, help="ERP base URL, e.g. https://your-test-erp.example")
    parser.add_argument("--route", default="fftest_stock_entry_test", help="Route field of the duplicated ERP Web Page (not a Python filename)")
    args = parser.parse_args()
    parsed = urlsplit(args.erp_url)
    if (parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.username
            or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/")):
        parser.error("--erp-url must be an HTTP(S) site base URL without credentials or a page path.")
    try:
        route = validate_route(args.route)
    except ValueError as exc:
        parser.error(str(exc))
    try:
        server = ThreadingHTTPServer(("127.0.0.1", 5001), Handler)
    except OSError as exc:
        parser.error("Cannot listen on 127.0.0.1:5001: {}".format(exc))
    server.erp_url = args.erp_url.rstrip("/")
    server.erp_route = route
    print("Open http://127.0.0.1:5001 in the browser logged into ERP.")
    print("ERP destination: {}/{}".format(server.erp_url, route))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
