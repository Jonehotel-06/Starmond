#!/usr/bin/env python3
"""
serve.py — local static server for the Starmond frontend.

Serves the built HTML with the same URL rules as production:
  /shop/<slug>/      -> pre-rendered file, else category.html
  /products/<slug>/  -> pre-rendered file, else product.html
  unknown path       -> 404.html with a real 404 status

Optionally proxies /api/ to a backend so the browser stays same-origin:
  API_PROXY_TARGET=http://127.0.0.1:8000 python3 tools/serve.py --port 5173
"""
import argparse
import os
import sys
import urllib.error
import urllib.request
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API_TARGET = os.environ.get("API_PROXY_TARGET", "").rstrip("/")


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if API_TARGET and self.path.startswith(("/api/", "/media/")):
            return self.proxy()
        return super().do_GET()

    def do_POST(self):
        if API_TARGET and self.path.startswith(("/api/", "/media/")):
            return self.proxy()
        self.send_error(405)

    do_PUT = do_POST
    do_PATCH = do_POST
    do_DELETE = do_POST

    def proxy(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        req = urllib.request.Request(API_TARGET + self.path, data=body, method=self.command)
        for key, value in self.headers.items():
            if key.lower() in {"host", "connection", "accept-encoding"}:
                continue
            req.add_header(key, value)
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                self.send_response(response.status)
                for key, value in response.headers.items():
                    if key.lower() in {"transfer-encoding", "connection", "content-encoding"}:
                        continue
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(response.read())
        except urllib.error.HTTPError as error:
            self.send_response(error.code)
            for key, value in error.headers.items():
                if key.lower() in {"transfer-encoding", "connection", "content-encoding"}:
                    continue
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(error.read())
        except Exception as error:  # noqa: BLE001
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"detail":"API proxy could not reach the backend."}')

    def send_head(self):
        path = self.path.split("?", 1)[0]
        candidate = ROOT / path.lstrip("/")
        if path.endswith("/") and not (candidate / "index.html").exists():
            if path.startswith("/shop/"):
                self.path = "/category.html"
            elif path.startswith("/products/"):
                self.path = "/product.html"
        return super().send_head()

    def send_error(self, code, message=None, explain=None):
        if code == 404:
            page = ROOT / "404.html"
            if page.exists():
                body = page.read_bytes()
                self.send_response(404)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
        super().send_error(code, message, explain)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        if self.path.startswith(("/admin/", "/cart", "/checkout", "/account", "/orders")):
            self.send_header("Cache-Control", "no-store, private")
        super().end_headers()

    def log_message(self, fmt, *args):
        if os.environ.get("QUIET"):
            return
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5173)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()
    handler = partial(Handler, directory=str(ROOT))
    with ThreadingHTTPServer((args.host, args.port), handler) as httpd:
        print(f"Starmond frontend on http://{args.host}:{args.port}")
        print(f"API proxy: {API_TARGET or 'disabled (set API_PROXY_TARGET to enable)'}")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
