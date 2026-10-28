# -*- coding: utf-8 -*-
"""📲 گارد قرارداد PWA — «نصب‌پذیر بودن» نباید بی‌صدا بشکند.

پیشینه
──────
مینی‌اپ `service worker` داشت و روی موبایل هم اجرا می‌شد، ولی **manifest
نداشت**. بدون manifest، مرورگر (Chrome/Edge/Safari) گزینهٔ «افزودن به صفحهٔ
اصلی / نصب برنامه» نمی‌دهد ⇒ ادعای «PWA» عملاً بی‌اثر بود و هیچ تستی هم
آن را نمی‌گرفت.

این تست قرارداد حداقلیِ نصب‌پذیری را قفل می‌کند (روی سورس، نه خروجی بیلد؛
پس بدون npm هم در CI سبز است):
  • manifest وجود دارد، JSON معتبر است و فیلدهای اجباری را دارد
  • آیکون‌های ۱۹۲ و ۵۱۲ (و نسخهٔ maskable) واقعاً در `public/` هستند
  • `index.html` به manifest و آیکون‌ها لینک می‌دهد
  • `main.jsx` سرویس‌ورکر را ثبت می‌کند
"""
from __future__ import annotations

import json
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUB = os.path.join(ROOT, "miniapp", "public")
MANIFEST = os.path.join(PUB, "manifest.webmanifest")
INDEX = os.path.join(ROOT, "miniapp", "index.html")
MAIN = os.path.join(ROOT, "miniapp", "src", "main.jsx")


class PwaContractTests(unittest.TestCase):
    manifest: dict = {}

    @classmethod
    def setUpClass(cls):
        if os.path.isfile(MANIFEST):
            with open(MANIFEST, encoding="utf-8") as f:
                cls.manifest = json.load(f)

    def test_manifest_exists_and_is_valid_json(self):
        self.assertTrue(os.path.isfile(MANIFEST),
                        "miniapp/public/manifest.webmanifest وجود ندارد ⇒ "
                        "مرورگر گزینهٔ نصب نمی‌دهد")
        self.assertIsInstance(self.manifest, dict)
        self.assertTrue(self.manifest, "manifest خالی است")

    def test_manifest_required_fields(self):
        m = self.manifest
        for field in ("name", "short_name", "start_url", "display",
                      "icons", "theme_color", "background_color"):
            self.assertIn(field, m, f"فیلد اجباری manifest ندارد: {field}")
        self.assertIn(m["display"], ("standalone", "fullscreen",
                                     "minimal-ui", "browser"))
        self.assertNotEqual(m["display"], "browser",
                            "display=browser یعنی نصب‌پذیر نیست")

    def test_manifest_is_rtl_farsi(self):
        m = self.manifest
        self.assertEqual(m.get("lang"), "fa")
        self.assertEqual(m.get("dir"), "rtl")

    def test_manifest_icons_exist_on_disk(self):
        sizes = set()
        for icon in self.manifest.get("icons") or []:
            rel = str(icon.get("src", "")).lstrip("./")
            path = os.path.join(PUB, rel)
            self.assertTrue(os.path.isfile(path),
                            f"آیکون manifest در دیسک نیست: {rel}")
            sizes.add(icon.get("sizes"))
        self.assertIn("192x192", sizes, "آیکون ۱۹۲ لازم است")
        self.assertIn("512x512", sizes, "آیکون ۵۱۲ لازم است")

    def test_manifest_has_maskable_icon(self):
        purposes = " ".join(str(i.get("purpose", "")) for i in
                            self.manifest.get("icons") or [])
        self.assertIn("maskable", purposes,
                      "آیکون maskable برای اندروید لازم است")

    def test_index_links_manifest_and_icons(self):
        with open(INDEX, encoding="utf-8") as f:
            html = f.read()
        self.assertIn('rel="manifest"', html)
        self.assertIn("manifest.webmanifest", html)
        self.assertIn("apple-touch-icon", html)
        self.assertIn("apple-mobile-web-app-capable", html)
        self.assertIn("viewport-fit=cover", html,
                      "بدون viewport-fit=cover، safe-area روی iPhone کار نمی‌کند")

    def test_service_worker_is_registered(self):
        with open(MAIN, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("serviceWorker", src)
        self.assertIn("register", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
