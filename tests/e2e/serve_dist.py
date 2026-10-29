#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
سرور ایستا با SPA fallback — برای تست محلی باندل مینی‌اپ/پنل.

چرا: `python -m http.server` برای مسیرهای تو‌در‌تو (مثل /app/learn/questions)
۴۰۴ می‌دهد و تست رابط کاربری بی‌معنا می‌شود. این سرور هر مسیر بدون پسوند را
به index.html همان پوشه برمی‌گرداند — دقیقاً مثل رفتار FastAPI در production.

اجرا:
  python3 tests/e2e/serve_dist.py --dir miniapp/dist --prefix /app --port 8099
"""
import argparse
import mimetypes
import os
import pathlib
from http.server import HTTPServer, SimpleHTTPRequestHandler


class Handler(SimpleHTTPRequestHandler):
    prefix = "/app"
    root = "."

    def do_GET(self):
        # /api/* در این سرور ایستا وجود ندارد — نباید index.html برگرداند،
        # وگرنه مرورگر HTML را به‌جای JSON می‌گیرد و باگ کاذب می‌سازد.
        if self.path.startswith("/api/"):
            self.send_response(404)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(b'{"detail":"no_api_in_static_harness"}')
            return
        super().do_GET()

    def translate_path(self, path):
        path = path.split("?", 1)[0].split("#", 1)[0]
        if path.startswith(self.prefix):
            path = path[len(self.prefix):]
        path = path.lstrip("/")
        full = pathlib.Path(self.root) / path
        if full.is_dir():
            full = full / "index.html"
        if not full.exists():
            # SPA fallback
            full = pathlib.Path(self.root) / "index.html"
        return str(full)

    def log_message(self, *a):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="miniapp/dist")
    ap.add_argument("--prefix", default="/app")
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    Handler.root = os.path.abspath(args.dir)
    Handler.prefix = args.prefix.rstrip("/") or ""
    mimetypes.add_type("application/manifest+json", ".webmanifest")
    mimetypes.add_type("text/javascript", ".js")
    srv = HTTPServer((args.host, args.port), Handler)
    print(f"serving {Handler.root} at http://{args.host}:{args.port}{args.prefix or ''}/", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
