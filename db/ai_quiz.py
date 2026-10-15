# -*- coding: utf-8 -*-
"""
📚 QUIZ-PDF — لایه‌ی داده‌ی «آزمون‌ساز هوشمند از روی PDF» (فاز A).

کالکشن‌ها (attrs در DBCore تعریف شده‌اند):
  • ai_documents       — سندِ کاربر: متادیتا + ساختار مباحث + متن صفحات
  • ai_quiz_sessions   — نشست آزمون (پایدار در برابر ری‌استارت)
  • ai_quiz_questions  — سؤال کامل + نگاشت telegram_poll_id (یکتا)
  • ai_generation_logs — تله‌متری تولید (بدون محتوا/بدون secret)

اصول:
  • پاسخ کاربر «اتمیک و idempotent» ثبت می‌شود: find_one_and_update با
    شرط status='sent' — آپدیت تکراری poll_answer دوبار شمرده نمی‌شود.
  • is_correct همیشه سمت سرور از correct_index محاسبه می‌شود.
"""
import logging
from datetime import timedelta

from bson import ObjectId
from time_utils import now_utc, utc_now_iso

logger = logging.getLogger('database')


class DBAiQuiz:
    """mixin — به کلاس DB در database.py اضافه می‌شود."""

    # ── اسناد ──────────────────────────────────────────────

    async def quiz_create_document(self, owner_id: int, name: str,
                                   size_bytes: int, source: str = 'upload',
                                   file_unique_id: str = '') -> ObjectId:
        doc = {
            'owner_id': int(owner_id),
            'name': (name or 'سند بدون نام').strip()[:120],
            'status': 'processing',      # processing | ready | failed
            'error': '',
            'size_bytes': int(size_bytes or 0),
            'page_count': 0,
            'quality': 0.0,
            'quality_note': '',
            'topics': [],                # [{id, title, page_start, page_end}]
            'pages': [],                 # [{no, text, topic_id, chars}]
            'source': source,
            'file_unique_id': file_unique_id[:120],
            'created_at': utc_now_iso(),
            'updated_at': utc_now_iso(),
            'last_used_at': None,
        }
        r = await self.ai_documents.insert_one(doc)
        return r.inserted_id

    async def quiz_finish_document(self, doc_id, pages: list, topics: list,
                                   quality: float, quality_note: str = '') -> bool:
        """ذخیره‌ی نتیجه‌ی پردازش (صفحات + ساختار مباحث)."""
        res = await self.ai_documents.update_one(
            {'_id': ObjectId(doc_id)},
            {'$set': {
                'status': 'ready', 'pages': pages, 'topics': topics,
                'page_count': len(pages),
                'quality': round(float(quality or 0), 3),
                'quality_note': quality_note[:300],
                'updated_at': utc_now_iso(),
            }})
        return bool(res.matched_count)

    async def quiz_fail_document(self, doc_id, error: str) -> None:
        await self.ai_documents.update_one(
            {'_id': ObjectId(doc_id)},
            {'$set': {'status': 'failed', 'error': str(error)[:400],
                      'updated_at': utc_now_iso()}})

    async def quiz_list_documents(self, owner_id: int, limit: int = 20) -> list:
        """فهرست اسناد کاربر — بدون متن صفحات (projection)."""
        return await self.ai_documents.find(
            {'owner_id': int(owner_id)},
            {'pages': 0}).sort('created_at', -1).to_list(limit)

    async def quiz_get_document(self, doc_id, owner_id: int = None) -> dict | None:
        q = {'_id': ObjectId(doc_id)} if ObjectId.is_valid(str(doc_id)) else {}
        if not q:
            return None
        if owner_id is not None:
            q['owner_id'] = int(owner_id)   # ایزوله‌سازی مالکیت
        return await self.ai_documents.find_one(q)

    async def quiz_delete_document(self, doc_id, owner_id: int) -> int:
        """حذف سند + همه‌ی داده‌های وابسته (نشست‌ها و سؤال‌ها)."""
        from bson import ObjectId as OI
        if not OI.is_valid(str(doc_id)):
            return 0
        doc = await self.ai_documents.find_one(
            {'_id': OI(doc_id), 'owner_id': int(owner_id)}, {'_id': 1})
        if not doc:
            return 0
        sess = await self.ai_quiz_sessions.find(
            {'doc_id': doc['_id']}, {'_id': 1}).to_list(None)
        sids = [s['_id'] for s in sess]
        if sids:
            await self.ai_quiz_questions.delete_many({'session_id': {'$in': sids}})
        await self.ai_quiz_sessions.delete_many({'doc_id': doc['_id']})
        await self.ai_documents.delete_one({'_id': doc['_id']})
        return 1

    # ── نشست‌ها ────────────────────────────────────────────

    async def quiz_create_session(self, user_id: int, doc: dict,
                                  settings: dict) -> ObjectId:
        s = {
            'user_id': int(user_id),
            'doc_id': doc['_id'],
            'doc_name': doc.get('name', ''),
            'status': 'building',        # building|active|paused|finished|cancelled
            'mode': settings.get('mode', 'practice'),
            'settings': settings,
            'total_planned': int(settings.get('count', 10)),
            'sent': 0, 'answered': 0, 'correct': 0, 'wrong': 0,
            'current_order': 0,
            'created_at': utc_now_iso(),
            'started_at': None, 'finished_at': None,
            'last_activity_at': utc_now_iso(),
        }
        r = await self.ai_quiz_sessions.insert_one(s)
        return r.inserted_id

    async def quiz_get_session(self, session_id) -> dict | None:
        if not ObjectId.is_valid(str(session_id)):
            return None
        return await self.ai_quiz_sessions.find_one({'_id': ObjectId(session_id)})

    async def quiz_active_session(self, user_id: int) -> dict | None:
        """نشستِ بازِ کاربر برای ادامه بعد از قطع/ری‌استارت."""
        return await self.ai_quiz_sessions.find_one(
            {'user_id': int(user_id),
             'status': {'$in': ['building', 'active', 'paused']}})

    async def quiz_update_session(self, session_id, update: dict = None,
                                  inc: dict = None) -> bool:
        q = {'_id': ObjectId(session_id)}
        u = {'$set': {'last_activity_at': utc_now_iso(), **(update or {})}}
        if inc:
            u['$inc'] = inc
        res = await self.ai_quiz_sessions.update_one(q, u)
        return bool(res.matched_count)

    async def quiz_finish_session(self, session_id, status='finished') -> None:
        await self.ai_quiz_sessions.update_one(
            {'_id': ObjectId(session_id)},
            {'$set': {'status': status, 'finished_at': utc_now_iso(),
                      'last_activity_at': utc_now_iso()}})

    # ── سؤال‌ها ────────────────────────────────────────────

    async def quiz_add_questions(self, session_id, user_id: int, doc_id,
                                 questions: list) -> int:
        """درج دسته‌ای سؤال‌های اعتبارسنجی‌شده با order_index پیوسته."""
        if not questions:
            return 0
        last = await self.ai_quiz_questions.find_one(
            {'session_id': ObjectId(session_id)},
            sort=[('order_index', -1)], projection={'order_index': 1})
        start = int((last or {}).get('order_index', -1)) + 1
        docs = []
        for i, q in enumerate(questions):
            q = dict(q)
            q.update({
                'session_id': ObjectId(session_id),
                'user_id': int(user_id),
                'doc_id': doc_id,
                'order_index': start + i,
                # 📌 telegram_poll_id عمداً ست نمی‌شود: ایندکس unique-sparse
                # است؛ مقدار null صریح مثل مقدار تکراری رفتار می‌شود و
                # درجِ بیش از یک سؤال را با E11000 می‌شکند. غیبت فیلد =
                # مستثنی از ایندکس (سمنتیک درست sparse).
                'chat_id': None, 'message_id': None,
                'sent_at': None,
                'status': 'queued',       # queued|sent|answered|closed|skipped
                'answered_option': None, 'is_correct': None,
                'answered_at': None, 'time_ms': None,
            })
            docs.append(q)
        r = await self.ai_quiz_questions.insert_many(docs)
        return len(r.inserted_ids)

    async def quiz_next_question(self, session_id) -> dict | None:
        """کوچک‌ترین order_index با status=queued (اتمیک برای ارسال)."""
        q = await self.ai_quiz_questions.find_one_and_update(
            {'session_id': ObjectId(session_id), 'status': 'queued'},
            {'$set': {'status': 'sent'}},
            sort=[('order_index', 1)])
        return q

    async def quiz_requeue_question(self, question_id) -> None:
        """برگشت سؤال به صف (مثلاً ارسال شکست خورد)."""
        await self.ai_quiz_questions.update_one(
            {'_id': ObjectId(question_id), 'status': 'sent'},
            {'$set': {'status': 'queued'}})

    async def quiz_bind_poll(self, question_id, telegram_poll_id: str,
                             chat_id: int, message_id: int) -> bool:
        """نگاشت poll_id → سؤال (کوئری poll_answer با همین کلید است)."""
        res = await self.ai_quiz_questions.update_one(
            {'_id': ObjectId(question_id), 'status': 'sent'},
            {'$set': {'telegram_poll_id': str(telegram_poll_id),
                      'chat_id': int(chat_id),
                      'message_id': int(message_id),
                      'sent_at': utc_now_iso()}})
        return bool(res.matched_count)

    async def quiz_question_by_poll(self, telegram_poll_id: str) -> dict | None:
        return await self.ai_quiz_questions.find_one(
            {'telegram_poll_id': str(telegram_poll_id)})

    async def quiz_record_answer(self, question_id, selected_option: int,
                                 time_ms: int = None):
        """ثبت اتمیک پاسخ — خروجی:
        ('first', q)  اولین پاسخ (ثبت شد)
        ('dup', None)  آپدیت تکراری (idempotent — نادیده)
        ('stale', None) سؤال بسته/ردشده است.

        آپدیت با aggregation-pipeline انجام می‌شود تا is_correct در همان
        عملیات اتمیک سمت سرور از correct_index محاسبه شود — بدون race
        و بدون اعتماد به کلاینت. سند بازگشتی = وضعیت قبل از آپدیت."""
        sel = int(selected_option)
        q = await self.ai_quiz_questions.find_one_and_update(
            {'_id': ObjectId(question_id), 'status': 'sent'},
            [{'$set': {
                'status': 'answered',
                'answered_option': sel,
                'is_correct': {'$eq': [sel, '$correct_index']},
                'answered_at': utc_now_iso(),
                'time_ms': int(time_ms) if time_ms is not None else None,
            }}])
        if q:
            return 'first', q
        cur = await self.ai_quiz_questions.find_one(
            {'_id': ObjectId(question_id)}, {'status': 1})
        if cur and cur.get('status') == 'answered':
            return 'dup', None
        return 'stale', None

    async def quiz_session_questions(self, session_id,
                                     only_answered=False,
                                     projection=None) -> list:
        q = {'session_id': ObjectId(session_id)}
        if only_answered:
            q['status'] = 'answered'
        return await self.ai_quiz_questions.find(
            q, projection).sort('order_index', 1).to_list(None)

    async def quiz_open_polls(self, session_id) -> list:
        return await self.ai_quiz_questions.find(
            {'session_id': ObjectId(session_id),
             'telegram_poll_id': {'$ne': None},
             'status': {'$in': ['sent']}}).to_list(None)

    # ── مصرف/سقف روزانه ───────────────────────────────────

    async def quiz_usage_today(self, user_id: int) -> int:
        from time_utils import today_tehran
        u = await self.users.find_one(
            {'user_id': int(user_id)},
            {'quiz_usage_date': 1, 'quiz_usage_count': 1}) or {}
        today = today_tehran().isoformat()
        return int(u.get('quiz_usage_count') or 0) \
            if u.get('quiz_usage_date') == today else 0

    async def quiz_inc_usage(self, user_id: int, n: int) -> None:
        from time_utils import today_tehran
        today = today_tehran().isoformat()
        await self.users.update_one(
            {'user_id': int(user_id)},
            [{'$set': {
                'quiz_usage_date': today,
                'quiz_usage_count': {
                    '$cond': [
                        {'$eq': [{'$ifNull': ['$quiz_usage_date', '']}, today]},
                        {'$add': [{'$ifNull': ['$quiz_usage_count', 0]}, int(n)]},
                        int(n)]},
            }}])

    # ── تله‌متری ───────────────────────────────────────────

    async def quiz_log_generation(self, user_id: int, purpose: str,
                                  provider: str, model: str,
                                  duration_ms: int, ok: bool,
                                  chars_in: int = 0, chars_out: int = 0,
                                  items_in: int = 0, items_out: int = 0,
                                  error_type: str = '') -> None:
        """لاگ تولید — فقط اعداد؛ هیچ محتوای سند/سؤال/کلید ثبت نمی‌شود."""
        try:
            await self.ai_generation_logs.insert_one({
                'user_id': int(user_id), 'purpose': purpose[:24],
                'provider': str(provider)[:24], 'model': str(model)[:64],
                'duration_ms': int(duration_ms or 0), 'ok': bool(ok),
                'chars_in': int(chars_in or 0), 'chars_out': int(chars_out or 0),
                'items_in': int(items_in or 0), 'items_out': int(items_out or 0),
                'error_type': str(error_type)[:64],
                'at': utc_now_iso(),
            })
        except Exception:
            logger.debug('quiz_log_generation failed', exc_info=True)

    # ── نگهداری/پاکسازی ───────────────────────────────────

    async def quiz_cleanup_old_documents(self, days: int = 90) -> int:
        """حذف اسناد (و داده‌های وابسته) قدیمی‌تر از `days` روز.

        idempotent؛ نشست‌های بازِ تازه را دست نمی‌زند."""
        cutoff = (now_utc() - timedelta(days=int(days))).isoformat()
        old = await self.ai_documents.find(
            {'created_at': {'$lt': cutoff},
             'status': {'$ne': 'processing'}},
            {'_id': 1, 'owner_id': 1}).to_list(None)
        removed = 0
        for d in old:
            removed += await self.quiz_delete_document(d['_id'], d['owner_id'])
        return removed
