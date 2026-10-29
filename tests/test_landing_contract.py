# -*- coding: utf-8 -*-
"""🏠 قرارداد لندینگ (صفحهٔ ریشهٔ دامنه) + سرو شدن فونت خودمیزبان.

چرا این فایل؟
──────────────
۱) ریشهٔ دامنه تا امروز **۳۰۷ به /app/** بود؛ بیرون از تلگرام یعنی
   بازدیدکنندهٔ عادی به صفحهٔ «از تلگرام باز کن» می‌رسید. حالا `/`
   باید HTML واقعی لندینگ بدهد.

۲) کد لندینگ در همان مخزن مینی‌اپ ساخته می‌شود (`npm run build:landing`)
   و باید در بیلد داکر هم باشد، وگرنه در Production صفحهٔ قدیمی برمی‌گردد.

۳) باگ واقعیِ کشف‌شده در همین دور: `globals.css` فونت‌ها را با مسیر
   مطلق `/fonts/vazirmatn-*.woff2` صدا می‌زند، ولی هیچ mountی روی
   `/fonts` نبود ⇒ در Production همهٔ فونت‌های خودمیزبان ۴۰۴ می‌شدند و
   مرورگر بی‌صدا به فونت سیستم برمی‌گشت. این تست همان را قفل می‌کند.
"""
from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "api" / "main.py"
MINI = ROOT / "miniapp"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class LandingSourceContractTests(unittest.TestCase):
    """منبع لندینگ — بیلد، ورودی، و اینکه «اپ» نیست."""

    def test_landing_entry_exists(self):
        self.assertTrue((MINI / "landing.html").is_file(), "miniapp/landing.html نیست")
        self.assertTrue((MINI / "src" / "landing" / "Landing.jsx").is_file())
        self.assertTrue((MINI / "src" / "landing" / "landing.css").is_file())
        self.assertTrue((MINI / "src" / "landing" / "main-landing.jsx").is_file())

    def test_landing_build_script_and_env(self):
        pkg = json.loads(read(MINI / "package.json"))
        self.assertIn("build:landing", pkg["scripts"])
        env = read(MINI / ".env.landing")
        self.assertIn("VITE_APP_MODE=landing", env)
        self.assertIn("VITE_BASE=/", env)
        self.assertIn("dist-landing", env)

    def test_vite_landing_mode(self):
        cfg = read(MINI / "vite.config.js")
        self.assertIn("landing.html", cfg)
        self.assertIn("landingAssets", cfg)
        # دارایی لندینگ باید نام اختصاصی داشته باشد، نه /assets/ مشترک
        self.assertIn("landing-assets", cfg)

    def test_landing_html_is_rtl_and_no_app_shell(self):
        html = read(MINI / "landing.html")
        self.assertIn('lang="fa"', html)
        self.assertIn('dir="rtl"', html)
        self.assertIn('name="description"', html)
        self.assertIn("viewport-fit=cover", html)
        # لندینگ نباید manifest/sw داشته باشد (وگرنه خودش «نصب‌شدنی» می‌شود)
        self.assertNotIn('rel="manifest"', html)
        self.assertNotIn("serviceWorker", read(MINI / "src" / "landing" / "main-landing.jsx"))

    def test_landing_has_no_hardcoded_bot_username(self):
        """آدرس ربات فقط از کانفیگ سرور می‌آید — هیچ یوزرنیم حدسی."""
        src = read(MINI / "src" / "landing" / "Landing.jsx")
        self.assertIn("/api/web/auth/config", src)
        self.assertNotIn("t.me/", src)

    def test_landing_respects_accessibility_basics(self):
        src = read(MINI / "src" / "landing" / "Landing.jsx")
        css = read(MINI / "src" / "landing" / "landing.css")
        self.assertIn('className="lp-skip"', src)          # skip link
        self.assertIn("focus-visible", css)                 # تمرکز دیده شود
        self.assertIn("prefers-reduced-motion", css)        # حرکت محترم
        self.assertIn("100dvh", css)                        # نه 100vh
        self.assertIn("aria-hidden=\"true\"", src)          # آیکون تزئینی
        # هیچ ایموجی‌ای به‌جای آیکون نباشد (کامنت‌های کد استثناست —
        # قانون پروژه اجازهٔ ایموجی در کامنت‌ها را می‌دهد، نه در UI را)
        import re
        code_only = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
        code_only = re.sub(r"^\s*//.*$", "", code_only, flags=re.M)
        emoji = re.findall(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", code_only)
        self.assertEqual(emoji, [], f"ایموجی در UI لندینگ: {emoji}")
        # هدف لمسی دکمه‌ها ≥ ۴۴px اعلام شده باشد
        self.assertIn("min-height: 44px", css)

    def test_landing_sections_follow_trust_authority_order(self):
        """الگوی «Trust & Authority + Conversion»: Hero → اعتماد → راه‌حل → CTA."""
        src = read(MINI / "src" / "landing" / "Landing.jsx")
        order = [src.index(m) for m in ("lp-hero", "lp-proof", 'id="features"', 'id="how"',
                                        'id="platforms"', 'id="faq"', "lp-final")]
        self.assertEqual(order, sorted(order), "ترتیب بخش‌ها جابه‌جا شده")

    def test_dockerfile_builds_landing(self):
        docker = read(ROOT / "Dockerfile")
        self.assertIn("build:landing", docker)
        self.assertIn("dist-landing", docker)
        self.assertIn("miniapp/dist-landing/index.html", docker)


class LandingServingTests(unittest.TestCase):
    """سرو واقعی در FastAPI (بدون Mongo — فقط مسیرها و فایل‌ها)."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
        os.environ.setdefault("MONGODB_DB", "test")
        os.environ.setdefault("BOT_TOKEN", "1:test")
        os.environ.setdefault("ADMIN_ID", "1")
        from fastapi.testclient import TestClient
        from api.main import app
        cls.client = TestClient(app)

    def test_root_serves_landing_or_redirects_when_not_built(self):
        r = self.client.get("/", follow_redirects=False)
        index = ROOT / "miniapp" / "dist-landing" / "index.html"
        if index.is_file():
            self.assertEqual(r.status_code, 200, r.text[:200])
            self.assertIn("text/html", r.headers.get("content-type", ""))
            self.assertIn("هامزیار", r.text)
        else:
            # بدون بیلد: همان رفتار قبلی حفظ می‌شود (۳۰۷ به /app/)
            self.assertEqual(r.status_code, 307)

    def test_root_is_never_cached_hard(self):
        r = self.client.get("/", follow_redirects=False)
        cc = r.headers.get("cache-control", "")
        self.assertNotIn("immutable", cc)

    def test_unknown_path_still_404(self):
        """mount روی ریشه نگذاشتیم؛ مسیر ناشناس نباید HTML بگیرد."""
        r = self.client.get("/this-path-does-not-exist", follow_redirects=False)
        self.assertEqual(r.status_code, 404)

    def test_api_still_404_json(self):
        r = self.client.get("/api/definitely-not-a-route")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json().get("detail"), "not_found")

    def test_shared_fonts_are_served(self):
        """فونت خودمیزبان باید روی /fonts/... واقعاً ۲۰۰ بدهد."""
        for name in ("vazirmatn-arabic.woff2", "vazirmatn-latin.woff2"):
            self.assertTrue((MINI / "public" / "fonts" / name).is_file(), name)
            r = self.client.get(f"/fonts/{name}")
            self.assertEqual(r.status_code, 200, f"{name} → {r.status_code}")
            self.assertIn("font", r.headers.get("content-type", ""))

    def test_shared_icons_are_served(self):
        r = self.client.get("/icons/icon-192.png")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers.get("content-type"), "image/png")

    def test_missing_font_is_404_not_html(self):
        r = self.client.get("/fonts/does-not-exist.woff2")
        self.assertEqual(r.status_code, 404)

    def test_landing_assets_are_served(self):
        assets = ROOT / "miniapp" / "dist-landing" / "landing-assets"
        if not assets.is_dir():
            self.skipTest("landing not built")
        css = sorted(p.name for p in assets.glob("*.css"))
        self.assertTrue(css, "هیچ CSS‌ای در landing-assets نیست")
        r = self.client.get(f"/landing-assets/{css[0]}")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/css", r.headers.get("content-type", ""))

    def test_health_reports_landing_state(self):
        data = self.client.get("/api/health").json()
        self.assertIn("landing", data)
        self.assertIsInstance(data["landing"], bool)


if __name__ == "__main__":
    unittest.main()
