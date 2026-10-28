# -*- coding: utf-8 -*-
"""🌊 W2 — پرداخت آنلاین زرین‌پال (ربات + مینی‌اپ + شارژ با درگاه).

۱) گارد ایستا: بک‌اند (gateway-status / zarinpal/topup / clamp کال‌بک)،
   ربات (sub:zpay/zchk/ztop + مالکیت)، مینی‌اپ (هوک + لندینگ + wiring).
۲) mock درگاه بدون DB: چرخه‌ی request→verify حالتی (کش کانفیگ seed می‌شود
   تا به Mongo دست نزند).
۳) runtime با Mongo محلی: خرید پلن + شارژ کیف پول + replay بدون اثر دوباره.

داده با پیشوند w2؛ در پایان پاک می‌شود. loop مشترک (tests/_rtloop).
"""
import asyncio
import os
import socket
import time
import unittest
from pathlib import Path

from bson import ObjectId as OID

ROOT = Path(__file__).resolve().parents[1]

W2_BUYER = 889101
W2_TOPUP = 889102

P_W2_BUY = OID(f"{301:024x}")
P_W2_TOPUP = OID(f"{302:024x}")


def read(*parts: str) -> str:
    return ROOT.joinpath(*parts).read_text(encoding="utf-8")


class GatewayStaticTests(unittest.TestCase):
    """گاردهای ایستای سیم‌کشی W2."""

    def test_backend_gateway_status_endpoint(self):
        src = read("api", "routers", "subscription.py")
        self.assertIn('@router.get("/gateway-status")', src)
        self.assertIn("gateway_public_status", src)

    def test_backend_topup_endpoint(self):
        src = read("api", "routers", "subscription.py")
        self.assertIn('@router.post("/zarinpal/topup")', src)
        idx = src.index('@router.post("/zarinpal/topup")')
        block = src[idx:idx + 2500]
        self.assertIn("wallet_topup", block)
        self.assertIn("sub_payment_has_pending", block)
        self.assertIn("topup_min", block)

    def test_backend_callback_clamped(self):
        src = read("api", "routers", "subscription.py")
        self.assertIn("def _clamp_callback_url", src)
        # هر دو مسیر ساخت پرداخت باید از clamp رد شوند
        self.assertGreaterEqual(src.count("_clamp_callback_url("), 3)

    def test_backend_normalize_exposes_pending_authority(self):
        src = read("api", "routers", "subscription.py")
        self.assertIn('"authority"', src)
        self.assertIn("zarinpal_pending", src)

    def test_payments_public_status_has_no_secrets(self):
        src = read("payments", "zarinpal.py")
        self.assertIn("async def gateway_public_status", src)
        idx = src.index("async def gateway_public_status")
        block = src[idx:idx + 600]
        for key in ('"online_pay_enabled":', '"mock":',
                    '"sandbox":', '"bot_username":'):
            self.assertIn(key, block)
        # مقدار secret هرگز در دیکشنری برگشتی نیست (تست runtime هم چک می‌کند)
        self.assertNotIn("MERCHANT_ID", block)

    def test_bot_online_pay_wired(self):
        src = read("subscription.py")
        for token in ("sub:zpay:", "sub:zchk:", "sub:ztop:",
                      "_zarinpal_start", "_zarinpal_check",
                      "_gateway_status"):
            self.assertIn(token, src, f"ربات {token} را ندارد")

    def test_bot_verify_checks_ownership(self):
        src = read("subscription.py")
        idx = src.index("async def _zarinpal_check")
        block = src[idx:idx + 1500]
        self.assertIn("user_id", block)
        self.assertIn("متعلق به شما نیست", block)

    def test_miniapp_hook_and_landing(self):
        hook = read("miniapp", "src", "hooks", "useZarinpalPay.js")
        for token in ("zarinpal/request", "zarinpal/topup",
                      "zarinpal/verify", "gateway-status",
                      "humsyar_zp_pending", "openExternalLink"):
            self.assertIn(token, hook, f"هوک {token} را ندارد")
        page = read("miniapp", "src", "pages", "Payment", "Verify.jsx")
        # لندینگ بدون احراز هویت verify نمی‌کند
        self.assertIn("getInitData", page)
        self.assertIn("hasAuth", page)
        self.assertIn("/zarinpal/verify", page)
        app = read("miniapp", "src", "App.jsx")
        self.assertIn('/payment/verify', app)
        page_sub = read("miniapp", "src", "pages", "Me", "Subscription.jsx")
        for token in ("useZarinpalPay", "useGatewayStatus",
                      "پرداخت آنلاین (زرین‌پال)", "شارژ آنی با درگاه",
                      "پرداخت کردم، بررسی کن", "zarinpal_pending"):
            self.assertIn(token, page_sub, f"Subscription ‏{token} را ندارد")

    def test_telegram_open_link_helper(self):
        src = read("miniapp", "src", "lib", "telegram.js")
        self.assertIn("openExternalLink", src)
        self.assertIn("openLink", src)


class ZarinpalMockTests(unittest.TestCase):
    """چرخه‌ی mock درگاه — بدون DB (کش کانفیگ seed می‌شود)."""

    @classmethod
    def setUpClass(cls):
        import payments.zarinpal as zp
        cls.zp = zp
        # 🐞 موج ۳ — این کلاس عمداً «حالت mock» را تست می‌کند و از موج ۳
        # حالت mock به‌صورت fail-closed بسته است (محیط ناشناخته = ممنوع).
        # پس محیط توسعه را صریح اعلام می‌کنیم؛ در غیر این صورت تست، رفتار
        # درستِ امنیتی را «شکست» می‌دید.
        cls._env_backup = {k: os.environ.get(k) for k in
                           ("APP_ENV", "ZARINPAL_ALLOW_MOCK",
                            "RAILWAY_ENVIRONMENT_NAME", "RAILWAY_ENVIRONMENT",
                            "ENVIRONMENT")}
        os.environ["APP_ENV"] = "development"
        os.environ.pop("ZARINPAL_ALLOW_MOCK", None)
        zp._CFG_CACHE["at"] = time.time()
        zp._CFG_CACHE["data"] = {
            "merchant_id": "", "sandbox": True,
            "callback_base": "", "enabled": True,
        }

    @classmethod
    def tearDownClass(cls):
        cls.zp._clear_cfg_cache()
        for k, v in (cls._env_backup or {}).items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_mock_request_verify_roundtrip(self):
        async def go():
            req = await self.zp.zarinpal_request(
                50000, "تست W2", "https://x.test/payment/verify")
            self.assertTrue(req["authority"].startswith("TEST-"))
            self.assertIn(req["authority"], req["url"])
            self.assertTrue(req.get("mock"))
            ver = await self.zp.zarinpal_verify(req["authority"], 50000)
            self.assertTrue(ver.get("ok"))
            self.assertTrue(ver.get("ref_id"))
            self.assertTrue(ver.get("mock"))
        asyncio.run(go())

    def test_public_status_shape(self):
        async def go():
            st = await self.zp.gateway_public_status()
            self.assertEqual(
                set(st.keys()),
                {"online_pay_enabled", "mock", "sandbox", "bot_username"})
            self.assertTrue(st["online_pay_enabled"])
            self.assertTrue(st["mock"])
        asyncio.run(go())


def _mongo_available() -> bool:
    """پروب مشترک و مقاوم (پارس URI با نام دیتابیس را هم می‌فهمد).

    جزئیات علت در tests/_mongo_probe.py — نسخهٔ قبلیِ محلی با URI
    `mongodb://host:port/db` در زمان import می‌شکست و کل فایل تست را
    به error تبدیل می‌کرد.
    """
    try:                                   # اجرا با `python -m unittest tests.x`
        from tests._mongo_probe import mongo_available as _probe
    except Exception:                      # اجرا با `discover -s tests`
        try:
            from _mongo_probe import mongo_available as _probe
        except Exception:
            return False
    return _probe()


@unittest.skipUnless(_mongo_available(), "MONGODB_URI محلی در دسترس نیست (CI)")
class GatewayRuntimeTests(unittest.TestCase):
    """خرید پلن + شارژ کیف پول با authority واقعی‌نما + replay بدون اثر دوباره."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("MONGODB_URI", "mongodb://127.0.0.1:27017")
        from database import db
        cls.db = db
        from _rtloop import adopt
        adopt()
        cls.plan_id = cls._run(cls._prepare())

    @classmethod
    def tearDownClass(cls):
        cls._run(cls._clean())

    @classmethod
    def _run(cls, coro):
        from _rtloop import run
        return run(coro)

    @classmethod
    async def _prepare(cls):
        db = cls.db
        await cls._clean()
        for uid in (W2_BUYER, W2_TOPUP):
            await db.users.update_one(
                {"user_id": uid},
                {"$set": {"user_id": uid, "name": f"W2 {uid}",
                          "role": "student", "approved": True,
                          "suspended": False}},
                upsert=True)
        plan_id = await db.sub_plan_add("w2-plan", 30, 100000)
        return plan_id

    @classmethod
    async def _clean(cls):
        db = cls.db
        await db.sub_payments.delete_many(
            {"_id": {"$in": [P_W2_BUY, P_W2_TOPUP]}})
        await db.sub_payments.delete_many(
            {"idem_key": {"$regex": "^w2-"}})
        await db.sub_plans.delete_many({"name": "w2-plan"})
        await db.subscriptions.delete_many(
            {"user_id": {"$in": [W2_BUYER, W2_TOPUP]}})
        await db.wallets.delete_many(
            {"user_id": {"$in": [W2_BUYER, W2_TOPUP]}})
        await db.wallet_transactions.delete_many(
            {"user_id": {"$in": [W2_BUYER, W2_TOPUP]}})

    async def _seed_pending(self, oid, uid, plan_id, plan_name, price):
        """ساخت مستقیم سند zarinpal_pending (معادل خروجی endpoint)."""
        authority = f"TEST-W2-{oid}"
        await self.db.sub_payments.insert_one({
            "_id": oid, "user_id": uid, "plan_id": plan_id,
            "plan_name": plan_name, "price": price, "final_price": price,
            "method": "zarinpal", "status": "zarinpal_pending",
            "zarinpal_authority": authority, "idem_key": f"w2-{oid}",
            "submitted_at": "2026-09-10T00:00:00+00:00",
        })
        return authority

    def test_plan_purchase_then_replay_is_idempotent(self):
        async def go():
            db = self.db
            auth = await self._seed_pending(
                P_W2_BUY, W2_BUYER, self.plan_id, "w2-plan", 100000)
            first = await db.sub_payment_verify_zarinpal(auth, "W2R1", 100000)
            self.assertTrue(first.get("ok"), first)
            self.assertFalse(first.get("already"))
            sub = await db.sub_get(W2_BUYER)
            self.assertIsNotNone(sub)
            end_first = sub.get("end_date")
            # تکرار همان authority → already، بدون تمدید دوباره
            second = await db.sub_payment_verify_zarinpal(auth, "W2R1", 100000)
            self.assertTrue(second.get("ok"))
            self.assertTrue(second.get("already"))
            sub2 = await db.sub_get(W2_BUYER)
            self.assertEqual(sub2.get("end_date"), end_first)
        self._run(go())

    def test_topup_credits_wallet_once(self):
        async def go():
            db = self.db
            auth = await self._seed_pending(
                P_W2_TOPUP, W2_TOPUP, "wallet_topup", "شارژ کیف پول", 50000)
            first = await db.sub_payment_verify_zarinpal(auth, "W2R2", 50000)
            self.assertTrue(first.get("ok"), first)
            w = await db.wallet_get_for_user_id(W2_TOPUP)
            self.assertIsNotNone(w)
            self.assertEqual(int(w.get("balance", 0)), 50000)
            second = await db.sub_payment_verify_zarinpal(auth, "W2R2", 50000)
            self.assertTrue(second.get("already"))
            w2 = await db.wallet_get_for_user_id(W2_TOPUP)
            self.assertEqual(int(w2.get("balance", 0)), 50000)
        self._run(go())

    def test_unknown_authority_not_pending(self):
        async def go():
            res = await self.db.sub_payment_verify_zarinpal(
                "TEST-W2-UNKNOWN", "W2RX", 1000)
            self.assertFalse(res.get("ok"))
            self.assertEqual(res.get("reason"), "not_pending")
        self._run(go())


if __name__ == "__main__":
    unittest.main()
