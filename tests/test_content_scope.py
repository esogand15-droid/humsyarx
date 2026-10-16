# -*- coding: utf-8 -*-
"""🧪 ماموریت ۶ — تست‌های نظام «محدوده محتوا» و رفع باگ کلون ⭐

سه دسته:
  ۱) داینامیک با FakeDB (بدون Mongo): تصمیم‌های CoW، اتمیسیتی/ایدمپوتنسی
     ensure_override، سایه‌اندازی (effective view)، ماتریس دسترسی API
  ۲) قرارداد static: هیچ ساخت داده‌ای با «کلیک/بازکردن» نیست؛ همه‌ی
     مسیرهای نوشتن از CoW می‌گذرند؛ نشان‌ها/برچسب‌ها یکدست‌اند
  ۳) رده‌بندی migration (A/B/C/D) — توابع خالص

اجرا:  python3 -m unittest tests.test_content_scope -v
(بدون Mongo — MONGODB_URI ساختگی فقط برای import گذاشته می‌شود)
"""
import os
import unittest

os.environ.setdefault('MONGODB_URI', 'mongodb://localhost:27017/test_unused')

import asyncio


# ════════════════════════════════════════════════════════════
# 🔧 FakeDB — کمینه برای مسیرهای CoW
# ════════════════════════════════════════════════════════════

class FakeCursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, *a, **k):
        return self

    async def to_list(self, n=None):
        return self._docs[:n] if n else self._docs

    def __aiter__(self):
        self._it = iter(self._docs)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class FakeColl:
    """کالکشن درون‌حافظه‌ای با semantics مورد نیاز (find_one/insert/
    find_one_and_update/count_documents/…)"""

    def __init__(self, docs=None):
        self.docs = list(docs or [])
        self.calls = []          # ثبت عملیات برای اثبات «نوشتن»

    # helpers
    def _by_id(self, _id):
        for d in self.docs:
            if str(d.get('_id')) == str(_id):
                return d
        return None

    async def find_one(self, q, *a, **k):
        return self._match(q)

    def _match(self, q):
        for d in self.docs:
            if self._ok(d, q):
                return d
        return None

    @staticmethod
    def _ok(doc, q):
        for k, v in q.items():
            if k == '_id':
                if str(doc.get('_id')) != str(v):
                    return False
            elif k == '$in':
                raise NotImplementedError
            elif isinstance(v, dict):
                if '$type' in v:
                    if not isinstance(doc.get(k), str):
                        return False
                elif '$ne' in v:
                    if doc.get(k) == v['$ne']:
                        return False
                elif '$gt' in v:
                    if not (doc.get(k, '') > v['$gt']):
                        return False
                else:
                    raise NotImplementedError(str(v))
            elif doc.get(k) != v:
                return False
        return True

    async def insert_one(self, doc):
        import copy
        d = copy.deepcopy(doc)
        if '_id' not in d:                     # مونگو خودش _id می‌سازد
            d['_id'] = f'{(len(self.docs) + 1):024x}'
        self.docs.append(d)
        self.calls.append(('insert', d))
        import types
        return types.SimpleNamespace(inserted_id=d['_id'])

    async def find_one_and_update(self, q, update, upsert=False, return_document=True):
        import copy
        existing = self._match(q)
        if existing is None and upsert:
            doc = {'_id': f'{(len(self.docs) + 1):024x}'}
            for k, v in q.items():
                if k != '_id':
                    doc[k] = v
            soi = update.get('$setOnInsert', {})
            doc.update(copy.deepcopy(soi))
            self.docs.append(doc)
            self.calls.append(('upsert', doc))
            return copy.deepcopy(doc)
        if existing is not None and update:
            soi = update.get('$setOnInsert', {})
            existing.update(copy.deepcopy(soi))
        return copy.deepcopy(existing) if existing else None

    async def count_documents(self, q):
        return sum(1 for d in self.docs if self._ok(d, q))

    def find(self, q, *a, **k):
        return FakeCursor([d for d in self.docs if self._ok(d, q)])

    async def delete_many(self, q):
        n = 0
        for d in list(self.docs):
            if self._ok(d, q):
                self.docs.remove(d)
                n += 1
        return n

    async def delete_one(self, q):
        d = self._match(q)
        if d:
            self.docs.remove(d)
        return 1 if d else 0

    async def update_one(self, q, update, *a, **k):
        d = self._match(q)
        if d and '$set' in update:
            d.update(update['$set'])
        return 1 if d else 0


def make_dal():
    """نمونه‌ی DAL واقعی بدون __init__ (اتصال Mongo لازم نیست) + کالکشن‌های فیک."""
    from database import db as real_db
    dal = object.__new__(type(real_db))
    dal.bs_sessions = FakeColl()
    dal.bs_content = FakeColl()
    dal.bs_lessons = FakeColl()
    dal.bs_content_log = FakeColl()
    dal.ref_books = FakeColl()
    dal.ref_files = FakeColl()
    dal.ref_subjects = FakeColl()
    return dal


# شناسه‌ها باید ObjectId-parsable (۲۴ hex) باشند — DAL با ObjectId(sid) می‌خواند
L1 = '111111111111111111111111'
B1 = '222222222222222222222222'
C1 = '333333333333333333333333'
N1 = '444444444444444444444444'
N2 = '555555555555555555555555'
F9 = '666666666666666666666666'
S1 = '777777777777777777777777'
BK1 = '888888888888888888888888'


def seed_basic_science(dal):
    """درس سراسری L1 + جلسه سراسری B1 با یک فایل C1 (شناسه‌های hex)."""
    dal.bs_lessons.docs.append({'_id': L1, 'name': 'فیزیولوژی', 'intake': '', 'term': 'ترم ۱'})
    dal.bs_sessions.docs.append(
        {'_id': B1, 'lesson_id': L1, 'number': 1, 'topic': 'معارفه',
         'teacher': 'احمدی', 'intake': '', 'created_at': '2026-01-01'})
    dal.bs_content.docs.append(
        {'_id': C1, 'session_id': B1, 'type': 'pdf', 'file_id': 'tgf1',
         'description': 'جزوه', 'order': 0, 'downloads': 5, 'notif_sent': True})


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


# ════════════════════════════════════════════════════════════
# ۱) داینامیک — DAL
# ════════════════════════════════════════════════════════════

class EnsureOverrideTests(unittest.TestCase):
    """T2/T3 — CoW: اتمیک در سطح سند + ایدمپوتنسی + کپی یک‌باره‌ی فایل‌ها"""

    def setUp(self):
        self.dal = make_dal()
        seed_basic_science(self.dal)

    def test_first_call_creates_and_copies_content(self):
        fork_id, created = run(self.dal.bs_ensure_override(B1, 'mehrab'))
        self.assertTrue(created)
        fork = self.dal.bs_sessions._by_id(fork_id)
        self.assertEqual(fork['fork_of'], B1)
        self.assertEqual(fork['intake'], 'mehrab')
        # فایل‌ها کپی شده‌اند با ارجاع file_id و بدون اعلان مجدد
        copies = [d for d in self.dal.bs_content.docs if d['session_id'] == fork_id]
        self.assertEqual(len(copies), 1)
        self.assertEqual(copies[0]['file_id'], 'tgf1')
        self.assertTrue(copies[0]['notif_sent'])
        self.assertEqual(copies[0]['downloads'], 0)
        self.assertEqual(copies[0]['fork_of'], C1)
        # base دست‌نخورده
        self.assertIsNotNone(self.dal.bs_content._by_id(C1))

    def test_idempotent_second_call_returns_same_no_recopy(self):
        f1, c1 = run(self.dal.bs_ensure_override(B1, 'mehrab'))
        n_inserts = len(self.dal.bs_content.calls)
        f2, c2 = run(self.dal.bs_ensure_override(B1, 'mehrab'))
        self.assertEqual(f1, f2)
        self.assertFalse(c2)
        # هیچ فایل جدیدی کپی نشد
        self.assertEqual(len(self.dal.bs_content.calls), n_inserts)

    def test_race_two_calls_single_fork(self):
        """دو فراخوانی هم‌زمان → فقط یک سند fork (find_one_and_update اتمیک)."""
        async def _both():
            return await asyncio.gather(
                self.dal.bs_ensure_override(B1, 'mehrab'),
                self.dal.bs_ensure_override(B1, 'mehrab'))
        (f1, c1), (f2, c2) = run(_both())
        forks = [d for d in self.dal.bs_sessions.docs if d.get('fork_of') == B1]
        self.assertEqual(len(forks), 1)
        self.assertEqual(f1, f2)
        # مجموع کپی فایل = ۱ (فقط یک برنده)
        copies = [d for d in self.dal.bs_content.docs if d.get('fork_of') == C1]
        self.assertEqual(len(copies), 1)

    def test_non_global_base_rejected(self):
        self.dal.bs_sessions.docs.append(
            {'_id': N1, 'lesson_id': L1, 'number': 2, 'topic': 'بومی',
             'intake': 'mehrab'})
        fork_id, created = run(self.dal.bs_ensure_override(N1, 'mehrab'))
        self.assertIsNone(fork_id)
        self.assertFalse(created)

    def test_archived_fork_is_resurrected(self):
        """fork آرشیوشده (A/C قدیمی) کلید یکتا را دارد ⇒ احیا می‌شود،
        نه درجِ ممنوع‌شده توسط ایندکس یکتا."""
        self.dal.bs_sessions.docs.append(
            {'_id': F9, 'lesson_id': L1, 'number': 1, 'topic': 'معارفه',
             'teacher': 'احمدی', 'intake': 'mehrab', 'fork_of': B1,
             'archived': True})
        fork_id, created = run(self.dal.bs_ensure_override(B1, 'mehrab'))
        self.assertEqual(fork_id, F9)            # همان سند احیا شد
        fork = self.dal.bs_sessions._by_id(F9)
        self.assertFalse(fork.get('archived'))
        self.assertIsNotNone(fork.get('resurrected_at'))


class EffectiveViewTests(unittest.TestCase):
    """T4 — سایه‌اندازی: fork جایگزین base برای همان ورودی؛ بقیه base را می‌بینند"""

    def setUp(self):
        self.dal = make_dal()
        seed_basic_science(self.dal)
        run(self.dal.bs_ensure_override(B1, 'mehrab'))

    def test_shadow_for_own_intake(self):
        view = run(self.dal.bs_get_sessions_effective(L1, ['mehrab', '']))
        self.assertEqual([s['topic'] for s in view], ['معارفه'])
        self.assertTrue(view[0].get('fork_of'))       # fork دیده می‌شود

    def test_other_intake_sees_base(self):
        view = run(self.dal.bs_get_sessions_effective(L1, ['bahman', '']))
        self.assertEqual(len(view), 1)
        self.assertFalse(view[0].get('fork_of'))

    def test_archived_fork_does_not_shadow(self):
        for d in self.dal.bs_sessions.docs:
            if d.get('fork_of') == B1:
                d['archived'] = True
        view = run(self.dal.bs_get_sessions_effective(L1, ['mehrab', '']))
        self.assertEqual(len(view), 1)
        self.assertFalse(view[0].get('fork_of'))      # base برگشت

    def test_shared_rule_helper(self):
        """قاعده‌ی مشترک (bs_effective_view) — همان چیزی که پنل هم مصرف می‌کند."""
        sessions = run(self.dal.bs_get_sessions(L1))
        out = type(self.dal).bs_effective_view(sessions, ['', 'mehrab'], {L1: ''})
        self.assertEqual(len(out), 1)
        self.assertTrue(out[0].get('fork_of'))

    def test_override_counts(self):
        run(self.dal.bs_ensure_override(B1, 'mehrab'))
        counts = run(self.dal.bs_override_counts(L1))
        self.assertEqual(counts.get(B1), 1)

    def test_divergence_merge_is_additive(self):
        """R5 — فایل جدیدِ base به fork اضافه می‌شود؛ چیزی حذف/بازنویسی نمی‌شود."""
        fork_id, _ = run(self.dal.bs_ensure_override(B1, 'mehrab'))
        self.dal.bs_content.docs.append(
            {'_id': '9' * 24, 'session_id': B1, 'type': 'voice', 'file_id': 'tgf2',
             'description': 'ویس', 'order': 1})
        self.assertEqual(run(self.dal.bs_base_new_content_count(fork_id)), 1)
        added = run(self.dal.bs_merge_base_new_content(fork_id))
        self.assertEqual(added, 1)
        self.assertEqual(run(self.dal.bs_base_new_content_count(fork_id)), 0)
        fork_files = [d for d in self.dal.bs_content.docs if d['session_id'] == fork_id]
        self.assertEqual(len(fork_files), 2)          # قدیمی + جدید
        self.assertEqual({f['type'] for f in fork_files}, {'pdf', 'voice'})

    def test_unfork_removes_only_fork(self):
        fork_id, _ = run(self.dal.bs_ensure_override(B1, 'mehrab'))
        base_id = run(self.dal.bs_unfork_session(fork_id))
        self.assertEqual(base_id, B1)
        self.assertIsNotNone(self.dal.bs_sessions._by_id(B1))
        self.assertIsNone(self.dal.bs_sessions._by_id(fork_id))
        self.assertEqual([d for d in self.dal.bs_content.docs
                          if d['session_id'] == fork_id], [])
        self.assertIsNotNone(self.dal.bs_content._by_id(C1))


# ════════════════════════════════════════════════════════════
# ۲) داینامیک — تصمیم‌های CoW ربات/API (ماتریس نقش×رکورد×عمل)
# ════════════════════════════════════════════════════════════

class FakeBotDB:
    """فقط متدهایی که تصمیم‌گیرهای CoW ربات صدا می‌زنند."""

    def __init__(self, dal):
        self.dal = dal
        self.override_calls = []

    async def get_all_intakes(self):
        return [{'code': 'mehrab', 'label': 'مهر ۱۴۰۵', 'active': True},
                {'code': 'bahman', 'label': 'بهمن ۱۴۰۴', 'active': True}]

    async def session_intake(self, sid):
        return await self.dal.session_intake(sid)

    async def ref_book_intake(self, bid):
        return await self.dal.ref_book_intake(bid)

    async def can_access_intake(self, uid, intake):
        # ارشد (uid=1) همه‌جا؛ scoped (uid=2) فقط 'mehrab'؛ بقیه هیچ‌جا
        if uid == 1:
            return True
        if uid == 2:
            return intake == 'mehrab'
        return intake == '' and False

    async def get_content_scope(self, uid):
        if uid == 1:
            return {'kind': 'global', 'intake': None}
        if uid == 2:
            return {'kind': 'scoped', 'intake': 'mehrab'}
        if uid == 3:
            return {'kind': 'scoped', 'intake': ''}   # بدون ورودی تنظیم‌شده
        return None

    async def bs_ensure_override(self, sid, intake):
        self.override_calls.append((sid, intake))
        return await self.dal.bs_ensure_override(sid, intake)

    async def ref_ensure_override(self, bid, intake):
        self.override_calls.append(('book:' + bid, intake))
        return await self.dal.ref_ensure_override(bid, intake)


class Ctx:
    def __init__(self, intake='', edit_scope=None):
        self.user_data = {}
        if intake:
            self.user_data['ca_intake'] = intake
        if edit_scope:
            self.user_data['ca_edit_scope'] = edit_scope


class CowDecisionTests(unittest.TestCase):
    """ماتریس §۳ DESIGN — نقش × رکورد × اولین ذخیره"""

    def setUp(self):
        import content_admin as ca
        self.ca = ca
        self.dal = make_dal()
        seed_basic_science(self.dal)
        self.dal.ref_subjects.docs.append({'_id': S1, 'name': 'آناتومی', 'intake': ''})
        self.dal.ref_books.docs.append(
            {'_id': BK1, 'subject_id': S1, 'name': 'کتاب سراسری', 'intake': ''})
        self._orig_db = ca.db
        self.fakedb = FakeBotDB(self.dal)
        ca.db = self.fakedb

    def tearDown(self):
        self.ca.db = self._orig_db

    def _session_target(self, uid, ctx):
        return run(self.ca._cow_session_target(ctx, uid, B1))

    def test_scoped_on_global_creates_override_own_intake(self):
        """ادمین ورودی + جلسه سراسری → CoW خودکار برای scope خودش (نه پارامتر کلاینت)."""
        ctx = Ctx(intake='FOREIGN')          # تلاش برای جعل هدف از user_data؟
        sid, note = self._session_target(2, ctx)
        self.assertIsNotNone(sid)
        self.assertEqual(self.fakedb.override_calls, [(B1, 'mehrab')])  # سرور تصمیم گرفت
        self.assertIn('مهر ۱۴۰۵', note)          # برچسب ورودی در پیام است

    def test_scoped_on_foreign_intake_denied(self):
        self.dal.bs_sessions.docs.append(
            {'_id': N2, 'lesson_id': L1, 'number': 9, 'topic': 'غیره',
             'intake': 'bahman'})
        sid, note = run(self.ca._cow_session_target(Ctx(), 2, N2))
        self.assertIsNone(sid)
        self.assertEqual(note, 'deny')

    def test_scoped_without_intake_denied_on_global(self):
        sid, note = self._session_target(3, Ctx())
        self.assertIsNone(sid)
        self.assertEqual(note, 'deny')

    def test_senior_global_bucket_edits_in_place(self):
        sid, note = self._session_target(1, Ctx(intake=''))
        self.assertEqual((sid, note), (B1, ''))

    def test_senior_in_intake_without_choice_returns_choose(self):
        sid, note = self._session_target(1, Ctx(intake='mehrab'))
        self.assertIsNone(sid)
        self.assertEqual(note, 'choose')

    def test_senior_in_intake_choice_intake_creates_override(self):
        sid, note = self._session_target(1, Ctx(intake='mehrab', edit_scope='intake'))
        self.assertIsNotNone(sid)
        self.assertNotEqual(sid, B1)
        self.assertEqual(self.fakedb.override_calls, [(B1, 'mehrab')])

    def test_senior_in_intake_choice_global_in_place(self):
        sid, note = self._session_target(1, Ctx(intake='mehrab', edit_scope='global'))
        self.assertEqual((sid, note), (B1, ''))

    def test_own_fork_edited_in_place(self):
        fork_id, _ = run(self.dal.bs_ensure_override(B1, 'mehrab'))
        sid, note = run(self.ca._cow_session_target(Ctx(intake='mehrab'), 2, fork_id))
        self.assertEqual(sid, fork_id)
        self.assertEqual(note, '')

    def test_book_cow_scoped(self):
        bid, note = run(self.ca._cow_book_target(Ctx(intake='x'), 2, BK1))
        self.assertIsNotNone(bid)
        self.assertEqual(self.fakedb.override_calls, [('book:' + BK1, 'mehrab')])

    def test_content_target_maps_to_fork_twin(self):
        """حذف/ترتیب فایل روی جلسه سراسری توسط scoped → فایل معادل fork."""
        fork_id, _ = run(self.dal.bs_ensure_override(B1, 'mehrab'))
        twin_id = next(str(d['_id']) for d in self.dal.bs_content.docs
                       if d.get('fork_of') == C1)
        # متدهای DAL مستقیم روی db فیک ربات (await-able)
        self.fakedb.bs_get_content_item = self.dal.bs_get_content_item
        self.fakedb.bs_content = self.dal.bs_content
        self.fakedb.bs_copy_content_item = self.dal.bs_copy_content_item
        mapped, note = run(self.ca._cow_content_target(Ctx(intake='x'), 2, C1))
        self.assertEqual(mapped, twin_id)
        # و حذف mapped فقط از fork است
        run(self.dal.bs_delete_content(twin_id))
        self.assertIsNotNone(self.dal.bs_content._by_id(C1))


class ApiCowWriteTests(unittest.TestCase):
    """ماتریس دسترسی API — edit_scope دستکاری‌شده نمی‌تواند scope را دور بزند"""

    def setUp(self):
        import api.routers.content_admin as router
        self.r = router
        self.dal = make_dal()
        seed_basic_science(self.dal)
        self._orig = router.db
        router.db = self.dal

    def tearDown(self):
        self.r.db = self._orig

    def _admin(self, kind, intake=None):
        return {'id': 2, '_scope': {'kind': kind, 'intake': intake}}

    def test_scoped_edit_scope_global_still_cows(self):
        """scoped با edit_scope='global' هم به override خودش هدایت می‌شود."""
        sid, created, note = run(self.r._cow_session_write(
            B1, self._admin('scoped', 'mehrab'), edit_scope='global'))
        self.assertNotEqual(sid, B1)
        fork = self.dal.bs_sessions._by_id(sid)
        self.assertEqual(fork['intake'], 'mehrab')

    def test_senior_intake_scope_creates_override(self):
        sid, created, note = run(self.r._cow_session_write(
            B1, self._admin('global'), edit_scope='intake',
            requested_intake='mehrab'))
        self.assertNotEqual(sid, B1)
        self.assertTrue(created)

    def test_senior_auto_in_place(self):
        sid, created, _ = run(self.r._cow_session_write(
            B1, self._admin('global'), edit_scope='auto'))
        self.assertEqual(sid, B1)
        self.assertFalse(created)

    def test_scoped_without_intake_403(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as cm:
            run(self.r._cow_session_write(B1, self._admin('scoped', ''), 'auto'))
        self.assertEqual(cm.exception.status_code, 403)

    def test_foreign_intake_403(self):
        from fastapi import HTTPException
        self.dal.bs_sessions.docs.append(
            {'_id': N2, 'lesson_id': L1, 'number': 9, 'topic': 'غیره',
             'intake': 'bahman'})
        with self.assertRaises(HTTPException) as cm:
            run(self.r._cow_session_write(N2, self._admin('scoped', 'mehrab'), 'auto'))
        self.assertEqual(cm.exception.status_code, 403)


# ════════════════════════════════════════════════════════════
# ۳) قرارداد static — «هیچ کلونی با کلیک ساخته نمی‌شود»
# ════════════════════════════════════════════════════════════

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


def read(rel):
    return open(os.path.join(ROOT, rel), encoding='utf-8', errors='replace').read()


class NoCloneOnClickContracts(unittest.TestCase):
    """T1/T5/T7/T8 — قراردادهای منبع در ۴ لایه"""

    def test_bot_has_no_fork_buttons(self):
        src = read('content_admin.py')
        self.assertNotIn('ca:fork_session:', src, 'دکمه‌ی ✂️ جلسه حذف نشده')
        self.assertNotIn('ca:fork_book:', src, 'دکمه‌ی ✂️ کتاب حذف نشده')
        self.assertNotIn('_specialize_row', src)

    def test_bot_views_do_not_write(self):
        src = read('content_admin.py')
        for view in ('_show_sessions', '_show_session_content', '_show_ref_books',
                     '_show_ref_book_files', '_show_terms', '_show_ref_subjects'):
            i = src.index(f'async def {view}')
            j = src.index('async def ', i + 10)
            body = src[i:j]
            for banned in ('bs_ensure_override', 'ref_ensure_override', 'insert_one'):
                self.assertNotIn(banned, body,
                                 f'{view} نباید بنویسد ({banned})')

    def test_bot_all_write_paths_use_cow(self):
        src = read('content_admin.py')
        # ذخیره‌ی ویرایش جلسه/آپلود محتوا/ویرایش کتاب/آپلود رفرنس
        for fragment in ("ca_mode == 'edit_session'", "ca_mode == 'waiting_description'",
                         "ca_mode == 'edit_ref_book'", "ca_mode == 'waiting_ref_description'"):
            i = src.index(fragment)
            j = src.index('elif ca_mode', i + 10)
            body = src[i:j]
            self.assertIn('_cow_', body, f'{fragment} از CoW نمی‌گذرد')
        self.assertIn('await _exec_content_action', src)
        self.assertIn("action == 'escope'", src)
        self.assertIn("action == 'merge_new'", src)
        self.assertIn('confirm_unfork_session', src)

    def test_bot_unified_markers_and_header(self):
        src = read('content_admin.py')
        self.assertIn('async def _scope_header', src)
        self.assertIn('🌐=سراسری (همه)', src)          # legend یکدست
        self.assertIn('↩️ بازگشت به نسخه‌ی سراسری', src)  # برچسب ↩️

    def test_student_sees_no_fork_marker(self):
        src = read('basic_science.py')
        self.assertNotIn('marker = "⭐ "', src)

    def test_api_edit_scope_and_logical_id(self):
        src = read('api/routers/content_admin.py')
        for ep in ('bs_edit_session_ep', 'bs_add_content_ep', 'bs_del_content_ep',
                   'bs_rename_content_ep', 'ref_edit_book_ep', 'ref_add_file_ep',
                   'ref_del_file_ep', 'ref_rename_file_ep'):
            self.assertIn(f'async def {ep}', src)
        self.assertIn('edit_scope: str = Query("auto")', src)
        self.assertIn('edit_scope: str = Form("auto")', src)
        self.assertIn('async def _cow_session_write', src)
        self.assertIn('async def _cow_book_write', src)
        self.assertIn('"logical_id"', src)
        self.assertIn('await db.bs_ensure_override(sid, target)', src)

    def test_web_admin_no_cascade_delete(self):
        src = read('api/routers/web_admin.py')
        self.assertNotIn('for f in await db.bs_sessions.find({"fork_of": sid})', src,
                         'cascade حذف forkها هنوز موجود است')
        self.assertIn('bs_session_has_forks', src)
        self.assertIn('db.bs_effective_view', src, 'درخت از قاعده‌ی مشترک DAL استفاده نمی‌کند')
        self.assertIn('"override_count"', src)

    def test_resources_no_fullscan_and_has_logical_id(self):
        src = read('api/routers/resources.py')
        self.assertNotIn('db.bs_content.find({})', src, 'full-scan شمارش فایل حذف نشده')
        self.assertNotIn('db.bs_sessions.find({})', src)
        self.assertIn('"logical_id"', src)

    def test_core_unique_partial_indexes(self):
        src = read('db/core.py')
        self.assertIn("name='uq_bs_session_fork'", src)
        self.assertIn("name='uq_ref_book_fork'", src)
        self.assertIn("partialFilterExpression={'fork_of': {'$type': 'string'}}", src)

    def test_core_logical_counts(self):
        src = read('db/core.py')
        self.assertIn("'fork_of': {'$exists': False}", src)

    def test_panel_no_instant_fork(self):
        src = read('webadmin/src/pages/Content.jsx')
        self.assertNotIn('caForkSession', src, 'دکمه‌ی 🍴 فوری هنوز در پنل است')
        self.assertIn('edit_scope', src)
        self.assertIn('override_count', src)

    def test_miniapp_no_scissors_button(self):
        src = read('miniapp/src/pages/Admin/ContentLibrary.jsx')
        self.assertNotIn('title="سفارشی‌سازی برای ورودی من"', src, 'دکمه‌ی ✂️ جلسه حذف نشده')
        self.assertNotIn('ساخت نسخه‌ی اختصاصی این کتاب', src, 'دکمه‌ی ✂️ کتاب حذف نشده')
        self.assertIn("edit_scope", src)
        self.assertIn("'intake'", src)

    def test_callback_budget(self):
        """callback_data ≤ 64B برای اکشن‌های جدید (شناسه = ۲۴ hex)."""
        samples = [
            'ca:escope:' + 'a' * 24 + ':g:be',           # 39
            'ca:confirm_unfork_session:' + 'a' * 24,     # 48
            'ca:merge_new:' + 'a' * 24,                  # 36
            'ca:edit_session_prompt:' + 'a' * 24 + ':number',  # 52
        ]
        for cb in samples:
            self.assertLessEqual(len(cb.encode()), 64, cb)


# ════════════════════════════════════════════════════════════
# ۴) رده‌بندی migration (A/B/C/D) — توابع خالص
# ════════════════════════════════════════════════════════════

class MigrationClassifierTests(unittest.TestCase):
    """T10 — رده‌بندی + انتخاب نگه‌دارنده در تکراری‌ها (قاعده C: جدیدترین/غنی‌ترین)"""

    def setUp(self):
        import sys
        sys.path.insert(0, ROOT)
        from tools.migration.content_forks import classify_forks, pick_duplicate_keepers
        self.classify = classify_forks
        self.pick = pick_duplicate_keepers
        self.base = {'_id': B1, 'number': 1, 'topic': 'معارفه', 'teacher': 'احمدی'}
        c = [{'file_id': 'f1', 'type': 'pdf', 'description': '', 'order': 0}]

        def fork(i, intake, **kw):
            d = {'_id': i, 'fork_of': B1, 'number': 1, 'topic': 'معارفه',
                 'teacher': 'احمدی', 'intake': intake}
            d.update(kw)
            return d
        self.f_same = fork('F1', 'mehrab')
        self.f_changed = fork('F2', 'mehrab', topic='ویرایش‌شده')
        self.f_dup_older = fork('F4', 'mehrab', created_at='2026-01-01')
        self.f_orphan = {'_id': 'F3', 'fork_of': 'GONE', 'number': 2,
                         'topic': 'x', 'teacher': '', 'intake': 'bahman'}
        self.contents = {B1: c, 'F1': [dict(c[0])], 'F2': [dict(c[0])],
                         'F3': [], 'F4': [dict(c[0])]}

    def test_classification(self):
        items = self.classify({B1: self.base},
                              [self.f_same, self.f_changed, self.f_orphan, self.f_dup_older],
                              self.contents)
        cls = {str(i['fork']['_id']): i['cls'] for i in items}
        self.assertEqual(cls, {'F1': 'A', 'F2': 'B', 'F3': 'D', 'F4': 'A'})

    def test_duplicate_group_keeps_single(self):
        items = self.classify({B1: self.base},
                              [self.f_same, self.f_changed, self.f_orphan, self.f_dup_older],
                              self.contents)
        items = [dict(i, nfiles=len(self.contents.get(str(i['fork']['_id']), [])))
                 for i in items]
        verdict = self.pick(items)
        keepers = [k for k, v in verdict.items() if v == 'keep']
        archivers = [k for k, v in verdict.items() if v == 'archive']
        # گروه (B1, mehrab) چهار عضو ندارد؟ F1,F2,F4 → فقط یک keep
        self.assertEqual(len(keepers), 1)
        self.assertGreaterEqual(len(archivers), 2)
        # یتیم در verdict نیست (D جداست)
        self.assertNotIn('F3', verdict)

    def test_changed_duplicate_not_a_group_of_one(self):
        """تغییرِ واقعی در گروهِ تک‌عضوی = B = حفظ."""
        items = self.classify({B1: self.base}, [self.f_changed], self.contents)
        verdict = self.pick([dict(i, nfiles=1) for i in items])
        self.assertEqual(verdict['F2'], 'keep')


if __name__ == '__main__':
    unittest.main()
