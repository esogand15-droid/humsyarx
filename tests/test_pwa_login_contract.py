# -*- coding: utf-8 -*-
"""📲 قرارداد ورود وب/PWA + نصب‌پذیری نسخهٔ نصب‌شدنی.

چرا این تست؟
────────────
تا امروز مینی‌اپ فقط داخل تلگرام کار می‌کرد: `get_current_user` بدون
`initData` همیشه ۴۰۱ می‌داد. یعنی PWA «نصب می‌شد ولی کار نمی‌کرد» —
و هیچ تستی هم آن را نمی‌گرفت.

این فایل دو چیز را قفل می‌کند:
  ۱) **منطق خالص** هستهٔ ورود (هش کد، مقایسهٔ ثابت‌زمان، انقضا،
     نرمال‌سازی شناسه، محدودیت نرخ) — بدون Mongo، همیشه اجرا می‌شود.
  ۲) **قرارداد سیمی**: روتر ثبت شده، auth مسیر کوکی را می‌شناسد،
     بیلد PWA با base درست/manifest/sw/offline ساخته می‌شود، و در
     حالت PWA صفحهٔ ورود جای «از داخل تلگرام باز کنید» را می‌گیرد.
"""
from __future__ import annotations

import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(*parts: str) -> str:
    return ROOT.joinpath(*parts).read_text(encoding="utf-8")


class CoreHashTests(unittest.TestCase):
    """هش/مقایسهٔ کد — پایهٔ امنیت ورود."""

    def setUp(self):
        from api import web_login_core as core
        self.core = core

    def test_code_is_six_digits(self):
        for _ in range(50):
            code = self.core.make_code()
            self.assertEqual(len(code), self.core.OTP_LENGTH)
            self.assertTrue(code.isdigit())

    def test_hash_is_salted_and_stable(self):
        c = self.core
        salt = c.make_salt()
        h1 = c.hash_code(salt, "123456")
        h2 = c.hash_code(salt, "123456")
        self.assertEqual(h1, h2)
        self.assertNotEqual(h1, c.hash_code("other-salt", "123456"))
        # کد خام هرگز داخل هش نیست
        self.assertNotIn("123456", h1)

    def test_compare_digest_semantics(self):
        c = self.core
        salt = c.make_salt()
        stored = c.hash_code(salt, "654321")
        self.assertTrue(c.code_matches(salt, "654321", stored))
        self.assertFalse(c.code_matches(salt, "654322", stored))
        self.assertFalse(c.code_matches(salt, "", stored))
        self.assertFalse(c.code_matches(salt, "654321", ""))
        # salt گم‌شده نباید استثنا بدهد
        self.assertFalse(c.code_matches(None, "654321", stored))

    def test_session_token_and_hash(self):
        c = self.core
        token = c.new_session_token()
        self.assertGreaterEqual(len(token), 32)
        self.assertNotEqual(token, c.new_session_token())
        self.assertEqual(len(c.hash_token(token)), 64)
        self.assertNotIn(token, c.hash_token(token))


class CoreExpiryTests(unittest.TestCase):

    def setUp(self):
        from api import web_login_core as core
        self.core = core

    def test_is_past(self):
        c = self.core
        self.assertTrue(c.is_past(datetime.now(timezone.utc) - timedelta(minutes=1)))
        self.assertFalse(c.is_past(datetime.now(timezone.utc) + timedelta(minutes=1)))
        # naive datetime باید امن تفسیر شود (نه استثنا)
        self.assertTrue(c.is_past(datetime.utcnow() - timedelta(hours=1)))
        # نوع نامعتبر = منقضی (fail-closed)
        self.assertTrue(c.is_past(None))
        self.assertTrue(c.is_past("2026-10-29"))

    def test_seconds_until_never_negative(self):
        c = self.core
        self.assertEqual(c.seconds_until(datetime.now(timezone.utc) - timedelta(hours=2)), 0)
        self.assertGreater(c.seconds_until(datetime.now(timezone.utc) + timedelta(minutes=2)), 60)

    def test_session_ttl_is_clamped(self):
        c = self.core
        os.environ["WEB_SESSION_TTL_DAYS"] = "9999"
        try:
            self.assertLessEqual(c.session_ttl_days(), c.SESSION_TTL_DAYS_MAX)
            os.environ["WEB_SESSION_TTL_DAYS"] = "-5"
            self.assertGreaterEqual(c.session_ttl_days(), 1)
        finally:
            os.environ.pop("WEB_SESSION_TTL_DAYS", None)


class CoreIdentifierTests(unittest.TestCase):

    def setUp(self):
        from api import web_login_core as core
        self.core = core

    def test_normalization(self):
        c = self.core
        self.assertEqual(c.normalize_identifier("  @Ali_Reza "), "Ali_Reza")
        self.assertEqual(c.normalize_identifier("۴۰۱۲۳۴۵۶۷"), "401234567")
        self.assertEqual(c.normalize_identifier(""), "")
        self.assertEqual(c.normalize_identifier(None), "")
        self.assertLessEqual(len(c.normalize_identifier("x" * 500)), 64)

    def test_numeric_detection(self):
        c = self.core
        self.assertTrue(c.is_numeric_identifier("100200300"))
        self.assertFalse(c.is_numeric_identifier("@name"))
        self.assertFalse(c.is_numeric_identifier(""))

    def test_phone_detection(self):
        c = self.core
        self.assertTrue(c.looks_like_phone("09123456789"))
        self.assertTrue(c.looks_like_phone("9123456789"))
        self.assertFalse(c.looks_like_phone("401234567"))

    def test_mask_never_leaks(self):
        c = self.core
        masked = c.mask_identifier("100200300")
        self.assertNotEqual(masked, "100200300")
        self.assertEqual(masked[0], "1")
        self.assertEqual(c.mask_identifier("۱۲۳"), "***")


class CoreRateLimitTests(unittest.TestCase):

    def test_window_blocks_after_limit(self):
        from api import web_login_core as core
        limiter = core.SlidingWindowLimiter(limit=3, window_sec=60)
        self.assertTrue(limiter.allow("k", at=0))
        self.assertTrue(limiter.allow("k", at=1))
        self.assertTrue(limiter.allow("k", at=2))
        self.assertFalse(limiter.allow("k", at=3))
        # پنجرهٔ لغزان: بعد از ۶۰ ثانیه آزاد می‌شود
        self.assertTrue(limiter.allow("k", at=61))
        # کلید دیگر مستقل است
        self.assertTrue(limiter.allow("other", at=61))

    def test_request_allowed_checks_ip_first(self):
        from api import web_login_core as core
        core.IP_LIMITER.reset()
        core.IDENT_LIMITER.reset()
        try:
            results = [core.request_allowed("100", "1.1.1.1") for _ in range(20)]
            self.assertIn(False, results)  # سقف IP یا شناسه فعال می‌شود
            self.assertTrue(results[0])
        finally:
            core.IP_LIMITER.reset()
            core.IDENT_LIMITER.reset()


class RouterContractTests(unittest.TestCase):
    """قرارداد سیمی — روتر ثبت شده و auth مسیر کوکی را می‌شناسد."""

    def setUp(self):
        self.main = read("api", "main.py")
        self.auth = read("api", "auth.py")
        self.router = read("api", "routers", "web_login.py")

    def test_router_registered_with_prefix(self):
        self.assertIn("web_login", self.main)
        self.assertIn('prefix="/api/web-auth"', self.main)

    def test_endpoints_exist(self):
        for route in ("/request", "/verify", "/session", "/logout"):
            found = (f'@router.post("{route}")' in self.router
                     or f'@router.get("{route}")' in self.router)
            self.assertTrue(found, f"endpoint {route} تعریف نشده")

    def test_auth_resolves_web_session_cookie(self):
        self.assertIn('WEB_SESSION_COOKIE = "hu_session"', self.auth)
        self.assertIn("resolve_web_user_session", self.auth)
        self.assertIn("web_user_sessions", self.auth)
        # سشن کاربر و سشن ادمین نباید یکی باشند
        self.assertIn('WA_SESSION_COOKIE = "wa_session"', self.auth)

    def test_no_account_enumeration_message(self):
        """پاسخ «درخواست کد» نباید وجود/عدم‌وجود حساب را لو بدهد."""
        self.assertNotIn("کاربر یافت نشد", self.router)
        self.assertNotIn("حساب وجود ندارد", self.router)
        self.assertIn("GENERIC_REQUEST_MESSAGE", self.router)

    def test_code_never_stored_plaintext(self):
        # فقط hش کد ذخیره می‌شود، نه خودِ کد
        self.assertIn('"code_hash"', self.router)
        store_block = self.router.split("code_hash", 1)[1][:400]
        self.assertNotIn('"code": code', store_block)

    def test_cookie_is_httponly(self):
        self.assertIn("httponly=True", self.router)
        self.assertIn("samesite=\"lax\"", self.router)


class PwaBuildContractTests(unittest.TestCase):
    """بیلد نصب‌شدنی — همان کد، پوستهٔ مستقل."""

    def test_vite_has_pwa_mode(self):
        cfg = read("miniapp", "vite.config.js")
        self.assertIn("VITE_APP_MODE", cfg)
        self.assertIn("dist-pwa", cfg)
        pkg = json.loads(read("miniapp", "package.json"))
        self.assertIn("build:pwa", pkg["scripts"])

    def test_env_pwa_points_to_pwa_base(self):
        env = read("miniapp", ".env.pwa")
        self.assertIn("VITE_APP_MODE=pwa", env)
        self.assertIn("VITE_BASE=/pwa/", env)
        self.assertIn("dist-pwa", env)

    def test_pwa_manifest_is_installable(self):
        manifest_path = ROOT / "miniapp" / "public-pwa" / "manifest.webmanifest"
        self.assertTrue(manifest_path.is_file(), "manifest نسخهٔ PWA وجود ندارد")
        m = json.loads(manifest_path.read_text(encoding="utf-8"))
        for field in ("name", "short_name", "start_url", "display", "icons",
                      "theme_color", "background_color", "scope"):
            self.assertIn(field, m)
        self.assertEqual(m["display"], "standalone")
        self.assertEqual(m["lang"], "fa")
        self.assertEqual(m["dir"], "rtl")
        sizes = {icon["sizes"] for icon in m["icons"]}
        self.assertIn("192x192", sizes)
        self.assertIn("512x512", sizes)
        self.assertTrue(any(i.get("purpose") == "maskable" for i in m["icons"]))
        # اسکرین‌شات‌ها فقط اگر واقعاً موجود باشند اعلام شوند
        for shot in m.get("screenshots", []):
            p = manifest_path.parent / shot["src"].lstrip("./")
            self.assertTrue(p.is_file(), f"اسکرین‌شات اعلام‌شده موجود نیست: {shot['src']}")

    def test_pwa_icons_exist(self):
        icons = ROOT / "miniapp" / "public-pwa" / "icons"
        for name in ("icon-192.png", "icon-512.png", "maskable-512.png",
                     "apple-touch-icon.png"):
            self.assertTrue((icons / name).is_file(), f"آیکون نیست: {name}")

    def test_service_worker_is_offline_aware(self):
        sw = read("miniapp", "public-pwa", "sw.js")
        self.assertIn("offline.html", sw)
        self.assertIn("addEventListener('fetch'", sw)
        # دادهٔ کاربر هرگز کش نشود
        self.assertIn("startsWith('/api/')", sw)
        self.assertIn("return;", sw.split("startsWith('/api/')", 1)[1][:80])

    def test_offline_page_exists_and_is_rtl(self):
        html = read("miniapp", "public-pwa", "offline.html")
        self.assertIn('dir="rtl"', html)
        self.assertIn("آفلاین", html)

    def test_main_mounts_pwa(self):
        self.assertIn('"/pwa"', read("api", "main.py"))
        self.assertIn("dist-pwa", read("api", "main.py"))

    def test_telegram_flag_requires_initdata(self):
        """شیء WebApp تنها کافی نیست — بدون initData یعنی «داخل تلگرام نیستیم»."""
        tg = read("miniapp", "src", "lib", "telegram.js")
        self.assertIn("Boolean(tg && tg.initData)", tg)

    def test_pwa_login_screen_wired(self):
        app = read("miniapp", "src", "App.jsx")
        self.assertIn("WebLogin", app)
        self.assertIn("IS_PWA", app)
        self.assertIn("web_login_required", app)

    def test_login_errors_are_wired_to_fields(self):
        """راهنمای Skill: خطا باید role=alert داشته باشد و به فیلد وصل شود."""
        src = read("miniapp", "src", "components", "pwa", "WebLogin.jsx")
        self.assertIn('id="pwa-auth-error"', src)
        self.assertIn('role="alert"', src)
        self.assertEqual(src.count("aria-invalid"), 2, "هر دو فیلد باید aria-invalid بگیرند")
        self.assertEqual(src.count("aria-describedby"), 2)
        self.assertIn('aria-describedby={error ? \'pwa-auth-error\' : undefined}', src)

    def test_pwa_mode_ignores_telegram(self):
        """در PWA حتی اگر اسکریپت تلگرام لود شود، مسیر «نشست وب» تصمیم می‌گیرد."""
        store = read("miniapp", "src", "stores", "authStore.js")
        self.assertIn("IS_PWA || !isTelegram", store)
        self.assertIn("/api/web-auth/session", store)


if __name__ == "__main__":
    unittest.main()
