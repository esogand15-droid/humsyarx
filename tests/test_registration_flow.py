# -*- coding: utf-8 -*-
"""🧪 تست دائمیِ جریان ثبت‌نام — تور ایمنیِ باگِ P0.

پیشینه
──────
باگ تولیدی `TypeError: DBCore.create_user() got an unexpected keyword
argument 'group_verified'` در **هیچ تستی** پوشش نداشت؛ همین باعث شد
چند کاربر واقعی ثبت‌نامشان شکسته شود. این فایل همان جریان را به‌صورت
تست دائمی می‌آورد تا هر رگرسیون مشابه، قبل از دیپلوی دیده شود.

نحوهٔ کار
─────────
بدون MongoDB و بدون Telegram واقعی: `start.db` با یک دیتابیس درون‌حافظه
جایگزین می‌شود و Update/Context/Bot با آبجکت‌های ساده شبیه‌سازی
می‌شوند. پس تست سریع، قطعی و بدون نیاز به Secret است.

پوشش
────
۱) قرارداد `create_user` (group_verified / استنتاج / تأیید بی‌مبنا)
۲) idempotency (کلیک دوباره، ریس هم‌زمان DuplicateKeyError)
۳) جریان کامل ربات برای `Mehr_1404` و `bahman_1404`
۴) اعتبارسنجی ورودی و callback ناقص
۵) فلوی «شماره دانشجویی اجباری» (پایان ثبت‌نام از پیام، بدون callback)
۶) context ازدست‌رفته، پاک‌سازی state، escape نام کاربر
"""
from __future__ import annotations

import asyncio
import os
import sys
import unittest

os.environ.setdefault("MONGODB_URI", "mongodb://127.0.0.1:27017/humsyar_test")
os.environ.setdefault("ADMIN_ID", "999")
os.environ.setdefault("TELEGRAM_TOKEN", "123:TEST")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo.errors import DuplicateKeyError          # noqa: E402
from telegram.ext import ConversationHandler         # noqa: E402

from db import DBCore                                # noqa: E402


# ─────────────────────────── دیتابیس درون‌حافظه ───────────────────────────
class _Res:
    inserted_id = "x"


class FakeColl:
    def __init__(self):
        self.docs = []
        self.fail_next_insert = False
        self.hide_existing = False       # شبیه‌سازی ریس: pre-check چیزی نمی‌بیند

    async def find_one(self, q, proj=None):
        if self.hide_existing:
            return None
        for d in self.docs:
            if all(d.get(k) == v for k, v in (q or {}).items()):
                return dict(d)
        return None

    async def insert_one(self, doc):
        if self.fail_next_insert:
            self.fail_next_insert = False
            raise RuntimeError("mongo down")
        if any(d.get("user_id") == doc.get("user_id") for d in self.docs):
            raise DuplicateKeyError("E11000 duplicate key")
        self.docs.append(dict(doc))
        return _Res()

    async def update_one(self, q, u):
        for d in self.docs:
            if all(d.get(k) == v for k, v in (q or {}).items()):
                d.update((u or {}).get("$set", {}))
                return _Res()
        return _Res()


class FakeDB(DBCore):
    """DBCore بدون اتصال شبکه."""

    def __init__(self):
        self.users = FakeColl()
        self.educational_group_logs = FakeColl()
        self.bot_notifs = FakeColl()
        self._user_cache = {}
        self.intakes = [
            {"code": "Mehr_1404", "label": "مهر ۱۴۰۴", "active": True},
            {"code": "bahman_1404", "label": "بهمن ۱۴۰۴", "active": True},
        ]
        self.settings = {"require_student_id": False}
        self.blacklisted = set()

    async def get_setting(self, key, default=None):
        return self.settings.get(key, default)

    async def get_active_intakes(self):
        return list(self.intakes)

    async def is_blacklisted(self, uid):
        return int(uid) in self.blacklisted


# ─────────────────────────── شبیه‌سازی تلگرام ───────────────────────────
class Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class FakeMessage:
    def __init__(self, text=None):
        self.text = text
        self.sent = []
        self.edits = []

    async def reply_text(self, text, **kw):
        self.sent.append(text)

    async def edit_message_text(self, text, **kw):
        self.edits.append(text)


class FakeQuery:
    def __init__(self, data):
        self.data = data
        self.message = FakeMessage()
        self.answers = []

    async def answer(self, text=None, show_alert=False):
        self.answers.append(text)

    async def edit_message_text(self, text, **kw):
        self.message.edits.append(text)


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, **kw):
        self.sent.append((chat_id, text))

    async def send_document(self, *a, **kw):
        return True


class FakeContext:
    def __init__(self):
        self.user_data = {}
        self.bot = FakeBot()


def make_update(uid, data=None, text=None, username=None, name="علی احمدی"):
    msg = FakeMessage(text=text)
    upd = Obj(effective_user=Obj(id=uid, username=username, first_name=name,
                                 full_name=name),
              effective_message=msg, message=msg, callback_query=None)
    if data is not None:
        q = FakeQuery(data)
        upd.callback_query = q
        upd.effective_message = q.message
    return upd


class RegistrationFlowTests(unittest.IsolatedAsyncioTestCase):
    """جریان ثبت‌نام ربات + قرارداد create_user."""

    @classmethod
    def setUpClass(cls):
        import start
        import utils
        cls.start = start
        cls.utils = utils
        cls._orig_db = start.db
        cls._orig_audit = getattr(utils, "send_audit_log", None)

    @classmethod
    def tearDownClass(cls):
        cls.start.db = cls._orig_db
        if cls._orig_audit is not None:
            cls.utils.send_audit_log = cls._orig_audit

    def setUp(self):
        self.db = FakeDB()
        self.start.db = self.db
        self.utils.send_audit_log = lambda *a, **k: asyncio.sleep(0)

    # ─────────── قرارداد create_user ───────────
    async def test_create_user_accepts_group_verified(self):
        res = await self.db.create_user(
            101, "علی احمدی", "", "1", "ali", intake="Mehr_1404",
            educational_group="male", group_source="user_confirmed",
            group_verified=True)
        doc = self.db.users.docs[-1]
        self.assertTrue(res["created"])
        self.assertIs(doc["group_verified"], True)
        self.assertEqual(doc["educational_group"], "male")

    async def test_group_verified_none_is_inferred_from_source(self):
        res = await self.db.create_user(
            102, "زهرا حسینی", "", "1", None, intake="bahman_1404",
            educational_group="female", group_source="user_confirmed")
        self.assertIs(res["group_verified"], True)

    async def test_unverified_claim_never_becomes_definitive(self):
        await self.db.create_user(
            103, "نامشخص", "", "2", None, intake="Mehr_1404",
            educational_group="unknown", group_source="user_confirmed",
            group_verified=True)
        doc = self.db.users.docs[-1]
        self.assertEqual(doc["educational_group"], "unknown")
        self.assertIs(doc["group_verified"], False)

    async def test_duplicate_registration_is_idempotent(self):
        await self.db.create_user(101, "علی", "", "1", None, intake="Mehr_1404",
                                  educational_group="male", group_verified=True)
        n = len(self.db.users.docs)
        res = await self.db.create_user(101, "علی", "", "1", None,
                                        intake="Mehr_1404",
                                        educational_group="male", group_verified=True)
        self.assertTrue(res["duplicate"])
        self.assertFalse(res["created"])
        self.assertEqual(len(self.db.users.docs), n)

    async def test_concurrent_insert_race_is_absorbed(self):
        await self.db.create_user(111, "ریس", "", "1", None, intake="Mehr_1404",
                                  educational_group="male", group_verified=True)
        self.db.users.hide_existing = True          # pre-check چیزی نمی‌بیند
        res = await self.db.create_user(111, "ریس", "", "1", None,
                                        intake="Mehr_1404",
                                        educational_group="male", group_verified=True)
        self.assertTrue(res["duplicate"])
        self.assertEqual(len(self.db.users.docs), 1)

    async def test_real_db_error_propagates(self):
        self.db.users.fail_next_insert = True
        with self.assertRaises(RuntimeError):
            await self.db.create_user(121, "خطا", "", "1", None)

    async def test_set_educational_group_accepts_reason(self):
        await self.db.create_user(101, "علی", "", "1", None, intake="Mehr_1404",
                                  educational_group="male", group_verified=True)
        await self.db.set_user_educational_group(
            101, "female", source="user_confirmed", verified=True,
            actor_id=101, reason="تست دلیل")
        hist = self.db.users.docs[0]["educational_group_history"]
        self.assertEqual(hist[-1].get("reason"), "تست دلیل")

    async def test_enqueue_bot_outbox(self):
        out = await self.db.enqueue_bot_outbox(0, "__COURSE_SELECTION_REMINDER__:first")
        self.assertTrue(out["ok"])
        self.assertIs(self.db.bot_notifs.docs[0]["sent"], False)

    # ─────────── جریان کامل ربات ───────────
    async def _register(self, uid, intake_code, edu="male", name="علی احمدی"):
        upd = make_update(uid, data=f"register:intake:{intake_code}")
        ctx = FakeContext()
        ctx.user_data.update({"reg_name": name, "reg_group": "1",
                              "reg_edu_group": edu})
        state = await self.start.register_intake_callback(upd, ctx)
        return upd, ctx, state

    async def test_flow_mehr_1404(self):
        upd, ctx, state = await self._register(201, "Mehr_1404")
        user = await self.db.get_user(201, use_cache=False)
        self.assertEqual(state, ConversationHandler.END)
        self.assertEqual(user["intake"], "Mehr_1404")
        self.assertTrue(any("ثبت‌نام با موفقیت" in m
                            for m in upd.callback_query.message.edits))
        self.assertTrue(any("درخواست ثبت‌نام جدید" in t for _, t in ctx.bot.sent))

    async def test_flow_bahman_1404(self):
        upd, ctx, state = await self._register(202, "bahman_1404", edu="female",
                                               name="مریم رضایی")
        user = await self.db.get_user(202, use_cache=False)
        self.assertEqual(user["intake"], "bahman_1404")
        self.assertIs(user["group_verified"], True)

    async def test_double_click_creates_one_user(self):
        await self._register(201, "Mehr_1404")
        upd, ctx, state = await self._register(201, "Mehr_1404")
        self.assertEqual(len([d for d in self.db.users.docs if d["user_id"] == 201]), 1)
        self.assertEqual(state, ConversationHandler.END)

    async def test_invalid_intake_rejected(self):
        upd, ctx, state = await self._register(203, "hacked_code")
        self.assertIsNone(await self.db.get_user(203, use_cache=False))
        self.assertTrue(any("فعال نیست" in m
                            for m in upd.callback_query.message.edits))

    async def test_truncated_callback_data(self):
        upd = make_update(204, data="register:intake")
        ctx = FakeContext()
        ctx.user_data.update({"reg_name": "کاربر", "reg_group": "1"})
        await self.start.register_intake_callback(upd, ctx)
        self.assertIsNone(await self.db.get_user(204, use_cache=False))

    async def test_missing_context_does_not_half_register(self):
        upd = make_update(205, data="register:intake:Mehr_1404")
        ctx = FakeContext()
        await self.start.register_intake_callback(upd, ctx)
        self.assertIsNone(await self.db.get_user(205, use_cache=False))
        self.assertTrue(any("منقضی" in m for m in upd.callback_query.message.edits))

    async def test_require_student_id_flow_finishes(self):
        """پایان ثبت‌نام از مسیر MessageHandler (بدون callback_query)."""
        self.db.settings["require_student_id"] = True
        upd, ctx, state = await self._register(206, "Mehr_1404", edu="female",
                                               name="سارا کریمی")
        self.assertEqual(state, self.start.STEP_STUDENT_ID)
        upd2 = make_update(206, text="40123456")
        state2 = await self.start.step_student_id_handler(upd2, ctx)
        user = await self.db.get_user(206, use_cache=False)
        self.assertEqual(state2, ConversationHandler.END)
        self.assertEqual(user["student_id"], "40123456")
        self.assertTrue(any("ثبت‌نام با موفقیت" in m
                            for m in upd2.effective_message.sent))

    async def test_user_markup_is_escaped(self):
        upd, ctx, _ = await self._register(
            207, "Mehr_1404", name='<a href="http://x">علی</a>')
        admin_msgs = " ".join(t for _, t in ctx.bot.sent)
        user_msgs = " ".join(upd.callback_query.message.edits)
        self.assertNotIn('<a href="http://x">', admin_msgs)
        self.assertIn("&lt;a href=", admin_msgs)
        self.assertNotIn("<a href=", user_msgs)

    async def test_unknown_educational_group_is_not_verified(self):
        upd = make_update(208, data="register:intake:Mehr_1404")
        ctx = FakeContext()
        ctx.user_data.update({"reg_name": "نام خانوادگی", "reg_group": "1"})
        await self.start.register_intake_callback(upd, ctx)
        user = await self.db.get_user(208, use_cache=False)
        self.assertEqual(user["educational_group"], "unknown")
        self.assertIs(user["group_verified"], False)

    async def test_context_is_cleaned_after_registration(self):
        upd, ctx, _ = await self._register(209, "Mehr_1404")
        self.assertNotIn("reg_edu_group", ctx.user_data)
        self.assertNotIn("reg_name", ctx.user_data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
