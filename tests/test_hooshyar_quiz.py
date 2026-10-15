# -*- coding: utf-8 -*-
"""📚 QUIZ-PDF (فاز A) — آزمون‌ساز هوشمند از روی PDF.

سه لایه‌ی تست:
  ۱) static — سیم‌کشی bot.py/ai_solver/requirements بدون اجرا
  ۲) pure — نرمال‌سازی فارسی، کیفیت صفحه، مباحث (هیوریستیک/تعمیر)،
     اعتبارسنجی سختِ سؤال (سقف‌های تلگرام)، shuffle/هش، بازخورد
  ۳) runtime (Mongo) — چرخه‌ی کامل DB: سند→نشست→سؤال→پاسخ اتمیک
     idempotency، شمارنده‌ها، گزارش، حذف آبشاری، retention،
     هوک آپلود (سقف حجم/تعداد سند)، ساختار مباحث با AI ماک‌شده.

الگوی runtime مثل test_w8: loop مشترک _rtloop.
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import _rtloop

_HAS_MONGO_URI = bool(os.environ.get("MONGODB_URI"))
_ADMIN_UID = 880901
_STUDENT = 880902


def _read(*parts):
    root = os.path.join(os.path.dirname(__file__), "..")
    with open(os.path.join(root, *parts), encoding="utf-8") as f:
        return f.read()


# ══════════════════════════════════════════════════════════════
#  ۱) static wiring
# ══════════════════════════════════════════════════════════════
@unittest.skipUnless(_HAS_MONGO_URI, "import bot به MONGODB_URI نیاز دارد")
class QuizStaticWiring(unittest.TestCase):

    def test_bot_wiring(self):
        b = _read("bot.py")
        # هوک آپلود *قبل از* چک ai_query باید بیاید
        i_quiz = b.index("quiz_upload_hook(update, context)")
        i_ai = b.index("context.user_data.get('mode') == 'ai_query'")
        self.assertLess(i_quiz, i_ai,
                        "هوک آپلود آزمون‌ساز باید قبل از ai_query چک شود")
        self.assertIn("(quiz_callback,               r'^quiz:')", b)
        self.assertIn("PollAnswerHandler(quiz_poll_answer_handler)", b)
        self.assertIn("from telegram.ext import", b)
        self.assertIn("PollAnswerHandler", _read("bot.py").split("def ")[0][:6000])
        # jobs
        self.assertIn("quiz_housekeeping_job", b)
        self.assertIn("quiz_retention_job", b)
        self.assertIn("_quiz_set_application(application)", b)
        # set_application بیرون از گارد job_queue (قبل از آن)
        self.assertLess(b.index("_quiz_set_application(application)"),
                        b.index("if application.job_queue is not None:"))

    def test_ai_intro_button(self):
        a = _read("ai_solver.py")
        self.assertIn('callback_data=\'quiz:main\'', a)
        self.assertIn("آزمون‌ساز از PDF", a)

    def test_requirements(self):
        self.assertRegex(_read("requirements.txt"), r"(?m)^pypdf")

    def test_db_wiring(self):
        self.assertIn("DBAiQuiz", _read("db", "__init__.py"))
        self.assertIn("DBAiQuiz", _read("database.py"))
        core = _read("db", "core.py")
        for coll in ("ai_documents", "ai_quiz_sessions",
                     "ai_quiz_questions", "ai_generation_logs"):
            self.assertIn(coll, core)
        # ایندکس یکتای sparse برای نگاشت poll → سؤال
        self.assertRegex(
            core,
            r"\[?\('telegram_poll_id', 1\)\]?, unique=True, sparse=True")

    def test_send_poll_non_anonymous(self):
        """is_anonymous=False — بدون آن poll_answer هرگز نمی‌آید."""
        h = _read("hooshyar_quiz.py")
        self.assertIn("is_anonymous=False", h)

    def test_no_pdf_text_in_logs(self):
        """متن PDF/سؤال نباید در لاگ بیاید — فقط نوع خطا/نام کلاس."""
        h = _read("hooshyar_quiz.py")
        for banned in ("logger.info(prompt", "logger.warning(prompt",
                       "logger.error(source", "print(prompt"):
            self.assertNotIn(banned, h)


# ══════════════════════════════════════════════════════════════
#  ۲) pure — توابع بدون DB
# ══════════════════════════════════════════════════════════════
@unittest.skipUnless(_HAS_MONGO_URI, "import hooshyar_quiz به MONGODB_URI نیاز دارد")
class QuizPersianText(unittest.TestCase):

    def test_normalize(self):
        import hooshyar_quiz as hq
        # presentation forms (متن PDF های قدیمی فارسی)
        t = hq._normalize_persian("ﺳﻼم ﺩﻧﯿﺎ يك ﻛﺘﺎﺏ\u0640 ﻣﻦ")
        self.assertNotIn("ي", t.replace("ی", ""))   # ي عربی حذف/تبدیل
        self.assertNotIn("ك", t)
        self.assertNotIn("\u0640", t)                 # tatweel
        self.assertIn("سلام دنیا", t)
        # ZWNJ حفظ می‌شود
        self.assertIn("\u200d", hq._normalize_persian("می\u200dشود"))

    def test_page_quality(self):
        import hooshyar_quiz as hq
        good = "این یک متن فارسی نمونه است که کیفیت استخراج خوبی دارد و کلمات سالم هستند"
        bad = "���� �� 1234 $%& *"
        empty = ""
        self.assertGreater(hq._page_quality(good), 0.6)
        self.assertLess(hq._page_quality(bad), 0.35)
        self.assertEqual(hq._page_quality(empty), 0.0)


@unittest.skipUnless(_HAS_MONGO_URI, "import hooshyar_quiz به MONGODB_URI نیاز دارد")
class QuizTopicHelpers(unittest.TestCase):

    def _pages(self, n=10):
        return [{"no": i, "text": "متن " * 5, "chars": 25} for i in range(1, n + 1)]

    def test_heuristic(self):
        import hooshyar_quiz as hq
        ts = hq._heuristic_topics(self._pages(22))
        self.assertTrue(ts)
        self.assertEqual(ts[0]["page_start"], 1)
        self.assertEqual(ts[-1]["page_end"], 22)
        # پوشش کامل و بدون همپوشانی
        for a, b in zip(ts, ts[1:]):
            self.assertEqual(b["page_start"], a["page_end"] + 1)

    def test_sanitize_repairs(self):
        import hooshyar_quiz as hq
        raw = [
            {"title": "فیزیک", "page_start": 1, "page_end": 5},
            {"title": "شیمی", "page_start": 4, "page_end": 8},      # همپوشانی
            {"title": "بیوشیمی", "page_start": 7, "page_end": 9},   # شکاف بعد از تعمیر
            {"title": "خراب", "page_start": 99, "page_end": 1},     # نامعتبر
            {"title": "", "page_start": 2, "page_end": 3},          # بدون عنوان
        ]
        ts = hq._sanitize_topics(raw, self._pages(10))
        titles = [t["title"] for t in ts]
        self.assertEqual(titles, ["فیزیک", "شیمی", "بیوشیمی"])
        # پیوستگی کامل
        self.assertEqual(ts[0]["page_start"], 1)
        self.assertEqual(ts[-1]["page_end"], 10)
        for a, b in zip(ts, ts[1:]):
            self.assertEqual(b["page_start"], a["page_end"] + 1)

    def test_range_topics(self):
        import hooshyar_quiz as hq
        doc = {"topics": [{"id": 0, "title": "الف", "page_start": 1, "page_end": 4},
                          {"id": 1, "title": "ب", "page_start": 5, "page_end": 8}]}
        self.assertEqual(len(hq._range_topics(doc, "all")), 2)
        self.assertEqual(len(hq._range_topics(doc, "t1")), 1)
        self.assertEqual(hq._range_topics(doc, "t1")[0]["title"], "ب")
        self.assertEqual(len(hq._range_topics(doc, "t99")), 2)  # fallback


@unittest.skipUnless(_HAS_MONGO_URI, "import hooshyar_quiz به MONGODB_URI نیاز دارد")
class QuizValidation(unittest.TestCase):
    """اعتبارسنجی سخت سؤال — سقف‌های رسمی تلگرام."""

    def setUp(self):
        import hooshyar_quiz as hq
        self.hq = hq
        self.valid_pages = {3, 4, 5}
        self.good = {
            "stem": "کدام اندام وظیفه‌ی ترشح انسولین را دارد؟",
            "options": ["کبد", "پانکراس", "طحال", "کلیه"],
            "correct_index": 1,
            "explanation_short": "جزایر لانگرهانس پانکراس انسولین می‌سازند.",
            "explanation_long": "سلول‌های بتا در جزایر لانگرهانس پانکراس "
                                "انسولین ترشح می‌کنند (صفحه ۴ جزوه).",
            "page_ref": 4,
            "difficulty": "medium",
            "cognitive_level": "recall",
            "concept_tags": ["انسولین"],
            "source_evidence": "پانکراس… انسولین",
        }

    def _v(self, **over):
        q = dict(self.good)
        q.update(over)
        return self.hq._validate_question(q, self.valid_pages)

    def test_ok(self):
        q = self._v()
        self.assertIsNotNone(q)
        self.assertEqual(q["correct_index"], 1)
        self.assertEqual(q["page_refs"], [4])

    def test_stem_limits(self):
        self.assertIsNone(self._v(stem="کوتاه"))                    # <10
        self.assertIsNone(self._v(stem="چ" * 301))                  # >300

    def test_option_limits(self):
        self.assertIsNone(self._v(options=["یک", "دو", "سه"]))      # ۳ گزینه
        self.assertIsNone(self._v(options=["x" * 101, "b", "c", "d"]))  # >100
        # گزینه تکراری
        self.assertIsNone(self._v(options=["پانکراس", "پانکراس", "طحال", "کبد"]))

    def test_correct_index(self):
        self.assertIsNone(self._v(correct_index=4))
        self.assertIsNone(self._v(correct_index=-1))
        self.assertIsNone(self._v(correct_index=None))

    def test_explanation_limits(self):
        self.assertIsNone(self._v(explanation_short="کم"))          # <5
        # 🩹 trim نرم: >200 روی مرز کلمه کوتاه می‌شود، نه رد کامل
        q = self._v(explanation_short="توضیح " + "طولانی" * 60)
        self.assertIsNotNone(q)
        self.assertLessEqual(len(q["explanation_short"]), 200)
        self.assertEqual(q["explanation_short"].startswith("توضیح"), True)
        self.assertIsNone(self._v(explanation_short="a\nb\nc\nd\n"))  # >2 خط

    def test_page_ref(self):
        self.assertIsNone(self._v(page_ref=99))                     # خارج از بازه
        self.assertIsNone(self._v(page_ref="سه"))

    def test_finalize_shuffle(self):
        """shuffle گزینه‌ها نباید گزینه‌ی درست را گم کند.

        هش روی stem + گزینه‌های *مرتب‌شده* است ⇒ نسبت به جابجایی
        گزینه‌ها ناوردا؛ سؤالِ تکراری با ترتیبِ متفاوت هم تشخیص داده
        می‌شود (ضدتکرار قوی‌تر)."""
        q = self._v()
        t = {"id": 7, "title": "غدد"}
        hashes = set()
        for _ in range(20):
            qd = dict(q)
            qd["options"] = list(q["options"])
            qd = self.hq._finalize_question(qd, t)
            self.assertEqual(qd["options"][qd["correct_index"]], "پانکراس")
            self.assertEqual(qd["topic_id"], 7)
            hashes.add(qd["content_hash"])
        self.assertEqual(len(hashes), 1)   # ناوردا نسبت به جایگشت
        # دو سؤالِ هم‌متن با ترتیب متفاوت → همان هش (ضدتکرار)
        qd2 = dict(q)
        qd2["options"] = list(reversed(q["options"]))
        qd2["correct_index"] = 3 - q["correct_index"]   # «ب» جابجا شد
        qd2 = self.hq._finalize_question(qd2, t)
        self.assertEqual(qd2["content_hash"], hashes.pop())


# ══════════════════════════════════════════════════════════════
#  ۳) runtime — Mongo واقعی
# ══════════════════════════════════════════════════════════════
def _mongo_available() -> bool:
    if not _HAS_MONGO_URI:
        return False
    import socket
    from urllib.parse import urlparse
    u = urlparse(os.environ["MONGODB_URI"])
    try:
        socket.create_connection((u.hostname or "127.0.0.1", u.port or 27017), 1).close()
        return True
    except OSError:
        return False


@unittest.skipUnless(_mongo_available(), "Mongo در دسترس نیست")
class QuizDbLifecycle(unittest.TestCase):

    def setUp(self):
        _rtloop.adopt()
        import database
        self.db = database.db
        self.uid = _STUDENT
        self._cleanup()

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        async def _c():
            await self.db.ai_documents.delete_many({"owner_id": self.uid})
            sids = await self.db.ai_quiz_sessions.distinct(
                "_id", {"user_id": self.uid})
            if sids:
                await self.db.ai_quiz_questions.delete_many(
                    {"session_id": {"$in": sids}})
            await self.db.ai_quiz_sessions.delete_many({"user_id": self.uid})
            await self.db.users.update_one(
                {"user_id": self.uid},
                {"$unset": {"quiz_usage_date": "", "quiz_usage_count": ""}})
        _rtloop.run(_c())

    # ── سند ──
    def test_document_lifecycle(self):
        async def _t():
            d = self.db
            did = await d.quiz_create_document(self.uid, "جزوه آناتومی", 12345)
            doc = await d.quiz_get_document(did, owner_id=self.uid)
            self.assertEqual(doc["status"], "processing")
            # ایزوله‌سازی مالکیت
            self.assertIsNone(await d.quiz_get_document(did, owner_id=self.uid + 1))
            pages = [{"no": 1, "text": "متن", "chars": 4, "topic_id": 0},
                     {"no": 2, "text": "متن", "chars": 4, "topic_id": 0}]
            topics = [{"id": 0, "title": "کلیه", "page_start": 1, "page_end": 2}]
            self.assertTrue(await d.quiz_finish_document(did, pages, topics, 0.8))
            docs = await d.quiz_list_documents(self.uid)
            self.assertEqual(len(docs), 1)
            self.assertNotIn("pages", docs[0])       # projection بدون متن
            self.assertEqual(docs[0]["page_count"], 2)
            # شکست
            did2 = await d.quiz_create_document(self.uid, "خراب", 1)
            await d.quiz_fail_document(did2, "scanned")
            self.assertEqual((await d.quiz_get_document(did2))["error"],
                             "scanned")
            return did
        _rtloop.run(_t())

    def test_delete_cascade(self):
        async def _t():
            d = self.db
            did = await d.quiz_create_document(self.uid, "کارتو", 1)
            pages = [{"no": 1, "text": "م", "chars": 1, "topic_id": 0}]
            await d.quiz_finish_document(did, pages, [], 0.5)
            doc = await d.quiz_get_document(did)
            sid = await d.quiz_create_session(self.uid, doc,
                                              {"mode": "practice", "count": 2})
            await d.quiz_add_questions(sid, self.uid, did, [{
                "stem": "سؤال تستی اول اینجاست؟", "options": ["الف", "ب", "ج", "د"],
                "correct_index": 0, "explanation_short": "چون الف درست است.",
                "explanation_long": "الف", "page_refs": [1],
                "content_hash": "h1"}])
            # مالک غریبه نمی‌تواند حذف کند
            self.assertEqual(await d.quiz_delete_document(did, self.uid + 1), 0)
            self.assertEqual(await d.quiz_delete_document(did, self.uid), 1)
            self.assertIsNone(await d.quiz_get_document(did))
            self.assertEqual(await d.ai_quiz_questions.count_documents(
                {"session_id": sid}), 0)
            self.assertEqual(await d.ai_quiz_sessions.count_documents(
                {"_id": sid}), 0)
        _rtloop.run(_t())

    # ── نشست/سؤال/پاسخ اتمیک ──
    def test_session_answer_flow(self):
        async def _t():
            d = self.db
            did = await d.quiz_create_document(self.uid, "فارما", 1)
            await d.quiz_finish_document(
                did, [{"no": 1, "text": "م", "chars": 1, "topic_id": 0}],
                [{"id": 0, "title": "کلیه", "page_start": 1, "page_end": 1}], 0.9)
            doc = await d.quiz_get_document(did)
            sid = await d.quiz_create_session(self.uid, doc,
                                              {"mode": "practice", "count": 3})
            self.assertEqual((await d.quiz_get_session(sid))["status"], "building")
            # نشست باز
            self.assertIsNotNone(await d.quiz_active_session(self.uid))

            def _q(h):
                return {"stem": f"سؤال شماره {h} کدام است؟",
                        "options": ["الف", "ب", "ج", "د"], "correct_index": 1,
                        "explanation_short": "ب درست است چون منبع می‌گوید.",
                        "explanation_long": "ب درست است.", "page_refs": [1],
                        "content_hash": f"hash{h}"}
            n = await d.quiz_add_questions(sid, self.uid, did,
                                           [_q(i) for i in range(3)])
            self.assertEqual(n, 3)
            # ترتیب پیوسته
            qs = await d.quiz_session_questions(sid)
            self.assertEqual([q["order_index"] for q in qs], [0, 1, 2])

            # سؤال بعدی اتمیک — دو برداشت متوالی، دو سؤال متفاوت
            q1 = await d.quiz_next_question(sid)
            q2 = await d.quiz_next_question(sid)
            self.assertEqual(q1["order_index"], 0)
            self.assertEqual(q2["order_index"], 1)
            # سند بازگشتی = قبل از آپدیت؛ وضعیت نهایی از DB:
            f1 = await d.ai_quiz_questions.find_one({"_id": q1["_id"]})
            self.assertEqual(f1["status"], "sent")

            # bind + پاسخ درست
            self.assertTrue(await d.quiz_bind_poll(q1["_id"], "poll:aaa", 10, 111))
            kind, qq = await d.quiz_record_answer(q1["_id"], 1)
            self.assertEqual(kind, "first")
            fresh = await d.ai_quiz_questions.find_one({"_id": q1["_id"]})
            self.assertTrue(fresh["is_correct"])
            self.assertEqual(fresh["status"], "answered")

            # 🔁 idempotency: آپدیت تکراری poll_answer
            kind2, _ = await d.quiz_record_answer(q1["_id"], 2)
            self.assertEqual(kind2, "dup")
            fresh2 = await d.ai_quiz_questions.find_one({"_id": q1["_id"]})
            self.assertTrue(fresh2["is_correct"])    # جواب عوض نشد
            self.assertEqual(fresh2["answered_option"], 1)

            # پاسخ غلط
            await d.quiz_bind_poll(q2["_id"], "poll:bbb", 10, 112)
            kind3, _ = await d.quiz_record_answer(q2["_id"], 0)
            self.assertEqual(kind3, "first")
            fresh3 = await d.ai_quiz_questions.find_one({"_id": q2["_id"]})
            self.assertFalse(fresh3["is_correct"])
            self.assertEqual(fresh3["answered_option"], 0)

            # stale: سؤال skipped شده
            q3 = await d.quiz_next_question(sid)
            await d.ai_quiz_questions.update_one(
                {"_id": q3["_id"]}, {"$set": {"status": "skipped"}})
            kind4, _ = await d.quiz_record_answer(q3["_id"], 1)
            self.assertEqual(kind4, "stale")

            # شمارنده‌های نشست
            await d.quiz_update_session(sid, inc={"answered": 3, "correct": 1,
                                                  "wrong": 1})
            s = await d.quiz_get_session(sid)
            self.assertEqual((s["answered"], s["correct"], s["wrong"]), (3, 1, 1))

            # پرسش با poll_id
            self.assertEqual((await d.quiz_question_by_poll("poll:aaa"))["_id"],
                             q1["_id"])

            # پایان + گزارش
            await d.quiz_update_session(sid, {"status": "active",
                                              "started_at": s["created_at"]})
            await d.quiz_finish_session(sid)
            self.assertIsNone(await d.quiz_active_session(self.uid))
        _rtloop.run(_t())

    def test_usage_counter(self):
        async def _t():
            d = self.db
            await d.users.update_one({"user_id": self.uid},
                                     {"$set": {"user_id": self.uid}}, upsert=True)
            self.assertEqual(await d.quiz_usage_today(self.uid), 0)
            await d.quiz_inc_usage(self.uid, 7)
            await d.quiz_inc_usage(self.uid, 5)
            self.assertEqual(await d.quiz_usage_today(self.uid), 12)
        _rtloop.run(_t())

    def test_retention(self):
        async def _t():
            d = self.db
            from datetime import timedelta
            from time_utils import now_utc
            # سند قدیمی → حذف؛ سند تازه → می‌ماند
            old = await d.quiz_create_document(self.uid, "قدیمی", 1)
            new = await d.quiz_create_document(self.uid, "جدید", 1)
            old_iso = (now_utc() - timedelta(days=100)).isoformat()
            await d.ai_documents.update_one({"_id": old}, {"$set": {
                "created_at": old_iso, "status": "ready"}})
            await d.ai_documents.update_one({"_id": new},
                                            {"$set": {"status": "ready"}})
            removed = await d.quiz_cleanup_old_documents(90)
            self.assertEqual(removed, 1)
            self.assertIsNone(await d.quiz_get_document(old))
            self.assertIsNotNone(await d.quiz_get_document(new))
        _rtloop.run(_t())


@unittest.skipUnless(_mongo_available(), "Mongo در دسترس نیست")
class QuizAiFlow(unittest.TestCase):
    """ساختار مباحث + تولید/بازبینی سؤال با AI ماک‌شده (بدون شبکه)."""

    def setUp(self):
        _rtloop.adopt()
        import database
        self.db = database.db
        self.uid = _STUDENT
        _rtloop.run(self._cleanup())

    def tearDown(self):
        _rtloop.run(self._cleanup())

    async def _cleanup(self):
        await self.db.ai_documents.delete_many({"owner_id": self.uid})
        await self.db.ai_generation_logs.delete_many({"user_id": self.uid})

    def test_topic_structure_ai_and_fallback(self):
        import hooshyar_quiz as hq
        import ai_solver
        pages = [{"no": i, "text": f"مبحث {i} " * 30, "chars": 200}
                 for i in range(1, 13)]

        # AI سالم → خروجی تعمیرشده
        async def fake_gen_ok(prompt, schema, purpose, **kw):
            return {"topics": [{"title": "قلب", "page_start": 1, "page_end": 6},
                               {"title": "عروق", "page_start": 5, "page_end": 12}]}
        async def fake_cfg():
            return {"enabled": True, "provider": "gemini", "model": "test"}
        with mock.patch.object(ai_solver, "generate_structured_json",
                               fake_gen_ok), \
             mock.patch.object(ai_solver, "get_ai_config", fake_cfg):
            ts = _rtloop.run(hq.build_topic_structure(pages, self.uid))
        self.assertEqual([t["title"] for t in ts], ["قلب", "عروق"])
        # همپوشانی (قلب تا ۶، عروق از ۵) → عروق از ۷ شروع می‌شود
        self.assertEqual((ts[0]["page_start"], ts[0]["page_end"]), (1, 6))
        self.assertEqual((ts[1]["page_start"], ts[1]["page_end"]), (7, 12))

        # خطای AI → fallback هیوریستیک
        async def fake_gen_err(prompt, schema, purpose, **kw):
            raise RuntimeError("api down")
        with mock.patch.object(ai_solver, "generate_structured_json",
                               fake_gen_err), \
             mock.patch.object(ai_solver, "get_ai_config", fake_cfg):
            ts2 = _rtloop.run(hq.build_topic_structure(pages, self.uid))
        self.assertTrue(ts2)
        self.assertEqual(ts2[0]["page_start"], 1)
        self.assertEqual(ts2[-1]["page_end"], 12)
        # لاگ خطا ثبت شده (بدون محتوا)
        n = _rtloop.run(self.db.ai_generation_logs.count_documents(
            {"user_id": self.uid, "purpose": "topics", "ok": False}))
        self.assertGreaterEqual(n, 1)

    def test_generate_and_verify(self):
        import hooshyar_quiz as hq
        import ai_solver
        topic = {"id": 0, "title": "کلیه", "page_start": 1, "page_end": 3}
        doc = {"_id": None, "pages": [
            {"no": 1, "text": "نفرون واحد کلیه است و فیلتراسیون در گلومرول "
                              "انجام می‌شود.", "chars": 70, "topic_id": 0},
            {"no": 2, "text": "هورمون ADH از هیپوفیز پسین ترشح و آب را "
                              "بازجذب می‌کند.", "chars": 70, "topic_id": 0},
            {"no": 3, "text": "رنین از دستگاه جکساگلومرولار ترشح "
                              "می‌شود.", "chars": 70, "topic_id": 0}]}
        gen_calls = {"n": 0}

        async def fake_gen(prompt, schema, purpose, **kw):
            gen_calls["n"] += 1
            if purpose == "تولید سؤال":
                return {"questions": [
                    # سؤال سالم
                    {"stem": "واحد ساختاری و عملکردی کلیه چیست؟",
                     "options": ["نفرون", "نورون", "هپاتوسیت", "گلبول"],
                     "correct_index": 0,
                     "explanation_short": "نفرون واحد کلیه است.",
                     "explanation_long": "نفرون واحد ساختاری کلیه است.",
                     "page_ref": 1},
                    # صفحه‌ی نامعتبر → validation رد می‌کند (قبل از verify)
                    {"stem": "سؤالی با صفحه‌ی خارج از بازه است؟",
                     "options": ["الف", "ب", "ج", "د"], "correct_index": 0,
                     "explanation_short": "توضیح کوتاه معتبر.",
                     "explanation_long": "طولانی", "page_ref": 9},
                ]}
            if purpose == "بازبینی سؤال":
                return {"results": [{"index": 0, "verdict": "ok"}]}
            return {}

        async def fake_cfg():
            return {"enabled": True, "provider": "gemini", "model": "test"}

        with mock.patch.object(ai_solver, "generate_structured_json", fake_gen), \
             mock.patch.object(ai_solver, "get_ai_config", fake_cfg):
            qs = _rtloop.run(hq.generate_questions_for_topic(
                doc, topic, want=2, user_id=self.uid))
        self.assertEqual(len(qs), 1)          # سؤال نامعتبر حذف شد
        self.assertEqual(qs[0]["topic_title"], "کلیه")
        self.assertIn(qs[0]["options"][qs[0]["correct_index"]], "نفرون")
        self.assertTrue(qs[0]["content_hash"])
        # تله‌متری تولید ثبت شد
        n = _rtloop.run(self.db.ai_generation_logs.count_documents(
            {"user_id": self.uid, "purpose": "questions", "ok": True}))
        self.assertGreaterEqual(n, 1)

    def test_verify_drops_wrong_and_applies_fix(self):
        import hooshyar_quiz as hq
        import ai_solver
        cands = [
            {"stem": "سؤال یک؟", "options": ["الف", "ب", "ج", "د"],
             "correct_index": 0, "explanation_short": "توضیح اول",
             "explanation_long": "طولانی", "page_refs": [2],
             "topic_title": "تست"},
            {"stem": "سؤال دو؟", "options": ["الف", "ب", "ج", "د"],
             "correct_index": 3, "explanation_short": "توضیح دوم",
             "explanation_long": "طولانی", "page_refs": [2],
             "topic_title": "تست"},
        ]

        async def fake_gen(prompt, schema, purpose, **kw):
            return {"results": [
                {"index": 0, "verdict": "ok"},
                {"index": 1, "verdict": "fixable", "fixed_correct_index": 1},
            ]}

        async def fake_cfg():
            return {"enabled": True, "provider": "gemini", "model": "t"}
        with mock.patch.object(ai_solver, "generate_structured_json", fake_gen), \
             mock.patch.object(ai_solver, "get_ai_config", fake_cfg):
            out = _rtloop.run(hq.verify_questions(cands, "منبع", self.uid))
        self.assertEqual(len(out), 2)
        self.assertEqual(out[1]["correct_index"], 1)   # fix اعمال شد

        # wrong → حذف
        async def fake_gen2(prompt, schema, purpose, **kw):
            return {"results": [{"index": 0, "verdict": "wrong"},
                                {"index": 1, "verdict": "ok"}]}
        with mock.patch.object(ai_solver, "generate_structured_json", fake_gen2), \
             mock.patch.object(ai_solver, "get_ai_config", fake_cfg):
            out2 = _rtloop.run(hq.verify_questions(cands, "منبع", self.uid))
        self.assertEqual(len(out2), 1)

        # verify در دسترس نیست → هیچ سؤالی ارسال نمی‌شود (سخت‌گیری)
        async def fake_gen3(prompt, schema, purpose, **kw):
            raise RuntimeError("down")
        with mock.patch.object(ai_solver, "generate_structured_json", fake_gen3), \
             mock.patch.object(ai_solver, "get_ai_config", fake_cfg):
            out3 = _rtloop.run(hq.verify_questions(cands, "منبع", self.uid))
        self.assertEqual(out3, [])


@unittest.skipUnless(_mongo_available(), "Mongo در دسترس نیست")
class QuizUploadHookGuards(unittest.TestCase):
    """گاردهای هوک آپلود بدون تماس واقعی با تلگرام."""

    def setUp(self):
        _rtloop.adopt()
        import database
        self.db = database.db
        self.uid = _STUDENT
        _rtloop.run(self._cleanup())

    def tearDown(self):
        _rtloop.run(self._cleanup())

    async def _cleanup(self):
        await self.db.ai_documents.delete_many({"owner_id": self.uid})
        await self.db.users.update_one(
            {"user_id": self.uid}, {"$set": {"user_id": self.uid}}, upsert=True)

    @staticmethod
    def _mk_update(file_size=1000, mime="application/pdf", uid=_STUDENT):
        """update ماک — فقط فیلدهایی که هوک استفاده می‌کند."""
        doc = mock.MagicMock()
        doc.mime_type = mime
        doc.file_size = file_size
        doc.file_unique_id = "uniq1"
        doc.file_name = "jozveh.pdf"
        msg = mock.MagicMock()
        msg.document = doc
        msg.chat.type = "private"
        msg.from_user.id = uid
        msg.reply_text = mock.AsyncMock()
        u = mock.MagicMock()
        u.message = msg
        u.effective_user.id = uid
        return u

    def _ctx(self, awaiting=True):
        ctx = mock.MagicMock()
        ctx.user_data = {"quiz_awaiting_pdf": True} if awaiting else {}
        return ctx

    def test_not_awaiting_passes_through(self):
        import hooshyar_quiz as hq
        ctx = self._ctx(awaiting=False)
        ok = _rtloop.run(hq.quiz_upload_hook(self._mk_update(), ctx))
        self.assertFalse(ok)

    def test_rejects_non_pdf(self):
        import hooshyar_quiz as hq
        u = self._mk_update(mime="image/jpeg")
        ok = _rtloop.run(hq.quiz_upload_hook(u, self._ctx()))
        self.assertTrue(ok)
        u.message.reply_text.assert_awaited_once()
        self.assertIn("PDF", u.message.reply_text.await_args.args[0])

    def test_rejects_oversize(self):
        import hooshyar_quiz as hq
        u = self._mk_update(file_size=25 * 1024 * 1024)
        import subscription, ai_solver
        async def ff(uid, f):
            return True
        async def cfg():
            return {"enabled": True}
        with mock.patch.object(subscription, "feature_allowed", ff), \
             mock.patch.object(ai_solver, "get_ai_config", cfg):
            ok = _rtloop.run(hq.quiz_upload_hook(u, self._ctx()))
        self.assertTrue(ok)
        u.message.reply_text.assert_awaited_once()
        self.assertIn("سقف", u.message.reply_text.await_args.args[0])

    def test_rejects_doc_limit(self):
        import hooshyar_quiz as hq
        import subscription, ai_solver
        async def ff(uid, f):
            return True
        async def cfg():
            return {"enabled": True}

        async def seed():
            for i in range(10):
                did = await self.db.quiz_create_document(self.uid, f"j{i}", 1)
                await self.db.quiz_finish_document(
                    did, [{"no": 1, "text": "م", "chars": 1, "topic_id": 0}],
                    [], 0.5)
        _rtloop.run(seed())
        u = self._mk_update()
        with mock.patch.object(subscription, "feature_allowed", ff), \
             mock.patch.object(ai_solver, "get_ai_config", cfg):
            ok = _rtloop.run(hq.quiz_upload_hook(u, self._ctx()))
        self.assertTrue(ok)
        u.message.reply_text.assert_awaited_once()
        self.assertIn("حداکثر", u.message.reply_text.await_args.args[0])


@unittest.skipUnless(_mongo_available(), "Mongo در دسترس نیست")
class QuizReportAndFeedback(unittest.TestCase):

    def setUp(self):
        _rtloop.adopt()
        import database
        self.db = database.db
        self.uid = _STUDENT
        _rtloop.run(self._cleanup())

    def tearDown(self):
        _rtloop.run(self._cleanup())

    async def _cleanup(self):
        await self.db.ai_documents.delete_many({"owner_id": self.uid})
        sids = await self.db.ai_quiz_sessions.distinct("_id",
                                                       {"user_id": self.uid})
        if sids:
            await self.db.ai_quiz_questions.delete_many(
                {"session_id": {"$in": sids}})
        await self.db.ai_quiz_sessions.delete_many({"user_id": self.uid})

    def test_final_report(self):
        async def _t():
            import hooshyar_quiz as hq
            d = self.db
            did = await d.quiz_create_document(self.uid, "فیزیولوژی قلب", 1)
            await d.quiz_finish_document(
                did, [{"no": 1, "text": "م", "chars": 1, "topic_id": 0}],
                [{"id": 0, "title": "سیستم قلبی", "page_start": 1,
                  "page_end": 1}], 0.9)
            doc = await d.quiz_get_document(did)
            sid = await d.quiz_create_session(self.uid, doc,
                                              {"mode": "practice", "count": 3})
            await d.quiz_update_session(sid, {"status": "active",
                                              "started_at": None})
            qs = [
                {"stem": "سؤال ۱", "options": ["الف", "ب", "ج", "د"],
                 "correct_index": 0, "explanation_short": "توضیح",
                 "explanation_long": "توضیح", "page_refs": [1],
                 "content_hash": f"r{i}", "topic_title": "سیستم قلبی"}
                for i in range(3)
            ]
            await d.quiz_add_questions(sid, self.uid, did, qs)
            # دو درست، یک غلط (correct_index=0 برای هر سه)
            for i, opt in enumerate([0, 0, 1]):
                q = await d.quiz_next_question(sid)
                await d.quiz_record_answer(q["_id"], opt)
            session = await d.quiz_get_session(sid)
            await d.quiz_finish_session(sid)
            report = await hq.build_final_report(session)
            # اعداد فارسی + تفکیک مبحث + نوار پیشرفت
            self.assertIn("۲", report)
            self.assertIn("۳", report)
            self.assertIn("سیستم قلبی", report)
            self.assertIn("■", report)
            self.assertIn("گزارش پایان آزمون", report)
        _rtloop.run(_t())

    def test_feedback_message(self):
        import hooshyar_quiz as hq
        sent = []

        class FakeBot:
            async def send_message(self, chat_id, text, parse_mode=None):
                sent.append((chat_id, text, parse_mode))

        q = {"options": ["الف", "ب", "ج", "د"], "correct_index": 1,
             "page_refs": [12], "topic_title": "غدد",
             "explanation_long": "انسولین از سلول‌های بتا ترشح می‌شود.",
             "chat_id": 42}
        session = {"mode": "practice", "correct": 3, "answered": 5}
        _rtloop.run(hq._send_feedback(FakeBot(), session, q, 1, True))
        self.assertEqual(len(sent), 1)
        chat_id, text, parse_mode = sent[0]
        self.assertEqual(chat_id, 42)
        self.assertEqual(parse_mode, "HTML")
        self.assertIn("درست", text)
        self.assertIn("صفحه ۱۲", text)          # ارقام فارسی
        self.assertIn("غدد", text)
        self.assertIn("۳/۵", text)
        # پاسخ غلط → نمایش گزینه‌ی درست
        _rtloop.run(hq._send_feedback(FakeBot(), session, q, 0, False))
        self.assertIn("نادرست", sent[1][1])
        self.assertIn("<b>ب</b>", sent[1][1])


@unittest.skipUnless(_HAS_MONGO_URI, "import hooshyar_quiz به MONGODB_URI نیاز دارد")
class QuizCountGuarantee(unittest.TestCase):
    """🩹 «۳۰ خواستم، ۱۶ ساخت» — توزیع سهم و ضدتکرارِ کلِ نشست."""

    def test_largest_remainder_nothing_lost(self):
        import hooshyar_quiz as hq
        # سهم هیچ چانکی گم نمی‌شود و جمع دقیقاً deficit است
        vols = [(0, 3000), (1, 2000), (2, 1000), (3, 500)]
        for deficit in (1, 5, 7, 30):
            shares = hq._largest_remainder_shares(deficit, vols)
            self.assertEqual(sum(shares.values()), deficit,
                             f'deficit={deficit}: {shares}')
            self.assertTrue(all(n >= 1 for n in shares.values()))
        # چانک بزرگ‌تر سهم بزرگ‌تر یا مساوی دارد
        s = hq._largest_remainder_shares(10, vols)
        self.assertGreaterEqual(s[0], s[2])
        # لبه‌ها
        self.assertEqual(hq._largest_remainder_shares(0, vols), {})
        self.assertEqual(hq._largest_remainder_shares(5, []), {})

    def test_cross_call_dedup(self):
        """seen_hashes مشترک ⇒ فراخوان دوم همان سؤال را نمی‌پذیرد."""
        import hooshyar_quiz as hq
        import ai_solver
        topic = {"id": 0, "title": "کلیه", "page_start": 1, "page_end": 1}
        doc = {"_id": None, "pages": [
            {"no": 1, "text": "نفرون واحد کلیه است و فیلتراسیون در "
                              "گلومرول انجام می‌شود.", "chars": 70,
             "topic_id": 0}]}
        the_q = {"stem": "واحد ساختاری و عملکردی کلیه چیست؟",
                 "options": ["نفرون", "نورون", "هپاتوسیت", "گلبول"],
                 "correct_index": 0,
                 "explanation_short": "نفرون واحد کلیه است.",
                 "explanation_long": "نفرون واحد ساختاری کلیه است.",
                 "page_ref": 1}

        async def fake_gen(prompt, schema, purpose, **kw):
            if purpose == "تولید سؤال":
                return {"questions": [dict(the_q)]}
            return {"results": [{"index": 0, "verdict": "ok"}]}

        async def fake_cfg():
            return {"enabled": True, "provider": "gemini", "model": "t"}

        shared = set()
        with mock.patch.object(ai_solver, "generate_structured_json",
                               fake_gen), \
             mock.patch.object(ai_solver, "get_ai_config", fake_cfg):
            qs1 = _rtloop.run(hq.generate_questions_for_topic(
                doc, topic, want=1, user_id=_STUDENT, seen_hashes=shared))
            qs2 = _rtloop.run(hq.generate_questions_for_topic(
                doc, topic, want=1, user_id=_STUDENT, seen_hashes=shared))
        self.assertEqual(len(qs1), 1)
        self.assertEqual(qs2, [])          # تکرار ⇒ هیچ

    def test_rounds_fill_shortfall(self):
        """دور اول ۱ سؤال می‌دهد؛ کمبود با دوریِ بعد پر می‌شود (تا want)."""
        import hooshyar_quiz as hq
        import ai_solver
        topic = {"id": 0, "title": "کلیه", "page_start": 1, "page_end": 1}
        doc = {"_id": None, "pages": [
            {"no": 1, "text": "نفرون واحد کلیه است و فیلتراسیون در گلومرول "
                              "انجام می‌شود و ADH بازجذب آب را تنظیم "
                              "می‌کند.", "chars": 90, "topic_id": 0}]}
        counter = {"n": 0}

        def _q(i):
            return {"stem": f"سؤال شماره {i} درباره‌ی نفرون چیست؟ " + "پ" * (i * 3),
                    "options": ["نفرون", "نورون", "هپاتوسیت", "گلبول"],
                    "correct_index": 0,
                    "explanation_short": "نفرون واحد کلیه است.",
                    "explanation_long": "نفرون واحد ساختاری کلیه است.",
                    "page_ref": 1}

        async def fake_gen(prompt, schema, purpose, **kw):
            if purpose == "تولید سؤال":
                # هر فراخوان فقط ۱ سؤالِ جدید می‌دهد (کم‌بازده)
                counter["n"] += 1
                return {"questions": [_q(counter["n"])]}
            return {"results": [{"index": 0, "verdict": "ok"}]}

        async def fake_cfg():
            return {"enabled": True, "provider": "gemini", "model": "t"}

        with mock.patch.object(ai_solver, "generate_structured_json",
                               fake_gen), \
             mock.patch.object(ai_solver, "get_ai_config", fake_cfg):
            qs = _rtloop.run(hq.generate_questions_for_topic(
                doc, topic, want=3, user_id=_STUDENT))
        self.assertEqual(len(qs), 3)      # کمبود با دورهای بعد پر شد
        # بدون تکرار
        self.assertEqual(len({q["content_hash"] for q in qs}), 3)


@unittest.skipUnless(_mongo_available(), "Mongo در دسترس نیست")
@unittest.skipUnless(_HAS_MONGO_URI, "env")
class QuizPdfEndToEnd(unittest.TestCase):
    """پردازش PDF واقعی (fpdf2) از صفر تا سندِ ready — با AI ماک‌شده.

    پوشش: استخراج pypdf + نرمال‌سازی + تعمیر visual-RTL + متریک کیفیت +
    ردِ PDF اسکن‌شده (بدون متن) + ذخیره‌ی صفحات/مباحث."""

    PDF_TEXTS = [
        "فیزیولوژی کلیه: نفرون واحد ساختاری و عملکردی کلیه است. فیلتراسیون "
        "خون در گلومرول انجام می‌شود و هر کلیه حدود یک میلیون نفرون دارد. "
        "هورمون ADH با افزایش نفوذپذیری مجاری جمع‌کننده باعث بازجذب آب "
        "می‌شود. این سازوکار برای تنظیم اسمولالیته خون حیاتی است.",
        "بیوشیمی غذاها: کربوهیدرات‌ها به مونوساکاریدها تجزیه می‌شوند و "
        "انسولین ورود گلوکز به سلول‌ها را تسهیل می‌کند. چربی‌ها به اسیدهای "
        "چرب و گلیسرول شکسته می‌شوند. پروتئین‌ها به آمینواسیدها تجزیه "
        "می‌شوند و در کبد دآمینه می‌شوند.",
        "آناتومی قلب: قلب چهار حفره دارد و دریچه‌های سه‌لختی و دولختی "
        "جریان خون را یک‌طرفه نگه می‌دارند. دهلیزها خون را به بطن‌ها "
        "می‌ریزند و بطن چپ خون را به آئورت پمپ می‌کند. عروق کرونری خودِ "
        "قلب را تغذیه می‌کنند.",
    ]

    def setUp(self):
        _rtloop.adopt()
        import database
        self.db = database.db
        self.uid = _STUDENT
        try:
            from fpdf import FPDF
            self.FPDF = FPDF
        except ImportError:
            raise unittest.SkipTest("fpdf2 نصب نیست")
        _rtloop.run(self._cleanup())

    def tearDown(self):
        _rtloop.run(self._cleanup())

    async def _cleanup(self):
        await self.db.ai_documents.delete_many({"owner_id": self.uid})

    def _make_pdf(self, texts):
        import tempfile, os
        pdf = self.FPDF()
        pdf.add_font("dv", "",
                     "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
        pdf.set_font("dv", size=11)
        for t in texts:
            pdf.add_page()
            pdf.multi_cell(0, 8, t)
        fd, path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        pdf.output(path)
        with open(path, "rb") as f:
            raw = f.read()
        os.unlink(path)
        return raw

    class _StatusMsg:
        def __init__(self):
            self.texts = []

        async def edit_text(self, text, **kw):
            self.texts.append(text)

    def test_process_real_pdf(self):
        import hooshyar_quiz as hq

        async def fake_topics(pages, user_id):
            return [{"id": 0, "title": "فیزیولوژی کلیه",
                     "page_start": 1, "page_end": 1},
                    {"id": 1, "title": "بیوشیمی و آناتومی",
                     "page_start": 2, "page_end": 3}]

        async def _t():
            did = await self.db.quiz_create_document(self.uid, "جزوه آزمون", 9000)
            raw = self._make_pdf(self.PDF_TEXTS)
            with mock.patch.object(hq, "build_topic_structure", fake_topics):
                ok = await hq.process_document(None, did, self.uid, raw,
                                               status_message=self._StatusMsg())
            self.assertTrue(ok)
            doc = await self.db.quiz_get_document(did)
            self.assertEqual(doc["status"], "ready")
            self.assertEqual(doc["page_count"], 3)
            self.assertGreater(doc["quality"], 0.5)
            # صفحات embedded + انتساب مبحث
            self.assertEqual(len(doc["pages"]), 3)
            self.assertEqual(doc["pages"][0]["topic_id"], 0)
            self.assertEqual(doc["pages"][2]["topic_id"], 1)
            # متن قابل‌فهم (نه visual-reversed): واژه‌های منطقی موجودند
            t0 = doc["pages"][0]["text"]
            self.assertIn("نفرون", t0)
            self.assertIn("می‌شود", t0)   # ZWNJ حفظ شده
            # لاگ بدون متن سند
        _rtloop.run(_t())

    def test_rejects_scanned_pdf(self):
        import hooshyar_quiz as hq

        async def _t():
            did = await self.db.quiz_create_document(self.uid, "اسکن", 500)
            raw = self._make_pdf(["", "", ""])   # صفحات خالی → بدون متن
            st = self._StatusMsg()
            ok = await hq.process_document(None, did, self.uid, raw,
                                           status_message=st)
            self.assertFalse(ok)
            doc = await self.db.quiz_get_document(did)
            self.assertEqual(doc["status"], "failed")
            self.assertEqual(doc["error"], "scanned_or_low_quality")
            self.assertTrue(any("اسکن" in t for t in st.texts),
                            st.texts)
        _rtloop.run(_t())

    def test_rejects_non_pdf_magic(self):
        import hooshyar_quiz as hq

        async def _t():
            did = await self.db.quiz_create_document(self.uid, "جعل", 10)
            st = self._StatusMsg()
            ok = await hq.process_document(None, did, self.uid,
                                           b"PK\x03\x04 not a pdf",
                                           status_message=st)
            self.assertFalse(ok)
            doc = await self.db.quiz_get_document(did)
            self.assertEqual(doc["error"], "not_pdf")
        _rtloop.run(_t())


if __name__ == "__main__":
    unittest.main(verbosity=2)
