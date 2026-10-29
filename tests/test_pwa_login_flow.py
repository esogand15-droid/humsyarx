# -*- coding: utf-8 -*-
"""🔐 تست عملکردی جریان کامل ورود وب/PWA (بدون Mongo واقعی).

تست قراردادی (`test_pwa_login_contract.py`) فقط *وجود* مسیرها را چک
می‌کند؛ این فایل **رفتار** را چک می‌کند: کد صادر می‌شود، به صف
`bot_notifications` می‌رود، کد غلط تلاش را زیاد می‌کند، کد درست کوکی
HttpOnly می‌دهد، نشست با همان کوکی معتبر است، و خروج آن را باطل می‌کند.

دیتابیس با یک فیک کوچک شبیه‌سازی می‌شود (همان الگوی
`tests/test_w7_access.py` در همین مخزن)؛ هیچ اتصال شبکه‌ای برقرار نمی‌شود.
"""
from __future__ import annotations

import re
import unittest
from datetime import timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import web_login_core as core
from api.routers import web_login


# ── فیک مینیمال Mongo ────────────────────────────────────────────
def _match(doc: dict, filt: dict) -> bool:
    for key, want in filt.items():
        have = doc.get(key)
        if isinstance(want, dict) and "$regex" in want:
            flags = re.IGNORECASE if str(want.get("$options", "")).lower() == "i" else 0
            if have is None or not re.search(want["$regex"], str(have), flags):
                return False
        elif want is None:
            if have is not None:
                return False
        elif have != want:
            return False
    return True


class FakeColl:
    def __init__(self):
        self.docs: list[dict] = []

    async def find_one(self, filt, *a, **kw):
        for d in self.docs:
            if _match(d, filt):
                return dict(d)
        return None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def delete_many(self, filt):
        self.docs = [d for d in self.docs if not _match(d, filt)]

    async def update_one(self, filt, upd, upsert=False):
        for d in self.docs:
            if _match(d, filt):
                for k, v in (upd.get("$inc") or {}).items():
                    d[k] = d.get(k, 0) + v
                for k, v in (upd.get("$set") or {}).items():
                    d[k] = v
                return


class FakeClient:
    def __init__(self):
        self.colls: dict[str, FakeColl] = {}

    def __getitem__(self, name):
        return self.colls.setdefault(name, FakeColl())


class FakeDB:
    def __init__(self, users):
        self.client = {"medicalbot": FakeClient()}
        self.users = FakeColl()
        for u in users:
            self.users.docs.append(dict(u))
        self.actions: list[tuple] = []

    async def get_user(self, uid):
        return await self.users.find_one({"user_id": int(uid)})

    async def log_action(self, uid, name, action, details="", tags=None):
        self.actions.append((int(uid), action, tuple(tags or ())))


APPROVED = {
    "user_id": 100200300, "name": "علی رضایی", "approved": True,
    "username": "ali_rezaei", "student_id": "401234567",
    "phone": "09123456789",
}
PENDING = {"user_id": 5550001, "name": "در انتظار", "approved": False,
           "username": "waiting"}
SUSPENDED = {"user_id": 5550002, "name": "تعلیق", "approved": True,
             "suspended": True, "username": "suspended"}
UNKNOWN_UID = 999000111


def reset_limits():
    core.IDENT_LIMITER.reset()
    core.IP_LIMITER.reset()


class WebLoginFlowTests(unittest.TestCase):
    def setUp(self):
        reset_limits()
        self.db = FakeDB([APPROVED, PENDING, SUSPENDED])
        self._orig = web_login.db
        web_login.db = self.db
        app = FastAPI()
        app.include_router(web_login.router, prefix="/api/web-auth")
        self.client = TestClient(app)
        self.otps = lambda: self.db.client["medicalbot"]["web_user_otps"]
        self.sessions = lambda: self.db.client["medicalbot"]["web_user_sessions"]
        self.outbox = lambda: self.db.client["medicalbot"]["bot_notifications"]

    def tearDown(self):
        web_login.db = self._orig
        reset_limits()

    # ── helpers ──
    def request_code(self, ident, **kw):
        return self.client.post("/api/web-auth/request", json={"identifier": ident}, **kw)

    def stored_code(self, uid):
        """کد خام را از متن پیام صف درمی‌آورد (کاربر هم همین را می‌بیند)."""
        for msg in reversed(self.outbox().docs):
            if msg.get("type") == "web_login_otp" and msg.get("chat_id") == uid:
                return re.search(r"<code>(\d{6})</code>", msg["text"]).group(1)
        return None

    def verify(self, ident, code):
        return self.client.post("/api/web-auth/verify",
                               json={"identifier": ident, "code": code})

    # ── ۱) مسیر خوش ──
    def test_full_happy_path(self):
        r = self.request_code("@ali_rezaei")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["ok"])

        # کد واقعاً ساخته و به صف ربات تحویل شده
        self.assertEqual(len(self.otps().docs), 1)
        otp_doc = self.otps().docs[0]
        self.assertEqual(otp_doc["uid"], APPROVED["user_id"])
        self.assertNotIn("code", otp_doc)  # کد خام ذخیره نشده
        self.assertEqual(otp_doc["attempts"], 0)
        self.assertEqual(len(self.outbox().docs), 1)
        msg = self.outbox().docs[0]
        self.assertEqual(msg["type"], "web_login_otp")
        self.assertEqual(msg["chat_id"], APPROVED["user_id"])
        self.assertFalse(msg["sent"])

        code = self.stored_code(APPROVED["user_id"])
        self.assertEqual(len(code), 6)

        r = self.verify("@ali_rezaei", code)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["user"]["uid"], APPROVED["user_id"])

        # کوکی HttpOnly صادر شده
        cookie = r.cookies.get(core.SESSION_COOKIE)
        self.assertTrue(cookie)
        # OTP سوخته، نشست ساخته شده و در DB فقط هش توکن است
        self.assertEqual(self.otps().docs, [])
        self.assertEqual(len(self.sessions().docs), 1)
        self.assertNotEqual(self.sessions().docs[0]["_id"], cookie)
        self.assertEqual(self.sessions().docs[0]["revoked"], False)

        # نشست با همان کوکی
        r = self.client.get("/api/web-auth/session")
        self.assertTrue(r.json()["authenticated"])
        self.assertEqual(r.json()["uid"], APPROVED["user_id"])

        # خروج → باطل
        r = self.client.post("/api/web-auth/logout")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(self.sessions().docs[0]["revoked"])
        r = self.client.get("/api/web-auth/session")
        self.assertFalse(r.json()["authenticated"])

        # حسابرسی ورود ثبت شده
        self.assertTrue(any("ورود" in a[1] for a in self.db.actions))

    def test_login_by_student_id_and_phone(self):
        for ident in ("401234567", "09123456789", "100200300"):
            reset_limits()
            self.db.client["medicalbot"]["web_user_otps"].docs = []
            r = self.request_code(ident)
            self.assertEqual(r.status_code, 200, ident)
            self.assertEqual(len(self.otps().docs), 1, ident)
            code = self.stored_code(APPROVED["user_id"])
            self.assertEqual(self.verify(ident, code).status_code, 200, ident)

    def test_persian_digits_accepted(self):
        r = self.request_code("۱۰۰۲۰۰۳۰۰")
        self.assertEqual(r.status_code, 200)
        code = self.stored_code(APPROVED["user_id"])
        fa = "".join("۰۱۲۳۴۵۶۷۸۹"[int(d)] for d in code)  # کل کد با ارقام فارسی
        self.assertEqual(self.verify("۱۰۰۲۰۰۳۰۰", fa).status_code, 200)

    # ── ۲) جلوگیری از شمارش حساب ──
    def test_unknown_and_pending_get_same_response(self):
        r1 = self.request_code("@nobody_here")
        r2 = self.request_code("@waiting")
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r1.json()["message"], r2.json()["message"])
        # برای این‌ها هیچ کدی ساخته نشده
        self.assertEqual(self.otps().docs, [])
        self.assertEqual(self.outbox().docs, [])

    def test_verify_pending_user_is_generic_error(self):
        r = self.verify("@waiting", "123456")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()["detail"], core.GENERIC_CODE_ERROR)
        self.assertNotIn("websession", r.headers.get("set-cookie", ""))

    def test_suspended_cannot_login(self):
        self.request_code("@suspended")
        self.assertEqual(self.outbox().docs, [])

    # ── ۳) کد غلط / انقضا / سقف تلاش ──
    def test_wrong_code_increments_attempts(self):
        self.request_code("@ali_rezaei")
        code = self.stored_code(APPROVED["user_id"])
        wrong = "000000" if code != "000000" else "111111"
        r = self.verify("@ali_rezaei", wrong)
        self.assertEqual(r.status_code, 401)
        self.assertEqual(self.otps().docs[0]["attempts"], 1)
        # کد درست بعد از آن هنوز کار می‌کند (attempts < سقف)
        self.assertEqual(self.verify("@ali_rezaei", code).status_code, 200)

    def test_attempt_cap_blocks_bruteforce(self):
        self.request_code("@ali_rezaei")
        code = self.stored_code(APPROVED["user_id"])
        wrong = "000000" if code != "000000" else "111111"
        for _ in range(core.OTP_MAX_ATTEMPTS):
            self.verify("@ali_rezaei", wrong)
        r = self.verify("@ali_rezaei", code)  # حتی با کد درست
        self.assertEqual(r.status_code, 429)
        self.assertEqual(self.sessions().docs, [])

    def test_expired_code_rejected(self):
        self.request_code("@ali_rezaei")
        code = self.stored_code(APPROVED["user_id"])
        self.otps().docs[0]["expires_at"] = core.now_utc() - timedelta(seconds=1)
        r = self.verify("@ali_rezaei", code)
        self.assertEqual(r.status_code, 401)
        self.assertEqual(self.sessions().docs, [])

    def test_cooldown_blocks_instant_resend(self):
        self.assertEqual(self.request_code("@ali_rezaei").status_code, 200)
        r = self.request_code("@ali_rezaei")
        self.assertEqual(r.status_code, 429)
        self.assertIn("ثانیه", r.json()["detail"])
        self.assertEqual(len(self.outbox().docs), 1)

    def test_resend_allowed_after_cooldown(self):
        self.request_code("@ali_rezaei")
        self.otps().docs[0]["created_at"] = core.now_utc() - timedelta(seconds=120)
        r = self.request_code("@ali_rezaei")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(self.outbox().docs), 2)  # کد تازه در صف
        self.assertEqual(len(self.otps().docs), 1)    # فقط آخرین کد معتبر است

    def test_identifier_rate_limit(self):
        reset_limits()
        codes = []
        for _ in range(core.IDENT_LIMITER.limit):
            self.otps().docs = []
            codes.append(self.request_code("@ali_rezaei").status_code)
        r = self.request_code("@ali_rezaei")
        self.assertEqual(r.status_code, 429)
        self.assertTrue(all(c == 200 for c in codes))

    # ── ۴) کوکی و پرچم‌ها ──
    def test_cookie_is_httponly_and_secure_behind_proxy(self):
        self.request_code("@ali_rezaei")
        code = self.stored_code(APPROVED["user_id"])
        r = self.client.post("/api/web-auth/verify",
                             json={"identifier": "@ali_rezaei", "code": code},
                             headers={"x-forwarded-proto": "https"})
        raw = r.headers["set-cookie"]
        self.assertIn("HttpOnly", raw)
        self.assertIn("Secure", raw)
        self.assertIn("SameSite=lax", raw.lower().replace("samesite=lax", "SameSite=lax"))
        self.assertIn("Path=/", raw)

    def test_no_secure_flag_on_plain_http(self):
        self.request_code("@ali_rezaei")
        code = self.stored_code(APPROVED["user_id"])
        self.verify("@ali_rezaei", code)
        # کوکی جدید در آخرین پاسخ
        self.request_code  # noqa: B018  (فقط برای خوانایی)
        reset_limits()
        self.otps().docs = []
        self.request_code("@ali_rezaei")
        code = self.stored_code(APPROVED["user_id"])
        r = self.client.post("/api/web-auth/verify",
                             json={"identifier": "@ali_rezaei", "code": code})
        self.assertNotIn("Secure", r.headers["set-cookie"])

    # ── ۵) نشست ──
    def test_session_endpoint_without_cookie(self):
        r = self.client.get("/api/web-auth/session")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["authenticated"])

    def test_session_endpoint_rejects_forged_cookie(self):
        self.client.cookies.set(core.SESSION_COOKIE, "forged-token-value")
        r = self.client.get("/api/web-auth/session")
        self.assertFalse(r.json()["authenticated"])

    def test_session_endpoint_rejects_expired(self):
        self.request_code("@ali_rezaei")
        code = self.stored_code(APPROVED["user_id"])
        self.verify("@ali_rezaei", code)
        self.sessions().docs[0]["expires_at"] = core.now_utc() - timedelta(minutes=1)
        r = self.client.get("/api/web-auth/session")
        self.assertFalse(r.json()["authenticated"])

    def test_auth_resolver_accepts_cookie_token(self):
        """همان کوکی که روتر صادر می‌کند باید در `get_current_user` معتبر باشد."""
        import asyncio

        from api import auth
        self.request_code("@ali_rezaei")
        code = self.stored_code(APPROVED["user_id"])
        r = self.verify("@ali_rezaei", code)
        token = r.cookies.get(core.SESSION_COOKIE)
        self.assertTrue(token)
        self.assertEqual(auth.WEB_SESSION_COOKIE, core.SESSION_COOKIE)

        # فقط هش توکن در DB است — نه توکن خام
        self.assertNotIn(token, str(self.sessions().docs))
        self.assertEqual(self.sessions().docs[0]["_id"], auth._hash_token(token))

        orig_auth_db = auth.db
        auth.db = self.db
        # ⚠️ هر دو فراخوانی داخل try باشند: بیرون از آن، resolver به
        # کلاینت واقعیِ Mongo می‌رسد و تست ۳۰ ثانیه منتظر server-selection
        # می‌ماند (در CI هم همین اتفاق می‌افتاد).
        try:
            loop = asyncio.new_event_loop()
            doc = loop.run_until_complete(auth.resolve_web_user_session(token))
            forged = loop.run_until_complete(
                auth.resolve_web_user_session("forged-token"))
            loop.close()
        finally:
            auth.db = orig_auth_db
        self.assertIsNotNone(doc)
        self.assertEqual(doc["uid"], APPROVED["user_id"])
        self.assertIsNone(forged)  # توکن جعلی رد می‌شود


if __name__ == "__main__":
    unittest.main()
