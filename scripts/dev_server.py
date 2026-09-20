"""Serve the front end and the handler together, for local work.

Not part of the deployment. It exists so the app can be developed without
pushing to AWS: `uv run python scripts/dev_server.py` and open the printed
address. POSTs go to the same handler function that Lambda runs.
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "lambda"))

import handler as lambda_handler  # noqa: E402

WEB = os.path.join(ROOT, "web")

TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json",
    ".svg": "image/svg+xml",
}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("  %s\n" % (fmt % args))

    def _send(self, status, body, content_type):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(body)))
        self.send_header("access-control-allow-origin", "*")
        self.send_header("access-control-allow-headers", "content-type")
        self.send_header("access-control-allow-methods", "POST,GET,OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(204, b"", "text/plain")

    def do_POST(self):
        length = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(length).decode("utf-8")
        event = {"requestContext": {"http": {"method": "POST"}}, "body": raw}
        result = lambda_handler.handler(event, None)
        self._send(result["statusCode"], result["body"], "application/json")

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", ""):
            path = "/index.html"
        target = os.path.normpath(os.path.join(WEB, path.lstrip("/")))
        if not target.startswith(WEB) or not os.path.isfile(target):
            self._send(404, "not found", "text/plain")
            return
        extension = os.path.splitext(target)[1]
        with open(target, "rb") as handle:
            self._send(200, handle.read(), TYPES.get(extension, "application/octet-stream"))


def main():
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print("PlateGap on http://127.0.0.1:%d" % port)
    server.serve_forever()


if __name__ == "__main__":
    main()
