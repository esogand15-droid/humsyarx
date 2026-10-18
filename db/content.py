# -*- coding: utf-8 -*-
"""
🗄️ HUMSYAR DB layer — 🌊 موج Q2/W12: ماژولارسازی database.py
این ماژول بخشی از mixinهای کلاس DB است؛ facade در database.py بدون تغییر
رفتار، همه‌ی importهای قبلی را سالم نگه می‌دارد.
"""
import os
import re
import logging
import asyncio
from datetime import datetime, timedelta
from html import escape
from urllib.parse import quote
from bson import ObjectId
from pymongo import ReturnDocument
import motor.motor_asyncio
from time_utils import today_tehran, utc_now_iso, now_utc, format_date_fa, format_time_fa
from question_bank.contracts import (
    DIFFICULTY_LABELS, and_query, approved_query, canonical_difficulty,
    canonical_status, status_query,
)

# نام logger عمداً «database» نگه داشته شد تا کانال لاگ تغییر نکند
logger = logging.getLogger('database')



class DBContent:


    async def bs_get_lessons(self, term: str, intake=None):
        q = {'term': term}
        q.update(self._intake_q(intake))
        return await self.bs_lessons.find(q).sort('order', 1).to_list(50)


    async def bs_add_lesson(self, term: str, name: str, teacher: str = '',
                            intake: str = ''):
        intake = intake or ''
        if await self.bs_lessons.find_one(
                {'term': term, 'name': name, 'intake': intake}):
            return None
        count = await self.bs_lessons.count_documents(
            {'term': term, 'intake': intake})
        r = await self.bs_lessons.insert_one({
            'term': term, 'name': name, 'teacher': teacher,
            'intake': intake,
            'order': count, 'created_at': utc_now_iso(),
        })
        return r.inserted_id


    async def bs_get_lesson(self, lesson_id: str):
        try:
            return await self.bs_lessons.find_one({'_id': ObjectId(lesson_id)})
        except Exception:
            return None


    async def bs_update_lesson(self, lesson_id: str, data: dict) -> bool:
        try:
            await self.bs_lessons.update_one({'_id': ObjectId(lesson_id)}, {'$set': data})
            return True
        except Exception:
            return False


    async def bs_delete_lesson(self, lesson_id: str):
        try:
            await self.bs_lessons.delete_one({'_id': ObjectId(lesson_id)})
            sessions = await self.bs_sessions.find({'lesson_id': lesson_id}).to_list(200)
            for s in sessions:
                await self.bs_content.delete_many({'session_id': str(s['_id'])})
            await self.bs_sessions.delete_many({'lesson_id': lesson_id})
        except Exception as e:
            logger.warning(f"bs_delete_lesson: {e}")


    # ══════════════════════════════════════════════════
    #  علوم پایه — جلسات
    # ══════════════════════════════════════════════════

    async def bs_get_sessions(self, lesson_id: str):
        """🛡 §۸۳ — مرتب‌سازی با `order` (کلیدی که reorder می‌نویسد).

        پیش‌تر با `number` مرتب می‌شد، پس دکمه‌های ↑↓ در پنل هیچ اثری
        نداشتند: سرور order را جابه‌جا می‌کرد ولی خواندن همچنان بر اساس
        شماره‌ی جلسه بود. `number` معیار دوم می‌ماند تا داکیومنت‌های قدیمی
        که هنوز order ندارند (همه صفر) ترتیب طبیعیِ خودشان را حفظ کنند.
        """
        return await self.bs_sessions.find({'lesson_id': lesson_id}) \
            .sort([('order', 1), ('number', 1)]).to_list(200)


    async def bs_add_session(self, lesson_id: str, number: int, topic: str, teacher: str,
                             intake: str = None):
        """🌊 موج C3 — پارامتر اختیاری intake:
          • intake=None/'' → رفتار قدیمی (بدون فیلد intake؛ یکتایی lesson+number).
          • intake=کد      → «فرزند ورودی‌خاص» زیر همان درس: فیلد intake روی سند
             نوشته می‌شود و یکتایی داخل همان سطل سنجیده می‌شود.

        ⚠️ چرا کلید یکتایی تغییر کرد: قبلاً find_one روی (lesson_id, number) بود،
        پس یک جلسه‌ی ورودی‌خاص با شماره‌ی جلسه‌ی سراسری، *به‌جای درج*، topic/teacher
        نسخه‌ی سراسری را بازنویسی می‌کرد (§۹.۵ گزارش). در حالت intake='' هم رفتار
        قبلی حفظ شده تا اسناد legacy و مسیرهای 🎓 هیچ تغییری نکنند.

        🧷 lesson_id به رشته نرمال می‌شود: همه‌ی خوانده‌ها (bs_get_sessions، نمای
        مؤثر، API، ربات) با str(_id) می‌پرسند؛ اگر جایی ObjectId رد شود جلسه
        یتیم می‌شود (در هیچ لیستی دیده نمی‌شود) — بی‌صدا و غیرقابل‌بازیابی."""
        lesson_id = str(lesson_id or '')
        parent_li = await self.lesson_intake(lesson_id)
        eff_intake = str(intake or '').strip()
        # اگر درس والد خودش مختص یک ورودی خاص است، جلسه زیر آن نیز متعلق به همان ورودی است
        # و نباید دو سند مجزا (یکی با فیلد intake و یکی بدون فیلد intake) برای یک شماره جلسه ساخته شود.
        if parent_li and (not eff_intake or eff_intake == parent_li):
            existing = await self.bs_sessions.find_one({
                'lesson_id': lesson_id,
                'number': number,
                'archived': {'$ne': True},
            })
            if existing:
                await self.bs_sessions.update_one(
                    {'_id': existing['_id']},
                    {'$set': {'topic': topic, 'teacher': teacher}}
                )
                return str(existing['_id'])
            r = await self.bs_sessions.insert_one({
                'lesson_id': lesson_id, 'number': number, 'topic': topic,
                'teacher': teacher, 'created_at': utc_now_iso(),
            })
            return str(r.inserted_id)

        if eff_intake:
            existing = await self.bs_sessions.find_one(
                {'lesson_id': lesson_id, 'number': number, 'intake': eff_intake, 'archived': {'$ne': True}})
            if existing:
                await self.bs_sessions.update_one(
                    {'_id': existing['_id']},
                    {'$set': {'topic': topic, 'teacher': teacher}}
                )
                return str(existing['_id'])
            r = await self.bs_sessions.insert_one({
                'lesson_id': lesson_id, 'number': number, 'topic': topic,
                'teacher': teacher, 'intake': eff_intake,
                'created_at': utc_now_iso(),
            })
            return str(r.inserted_id)
        existing = await self.bs_sessions.find_one({
            'lesson_id': lesson_id,
            'number': number,
            'archived': {'$ne': True},
            '$or': [{'intake': ''}, {'intake': None}, {'intake': {'$exists': False}}],
        })
        if not existing:
            # fallback برای سازگاری با FakeColl در تست‌های واحد که $or ندارند
            try:
                cand = await self.bs_sessions.find_one({'lesson_id': lesson_id, 'number': number})
                if cand and not str(cand.get('intake') or '').strip() and not cand.get('archived'):
                    existing = cand
            except Exception:
                pass
        if existing:
            await self.bs_sessions.update_one(
                {'_id': existing['_id']},
                {'$set': {'topic': topic, 'teacher': teacher}}
            )
            return str(existing['_id'])
        r = await self.bs_sessions.insert_one({
            'lesson_id': lesson_id, 'number': number, 'topic': topic,
            'teacher': teacher, 'created_at': utc_now_iso(),
        })
        return str(r.inserted_id)


    async def bs_next_session_number(self, lesson_id: str, intake: str = None) -> int:
        """پیشنهاد شماره‌ی بعدی جلسه.
        intake=None → ماکزیممِ *همه‌ی* جلسات درس (رفتار «len+۱» را با ماکزیمم
          عوض می‌کند تا حذف‌شدن‌ها شماره‌ی تکراری نسازند).
        intake=کد   → ماکزیممِ (جلسات همان ورودی ∪ جلسات سراسری) تا در نمای
          مؤثر دانشجو (سراسری + ورودی من) دو «جلسه‌ی n» نداشته باشیم.
        ⚠️ یکتایی همچنان داخل سطل خودش است؛ این فقط UX شماره‌گذاری است."""
        q = {'lesson_id': str(lesson_id or '')}
        if intake:
            q['$or'] = [
                {'intake': intake},
                {'intake': {'$in': ['', None]}},
                {'intake': {'$exists': False}},
            ]
        mx = 0
        async for s in self.bs_sessions.find(q, {'number': 1}):
            try:
                n = int(s.get('number') or 0)
            except (TypeError, ValueError):
                n = 0
            if n > mx:
                mx = n
        return mx + 1



    async def bs_session_number_taken(self, lesson_id: str, number: int,
                                      intake: str = None) -> bool:
        """آیا این شماره‌ی جلسه گرفته شده است؟
        intake=کد → فقط در سطل همان ورودی؛ intake=None/'' → در سطل سراسری
        (اسناد legacy بدون فیلد intake هم «سراسری» حساب می‌شوند)."""
        q = {'lesson_id': lesson_id, 'number': number}
        if intake:
            q['intake'] = intake
        else:
            q['$or'] = [{'intake': {'$in': ['', None]}}, {'intake': {'$exists': False}}]
        return bool(await self.bs_sessions.find_one(q, {'_id': 1}))


    async def bs_get_session(self, sid: str):
        try:
            return await self.bs_sessions.find_one({'_id': ObjectId(sid)})
        except Exception:
            return None


    async def bs_update_session(self, session_id: str, data: dict) -> bool:
        try:
            await self.bs_sessions.update_one({'_id': ObjectId(session_id)}, {'$set': data})
            return True
        except Exception:
            return False


    async def bs_delete_session(self, sid: str):
        try:
            await self.bs_sessions.delete_one({'_id': ObjectId(sid)})
            await self.bs_content.delete_many({'session_id': sid})
        except Exception as e:
            logger.warning(f"bs_delete_session: {e}")


    # ══════════════════════════════════════════════════
    #  علوم پایه — محتوا
    # ══════════════════════════════════════════════════

    async def bs_get_content(self, session_id: str):
        return await self.bs_content.find({'session_id': session_id}).sort('order', 1).to_list(50)


    # ── 📄 File naming & branding — Step 4-14 of rename spec ──
    async def bs_add_content(self, session_id: str, ctype: str, file_id: str,
                             description: str = '', extra_info: str = '',
                             original_name: str = '', display_name: str = '',
                             file_extension: str = '', mime_type: str = '',
                             file_size: int = 0, branding_enabled: bool = False):
        """
        Extended with file-naming fields (backward compatible).
        original_name: Telegram original file_name (or synthetic for photo)
        display_name: admin-chosen final name (includes extension)
        If display_name empty -> derived from original_name or fallback.
        Handles duplicate (1), sanitization assumed done by caller; here
        we defensively sanitize again and ensure extension preservation.
        """
        from utils_file_naming import (
            prepare_rename, get_extension, sanitize_filename)
        # 🔴 FIX-R1 (مورد ۴) — «-» یعنی «بدون توضیح» (قرارداد ربات)؛
        # همیشه به‌صورت رشته‌ی خالی ذخیره می‌شود تا ruleهای کیفیت داده
        # و نمایش‌ها مقدار واقعی (خالی = اختیاری) را ببینند، نه placeholder.
        description = (description or '').strip()
        if description in ('-', '—', '–'):
            description = ''
        # Determine extension
        ext = (file_extension or '').strip().lower().lstrip('.')
        if not ext and display_name:
            ext = get_extension(display_name)
        if not ext and original_name:
            ext = get_extension(original_name)
        if not ext:
            # infer from mime? keep empty
            ext = ''
        # Prepare display name via utility (sanitize + truncate + dedup)
        existing = set()
        try:
            async for doc in self.bs_content.find({'session_id': session_id}, {'display_name': 1}):
                dn = doc.get('display_name') or doc.get('display_file_name') or ''
                if dn:
                    existing.add(dn)
        except Exception:
            pass
        # Choose user_input vs original
        user_input = (display_name or '').strip()
        orig_for_build = original_name or display_name or ''
        # If both empty, fallback to generic
        if not user_input and not orig_for_build:
            fallback_base = 'فایل'
            # use description as hint?
            if description.strip():
                fallback_base = sanitize_filename(description.strip()[:60]) or 'فایل'
            user_input = fallback_base
        prep = prepare_rename(user_input, orig_for_build or (mime_type or ''), existing_names=existing, fallback='فایل')
        final_display = prep['display_name']
        # If caller forced ext separately and prep didn't use it, fix
        if ext and get_extension(final_display) != ext:
            base = final_display.rsplit('.', 1)[0] if '.' in final_display else final_display
            final_display = f"{base}.{ext}"
        final_original = original_name or final_display
        # Ensure original sanitized for storage but preserve as given for audit
        mime = (mime_type or 'application/octet-stream').strip()[:120]
        size = max(0, int(file_size or 0))
        count = await self.bs_content.count_documents({'session_id': session_id})
        doc = {
            'session_id': session_id, 'type': ctype, 'file_id': file_id,
            'description': description, 'extra_info': extra_info,
            'order': count, 'uploaded_at': utc_now_iso(), 'downloads': 0,
            'notif_sent': False,
            # new naming fields
            'original_file_name': final_original[:255],
            'display_file_name': final_display[:255],
            # legacy alias for older code (display || original)
            'display_name': final_display[:255],
            'file_extension': ext[:10],
            'mime_type': mime,
            'file_size': size,
            'branding_enabled': bool(branding_enabled),
        }
        r = await self.bs_content.insert_one(doc)
        return r.inserted_id


    # ══════════════════════════════════════════════════
    #  FIX جدید: نوتیف دسته‌ای منابع جدید (هر N ساعت)
    # ══════════════════════════════════════════════════

    async def get_unnotified_resources(self) -> list:
        """
        محتوای جدیدی که هنوز برای آن نوتیف ارسال نشده.
        FIX جدید: علاوه بر bs_content (منابع علوم‌پایه)، فایل‌های
        رفرنس (ref_files) هم اضافه شدند — طبق تصمیم صریح ادمین.
        هر آیتم با کلید داخلی '_source' مشخص می‌شود که از
        کدام کالکشن آمده، تا هم متن نوتیف و هم علامت‌گذاری نهایی
        بدانند با کدام کالکشن طرفند.
        🌊 C1.5 — کلید '_intake' هم به هر آیتم متصل می‌شود (از طریق
        resolver والد: bs_content←درس، ref_files←موضوع) تا جریان نوتیف
        scope-aware شود: سراسری→همه، ورودی X→فقط دانشجویان X.
        ⚡ W1 — batch resolve: قبلاً به‌ازای هر آیتم دو کوئری تودرتو
        (session→lesson / book→subject) می‌رفت (N+1)؛ حالا والدها با
        $in یک‌جا خوانده و در حافظه join می‌شوند. معنای resolver دقیقاً
        حفظ شده: intake صریح سند والد (fork) مقدم بر ارث از ریشه است.
        """
        from bson import ObjectId as _OId

        def _oids(vals):
            out = []
            for v in vals:
                try:
                    out.append(_OId(str(v)))
                except Exception:
                    pass
            return out

        bs_items = await self.bs_content.find({'notif_sent': {'$ne': True}}).to_list(200)
        if bs_items:
            _sids = {it.get('session_id', '') for it in bs_items}
            _sobs = _oids(_sids)
            _smap = {str(s['_id']): s for s in await self.bs_sessions.find(
                {'_id': {'$in': _sobs}}).to_list(500)} if _sobs else {}
            _lids = {s.get('lesson_id', '') for s in _smap.values()}
            _lobs = _oids(_lids)
            _lmap = {str(l['_id']): l for l in await self.bs_lessons.find(
                {'_id': {'$in': _lobs}}).to_list(500)} if _lobs else {}
        for it in bs_items:
            it['_source'] = 'bs_content'
            s = _smap.get(str(it.get('session_id', '')))
            if s is None:
                it['_intake'] = ''
            elif 'intake' in s:
                it['_intake'] = s.get('intake') or ''
            else:
                it['_intake'] = ((_lmap.get(str(s.get('lesson_id', ''))) or {})
                                 .get('intake') or '')

        ref_items = await self.ref_files.find({'notif_sent': {'$ne': True}}).to_list(200)
        if ref_items:
            _bids = {it.get('book_id', '') for it in ref_items}
            _bobs = _oids(_bids)
            _bmap = {str(b['_id']): b for b in await self.ref_books.find(
                {'_id': {'$in': _bobs}}).to_list(500)} if _bobs else {}
            _sjids = {b.get('subject_id', '') for b in _bmap.values()}
            _sjobs = _oids(_sjids)
            _sjmap = {str(s['_id']): s for s in await self.ref_subjects.find(
                {'_id': {'$in': _sjobs}}).to_list(500)} if _sjobs else {}
        for it in ref_items:
            it['_source'] = 'ref_files'
            b = _bmap.get(str(it.get('book_id', '')))
            if b is None:
                it['_intake'] = ''
            elif 'intake' in b:
                it['_intake'] = b.get('intake') or ''
            else:
                it['_intake'] = ((_sjmap.get(str(b.get('subject_id', ''))) or {})
                                 .get('intake') or '')

        return bs_items + ref_items


    async def mark_resources_notified(self, content_ids: list):
        """علامت‌گذاری محتوای علوم‌پایه ارسال‌شده تا دوباره اعلام نشود"""
        if not content_ids:
            return
        await self.bs_content.update_many(
            {'_id': {'$in': [ObjectId(c) if isinstance(c, str) else c for c in content_ids]}},
            {'$set': {'notif_sent': True}}
        )


    async def mark_ref_files_notified(self, file_ids: list):
        """FIX جدید: علامت‌گذاری فایل‌های رفرنس ارسال‌شده — موازی و
        مستقل از mark_resources_notified، تا هیچ تغییری روی منطق
        فعلی bs_content اعمال نشود."""
        if not file_ids:
            return
        await self.ref_files.update_many(
            {'_id': {'$in': [ObjectId(c) if isinstance(c, str) else c for c in file_ids]}},
            {'$set': {'notif_sent': True}}
        )


    async def migrate_mark_existing_ref_files_notified(self):
        """
        FIX جدید (یک‌بار در post_init اجرا می‌شود، idempotent):
        رفرنس‌هایی که از قبل توی دیتابیس بودند و فیلد notif_sent
        ندارند، به‌عنوان «قبلاً دیده‌شده» علامت می‌خورند — تا اولین
        اجرای job بعد از این آپدیت، یک‌جا سیل نوتیف قدیمی نفرستد.
        فقط رفرنس‌هایی که از این به بعد آپلود/جایگزین می‌شوند وارد
        صف نوتیف واقعی می‌شوند.
        """
        already_done = await self.get_setting('ref_notif_migration_done', False)
        if already_done:
            return
        result = await self.ref_files.update_many(
            {'notif_sent': {'$exists': False}},
            {'$set': {'notif_sent': True}}
        )
        await self.set_setting('ref_notif_migration_done', True)
        logger.info(
            f"📖 مهاجرت یک‌باره نوتیف رفرنس‌ها: {result.modified_count} فایل قدیمی "
            f"به‌عنوان قبلاً-دیده‌شده علامت خورد"
        )


    async def bs_get_content_item(self, cid: str):
        try:
            return await self.bs_content.find_one({'_id': ObjectId(cid)})
        except Exception:
            return None


    async def bs_get_content_full_path(self, cid: str) -> dict:
        """
        FIX جدید: زنجیره کامل یک فایل محتوا — درس، ترم، مبحث، استاد.
        برای گزارش ایراد دقیق و نوتیف منابع جدید استفاده می‌شود.
        """
        item = await self.bs_get_content_item(cid)
        if not item:
            return {}
        session = await self.bs_get_session(item.get('session_id', ''))
        lesson  = await self.bs_get_lesson(session.get('lesson_id', '')) if session else None
        return {
            'content':     item,
            'session':     session or {},
            'lesson':      lesson or {},
            'lesson_name': lesson.get('name', '') if lesson else '',
            'term':        lesson.get('term', '') if lesson else '',
            'topic':       session.get('topic', '') if session else '',
            'teacher':     session.get('teacher', '') or (lesson.get('teacher', '') if lesson else ''),
            'content_type': item.get('type', ''),
            'description':  item.get('description', ''),
        }


    async def bs_delete_content(self, cid: str):
        # 🛡 AUDIT-R6 — خطای حذف نباید بلعیده شود: None = خطا، عدد = تعداد حذف‌شده
        # (قبلاً پنل «موفق» گزارش می‌داد درحالی‌که آیتم سر جایش بود).
        try:
            r = await self.bs_content.delete_one({'_id': ObjectId(cid)})
            return int(getattr(r, 'deleted_count', 0) or 0)
        except Exception as e:
            logger.error(f"bs_delete_content failed for {cid}: {e}")
            return None


    async def bs_inc_download(self, cid: str, uid: int):
        try:
            await self.bs_content.update_one({'_id': ObjectId(cid)}, {'$inc': {'downloads': 1}})
        except Exception:
            pass
        # 👑 P1 — رویداد پرستیژ دانلود در تک‌منبع DB (پوشش بات+API):
        # اولین‌بار (pre-check شمارش لاگ) + تکمیل همه‌ی محتوای یک جلسه
        first_time = False
        lesson_done = False
        try:
            first_time = (await self.stats_col.count_documents(
                {'user_id': uid, 'action': 'bs_download',
                 'data.content_id': str(cid)})) == 0
        except Exception:
            pass
        await self.log(uid, 'bs_download', {'content_id': cid})
        try:
            content = await self.bs_content.find_one({'_id': ObjectId(cid)})
            sid = (content or {}).get('session_id')
            if sid:
                sess_docs = await self.bs_content.find({'session_id': sid}).to_list(500)
                sess_ids = {str(d.get('_id')) for d in sess_docs}
                mine = await self.stats_col.find(
                    {'user_id': uid, 'action': 'bs_download'}).to_list(2000)
                got = {str((m.get('data') or {}).get('content_id') or '')
                       for m in mine}
                lesson_done = bool(sess_ids) and sess_ids.issubset(got)
        except Exception:
            pass
        try:
            await self.prestige_event(uid, 'file_download',
                {'first_time': first_time, 'lesson_done': lesson_done})
        except Exception:
            pass


    def _resolve_display_name(self, doc: dict) -> str:
        """Backward-compatible filename resolver (display||original||description||file_id)."""
        for key in ('display_file_name', 'display_name', 'original_file_name', 'description'):
            val = (doc or {}).get(key, '')
            if isinstance(val, str) and val.strip():
                # ensure extension preserved? just return
                return val.strip()
        # fallback: file_id short
        fid = (doc or {}).get('file_id', '') or 'فایل'
        return str(fid)[:40]

    async def bs_update_content_filename(self, content_id: str, new_display: str) -> bool:
        """Rename existing content (re-upload already done outside). Idempotent."""
        try:
            from utils_file_naming import sanitize_filename, get_extension, truncate_display_filename
            # sanitize but keep ext
            ext = get_extension(new_display)
            base = new_display.rsplit('.', 1)[0] if ext and '.' in new_display else new_display
            base = sanitize_filename(base)
            final = f"{base}.{ext}" if ext else base
            final = truncate_display_filename(final)
            await self.bs_content.update_one({'_id': ObjectId(content_id)}, {'$set': {
                'display_file_name': final[:255],
                'display_name': final[:255],
                'file_extension': ext[:10],
            }})
            return True
        except Exception:
            return False

    async def migrate_file_naming(self):
        """Idempotent migration: backfill missing naming fields for legacy docs."""
        already = await self.get_setting('file_naming_migration_done', False)
        if already:
            return {'bs': 0, 'ref': 0, 'skipped': True}
        bs_mod = 0
        ref_mod = 0
        # bs_content
        async for doc in self.bs_content.find({'display_file_name': {'$exists': False}}):
            # derive from description or file_id
            hint = (doc.get('description') or '').strip()[:60] or 'فایل'
            # use generic fallback + type as ext hint? keep plain
            fallback = hint
            # pick ext from type?
            type_ext = {'pdf': 'pdf', 'ppt': 'pptx', 'video': 'mp4', 'voice': 'mp3'}.get(doc.get('type',''), '')
            if type_ext and '.' not in fallback:
                fallback = f"{fallback}.{type_ext}"
            # try to store
            try:
                from utils_file_naming import get_extension, sanitize_filename
                # simple
                await self.bs_content.update_one({'_id': doc['_id']}, {'$set': {
                    'display_file_name': fallback[:255],
                    'display_name': fallback[:255],
                    'original_file_name': fallback[:255],
                    'file_extension': get_extension(fallback),
                    'mime_type': 'application/octet-stream',
                    'file_size': 0,
                    'branding_enabled': False,
                }})
                bs_mod += 1
            except Exception:
                continue
        async for doc in self.ref_files.find({'display_file_name': {'$exists': False}}):
            hint = (doc.get('description') or '').strip()[:60] or f"رفرنس_{doc.get('volume',1)}"
            fallback = hint
            if '.' not in fallback:
                fallback = f"{fallback}.pdf"
            try:
                from utils_file_naming import get_extension
                await self.ref_files.update_one({'_id': doc['_id']}, {'$set': {
                    'display_file_name': fallback[:255],
                    'display_name': fallback[:255],
                    'original_file_name': fallback[:255],
                    'file_extension': get_extension(fallback),
                    'mime_type': 'application/octet-stream',
                    'file_size': 0,
                    'branding_enabled': False,
                }})
                ref_mod += 1
            except Exception:
                continue
        await self.set_setting('file_naming_migration_done', True)
        logger.info(f"📄 file_naming migration: bs={bs_mod} ref={ref_mod}")
        return {'bs': bs_mod, 'ref': ref_mod, 'skipped': False}

    async def search_resources(self, query_text: str, intake=None):
        """
        FIX جدید: قبلاً هر آیتم فقط '_session' (شامل topic/teacher) داشت
        ولی اسم درس (lesson name) روی خود session نیست، روی bs_lessons
        است — و search.py با فرض غلط r.get('lesson','') می‌خواند که
        همیشه خالی برمی‌گشت. حالا '_lesson' هم (با کش ساده در همین
        اجرا، چون چند session می‌توانند lesson_id مشترک داشته باشند)
        به هر نتیجه اضافه می‌شود.
        🌊 C1.5 — پارامتر اختیاری intake: None=رفتار قدیمی (ادمین)؛
        لیست student_intake_filter = post-filter بر اساس scope دید،
        پس حتی *عنوان* محتوای ورودی دیگر هم در نتایج دیده نمی‌شود.
        🍴 Q1 (موج QA) — دقیق‌سازی fork:
          ۱) scope هر «جلسه» بر اساس intake صریح خودش (fork) وگرنه درسِ
          والد سنجیده می‌شود — قبلاً فقط درس چک می‌شد و fork ورودی X
          برای دانشجوی ورودی Y در جستجو لو می‌رفت (نشت).
          ۲) baseای که برای ورودیِ بیننده fork دارد سرکوب می‌شود تا
          نتیجه‌ی تکراری (base+fork با هم) نمایش داده نشود.
        """
        import re
        regex = {'$regex': re.escape(query_text), '$options': 'i'}
        sessions = await self.bs_sessions.find(
            {'$or': [{'topic': regex}, {'teacher': regex}]}
        ).to_list(20)
        result = []
        result_sessions = []
        lesson_cache: dict = {}

        async def _lesson_for(lesson_id: str) -> dict:
            if not lesson_id:
                return {}
            if lesson_id not in lesson_cache:
                lesson_cache[lesson_id] = await self.bs_get_lesson(lesson_id) or {}
            return lesson_cache[lesson_id]

        # ورودیِ مشخص بیننده (غیر سراسری) — برای قاعده‌ی سرکوب baseها
        viewer = None
        if intake is not None:
            _vals = intake if isinstance(intake, (list, tuple, set)) else [intake]
            viewer = next((v for v in _vals if v), None)
        forked_bases = set()
        if viewer:
            # یک کوئری گروهی (بدون N+1): baseهایی که forkِ همین ورودی دارند
            for f in await self.bs_sessions.find(
                    {'intake': viewer, 'fork_of': {'$ne': None}}).to_list(5000):
                forked_bases.add(str(f.get('fork_of')))

        def _in_scope(sess_doc: dict, lesson_doc: dict) -> bool:
            # None = بدون محدودیت؛ غیر None (str/list) = scope دید
            if intake is None:
                return True
            sd = sess_doc or {}
            si = (sd.get('intake') if 'intake' in sd
                  else (lesson_doc or {}).get('intake')) or ''
            if isinstance(intake, (list, tuple, set)):
                return si in intake
            return si == (intake or '')

        for s in sessions:
            sid = str(s['_id'])
            lesson_doc = await _lesson_for(s.get('lesson_id', ''))
            if not _in_scope(s, lesson_doc):
                continue
            if viewer and sid in forked_bases:
                continue  # نسخه‌ی اختصاصی همان ورودی جایگزین base شده است
            s['_lesson_resolved'] = lesson_doc
            result_sessions.append(s)
        # ⚡ W1 — batch: قبلاً به‌ازای هر جلسه یک کوئری محتوا (N+1)؛
        # حالا یک کوئری گروهی با $in
        vids = [str(s['_id']) for s in result_sessions]
        if vids:
            _contents = await self.bs_content.find(
                {'session_id': {'$in': vids}}).to_list(500)
            _by_sess: dict = {}
            for c in _contents:
                _by_sess.setdefault(c.get('session_id', ''), []).append(c)
            for s in result_sessions:
                sid = str(s['_id'])
                for c in _by_sess.get(sid, [])[:10]:
                    c['_session'] = s
                    c['_lesson']  = s.get('_lesson_resolved') or {}
                    result.append(c)
            for s in result_sessions:
                s.pop('_lesson_resolved', None)
        direct = await self.bs_content.find({'description': regex}).to_list(10)
        existing_ids = {str(r['_id']) for r in result}
        # ⚡ W1 — batch: sessionهای شاخه‌ی direct هم یک‌جا خوانده می‌شوند
        _need = [str(c.get('session_id', '')) for c in direct
                 if str(c['_id']) not in existing_ids]
        _sess_map: dict = {}
        if _need:
            from bson import ObjectId as _OId
            _oids = [_OId(x) for x in _need if len(x) == 24]
            _docs2 = await self.bs_sessions.find(
                {'_id': {'$in': _oids}}).to_list(50) if _oids else []
            _sess_map = {str(x['_id']): x for x in _docs2}
        for c in direct:
            if str(c['_id']) not in existing_ids:
                sess = _sess_map.get(str(c.get('session_id', '')), {})
                lesson_doc = await _lesson_for(sess.get('lesson_id', ''))
                if not _in_scope(sess, lesson_doc):
                    continue
                if viewer and str(sess.get('_id', '')) in forked_bases:
                    continue
                c['_session'] = sess
                c['_lesson']  = lesson_doc
                result.append(c)
        return result[:15]


    # ══════════════════════════════════════════════════
    #  ترتیب‌بندی
    # ══════════════════════════════════════════════════

    async def _normalize_order(self, col, query_filter: dict):
        items = await col.find(query_filter).to_list(1000)
        # 🌊 WA3-fix — order مفقود/None در داکیومنت legacy مقایسه را نمی‌شکند
        items.sort(key=lambda x: ((x.get('order') if isinstance(x.get('order'), int) else 99999),
                                  str(x['_id'])))
        updates = []
        for i, item in enumerate(items):
            if item.get('order') != i:
                updates.append(col.update_one({'_id': item['_id']}, {'$set': {'order': i}}))
                item['order'] = i
        if updates:
            await asyncio.gather(*updates)
        return items


    async def reorder_up(self, collection: str, doc_id: str, query_filter: dict) -> bool:
        try:
            col = getattr(self, collection)
            items = await self._normalize_order(col, query_filter)
            ids = [str(it['_id']) for it in items]
            if doc_id not in ids: return False
            idx = ids.index(doc_id)
            if idx == 0: return False
            await asyncio.gather(
                col.update_one({'_id': items[idx]['_id']},     {'$set': {'order': idx - 1}}),
                col.update_one({'_id': items[idx - 1]['_id']}, {'$set': {'order': idx}}),
            )
            return True
        except Exception as e:
            logger.warning(f"reorder_up: {e}")
            return False


    async def reorder_down(self, collection: str, doc_id: str, query_filter: dict) -> bool:
        try:
            col = getattr(self, collection)
            items = await self._normalize_order(col, query_filter)
            ids = [str(it['_id']) for it in items]
            if doc_id not in ids: return False
            idx = ids.index(doc_id)
            if idx >= len(items) - 1: return False
            await asyncio.gather(
                col.update_one({'_id': items[idx]['_id']},     {'$set': {'order': idx + 1}}),
                col.update_one({'_id': items[idx + 1]['_id']}, {'$set': {'order': idx}}),
            )
            return True
        except Exception as e:
            logger.warning(f"reorder_down: {e}")
            return False


    async def reorder_content_up(self, content_id: str, session_id: str) -> bool:
        try:
            items = await self._normalize_order(self.bs_content, {'session_id': session_id})
            ids = [str(it['_id']) for it in items]
            if content_id not in ids: return False
            idx = ids.index(content_id)
            if idx == 0: return False
            await asyncio.gather(
                self.bs_content.update_one({'_id': items[idx]['_id']},     {'$set': {'order': idx - 1}}),
                self.bs_content.update_one({'_id': items[idx - 1]['_id']}, {'$set': {'order': idx}}),
            )
            return True
        except Exception:
            return False


    async def reorder_content_down(self, content_id: str, session_id: str) -> bool:
        try:
            items = await self._normalize_order(self.bs_content, {'session_id': session_id})
            ids = [str(it['_id']) for it in items]
            if content_id not in ids: return False
            idx = ids.index(content_id)
            if idx >= len(items) - 1: return False
            await asyncio.gather(
                self.bs_content.update_one({'_id': items[idx]['_id']},     {'$set': {'order': idx + 1}}),
                self.bs_content.update_one({'_id': items[idx + 1]['_id']}, {'$set': {'order': idx}}),
            )
            return True
        except Exception:
            return False


    # ══════════════════════════════════════════════════
    #  رفرنس‌ها
    # ══════════════════════════════════════════════════

    async def ref_get_subjects(self, intake=None):
        q = self._intake_q(intake)
        return await self.ref_subjects.find(q).sort('order', 1).to_list(100)


    async def ref_add_subject(self, name: str, intake: str = ''):
        intake = intake or ''
        if await self.ref_subjects.find_one({'name': name, 'intake': intake}):
            return None
        count = await self.ref_subjects.count_documents({'intake': intake})
        r = await self.ref_subjects.insert_one({
            'name': name, 'intake': intake,
            'order': count, 'created_at': utc_now_iso(),
        })
        return r.inserted_id


    async def ref_get_subject(self, sid: str):
        try:
            return await self.ref_subjects.find_one({'_id': ObjectId(sid)})
        except Exception:
            return None


    async def ref_update_subject(self, subject_id: str, data: dict) -> bool:
        try:
            await self.ref_subjects.update_one({'_id': ObjectId(subject_id)}, {'$set': data})
            return True
        except Exception:
            return False


    async def ref_delete_subject(self, sid: str):
        try:
            await self.ref_subjects.delete_one({'_id': ObjectId(sid)})
            books = await self.ref_books.find({'subject_id': sid}).to_list(100)
            for b in books:
                await self.ref_files.delete_many({'book_id': str(b['_id'])})
            await self.ref_books.delete_many({'subject_id': sid})
        except Exception as e:
            logger.warning(f"ref_delete_subject: {e}")


    async def ref_get_books(self, subject_id: str):
        return await self.ref_books.find({'subject_id': subject_id}).sort('order', 1).to_list(50)


    async def ref_add_book(self, subject_id: str, name: str, intake: str = None):
        """🌊 C3 — ساخت کتاب رفرنس.

        • intake=None/'' → رفتار پیشین، بیت‌به‌بیت (سند فیلد intake ندارد و
          از موضوع ارث می‌برد — هیچ migration لازم نیست)
        • intake='A'   → کتاب «فقط ورودی A» (فرزندِ scope‌دار زیر موضوع 🌐 یا
          موضوع ورودیِ خودش)؛ کلید سطل روی خود سند نوشته می‌شود تا resolver
          زنجیره‌ای (ref_book_intake) و نمای مؤثر (ref_get_books_effective)
          همان چیزی را ببینند که برای جلسه‌های اختصاصی استفاده می‌شود.

        subject_id همیشه به str نرمال می‌شود: خوانده‌ها با str(_id) کوئری
        می‌زنند و ObjectIdِ خام، سند یتیم تولید می‌کرد (همان درس §۱۵.۵ب).
        """
        subject_id = str(subject_id or '')
        intake = (intake or '').strip() or None
        count = await self.ref_books.count_documents({'subject_id': subject_id})
        doc = {'subject_id': subject_id, 'name': name,
               'order': count, 'created_at': utc_now_iso()}
        if intake:
            doc['intake'] = intake
        r = await self.ref_books.insert_one(doc)
        return r.inserted_id


    @staticmethod
    def ref_books_order_filter(book: dict) -> dict:
        """🌊 C3 — فیلتر «هم‌سطل» برای جابه‌جایی ترتیب کتاب رفرنس.

        ترتیب کتاب‌ها کلید مشترک `(subject_id, order)` است و در آن سطل‌ها
        قاطی‌اند؛ بدون این فیلتر، ⬆️⬇️ روی یک سندِ ورودی‌خاص (fork یا فرزند
        C3) ترتیبِ **پایه‌ی سراسری** را هم جابه‌جا می‌کرد — یعنی نشتِ نوشتن
        به سطل دیگر. قانون: هر سطل فقط با همسطل‌های خودش swap می‌شود.
        """
        q = {'subject_id': str(book.get('subject_id') or '')}
        if book.get('fork_of') or (book.get('intake') or ''):
            q['intake'] = book.get('intake') or ''
        else:
            q['fork_of'] = {'$in': [None, '']}
            q['$or'] = [{'intake': ''}, {'intake': None}, {'intake': {'$exists': False}}]
        return q

    async def ref_get_book(self, bid: str):
        try:
            return await self.ref_books.find_one({'_id': ObjectId(bid)})
        except Exception:
            return None


    async def ref_update_book(self, book_id: str, data: dict) -> bool:
        try:
            await self.ref_books.update_one({'_id': ObjectId(book_id)}, {'$set': data})
            return True
        except Exception:
            return False


    async def ref_delete_book(self, bid: str):
        try:
            await self.ref_books.delete_one({'_id': ObjectId(bid)})
            await self.ref_files.delete_many({'book_id': bid})
        except Exception as e:
            logger.warning(f"ref_delete_book: {e}")


    async def ref_get_files(self, book_id: str):
        return await self.ref_files.find({'book_id': book_id}).sort('order', 1).to_list(20)


    async def ref_get_files_page(self, book_id: str, skip: int = 0, limit: int = 50):
        """Bounded admin listing; keeps Mini App/domain reads unchanged."""
        query = {'book_id': book_id}
        total = await self.ref_files.count_documents(query)
        items = await self.ref_files.find(query).sort('order', 1).skip(skip).limit(limit).to_list(limit)
        return items, total


    async def ref_add_file(self, book_id: str, lang: str, file_id: str,
                           volume: int = 1, description: str = '',
                           original_name: str = '', display_name: str = '',
                           file_extension: str = '', mime_type: str = '',
                           file_size: int = 0, branding_enabled: bool = False):
        # Extended with file-naming (backward compatible). See bs_add_content.
        from utils_file_naming import prepare_rename, get_extension, sanitize_filename
        # 🔴 FIX-R1 (مورد ۴) — نرمال‌سازی «بدون توضیح» (قرارداد ربات: «-»)
        description = (description or '').strip()
        if description in ('-', '—', '–'):
            description = ''
        ext = (file_extension or '').strip().lower().lstrip('.')
        if not ext and display_name:
            ext = get_extension(display_name)
        if not ext and original_name:
            ext = get_extension(original_name)
        if not ext:
            ext = ''
        # collect existing display names for this book
        existing_set = set()
        try:
            async for doc in self.ref_files.find({'book_id': book_id}, {'display_name': 1, 'display_file_name': 1}):
                dn = doc.get('display_name') or doc.get('display_file_name') or ''
                if dn:
                    existing_set.add(dn)
        except Exception:
            pass
        user_input = (display_name or '').strip()
        orig_for_build = original_name or display_name or ''
        if not user_input and not orig_for_build:
            fallback_base = sanitize_filename(description.strip()[:60]) if description.strip() else 'فایل'
            user_input = fallback_base or 'فایل'
        prep = prepare_rename(user_input, orig_for_build or (mime_type or ''), existing_names=existing_set, fallback='فایل')
        final_display = prep['display_name']
        if ext and get_extension(final_display) != ext:
            base = final_display.rsplit('.', 1)[0] if '.' in final_display else final_display
            final_display = f"{base}.{ext}"
        final_original = (original_name or final_display)[:255]
        mime = (mime_type or 'application/octet-stream').strip()[:120]
        size = max(0, int(file_size or 0))
        existing = await self.ref_files.find_one({'book_id': book_id, 'lang': lang, 'volume': volume})
        if existing:
            await self.ref_files.update_one({'_id': existing['_id']}, {'$set': {
                'file_id': file_id, 'description': description,
                'uploaded_at': utc_now_iso(),
                'notif_sent': False,
                'original_file_name': final_original,
                'display_file_name': final_display[:255],
                'display_name': final_display[:255],
                'file_extension': ext[:10],
                'mime_type': mime,
                'file_size': size,
                'branding_enabled': bool(branding_enabled),
            }})
            return str(existing['_id'])
        count = await self.ref_files.count_documents({'book_id': book_id})
        r = await self.ref_files.insert_one({
            'book_id': book_id, 'lang': lang, 'volume': volume,
            'description': description, 'file_id': file_id,
            'uploaded_at': utc_now_iso(), 'downloads': 0, 'order': count,
            'notif_sent': False,
            'original_file_name': final_original,
            'display_file_name': final_display[:255],
            'display_name': final_display[:255],
            'file_extension': ext[:10],
            'mime_type': mime,
            'file_size': size,
            'branding_enabled': bool(branding_enabled),
        })
        return str(r.inserted_id)


    async def ref_get_file_full_path(self, fid: str) -> dict:
        """
        FIX جدید: زنجیره‌ی کامل یک فایل رفرنس — موضوع، کتاب، جلد، زبان.
        دقیقاً هم‌الگو با bs_get_content_full_path؛ برای نوتیف «منابع
        جدید» استفاده می‌شود تا فایل‌های رفرنس هم بتوانند گروه‌بندی و
        نمایش داده شوند.
        """
        item = await self.ref_get_file(fid)
        if not item:
            return {}
        book = await self.ref_get_book(item.get('book_id', ''))
        subject = await self.ref_get_subject(book.get('subject_id', '')) if book else None
        lang_label = '🇮🇷 فارسی' if item.get('lang') == 'fa' else '🌐 لاتین'
        vol = item.get('volume', 1)
        return {
            'content':      item,
            'book':         book or {},
            'subject':      subject or {},
            'lesson_name':  subject.get('name', '') if subject else '',
            'topic':        book.get('name', '') if book else '',
            'content_type': 'ref',
            'description':  item.get('description') or f"{book.get('name','') if book else ''} — جلد {vol} — {lang_label}",
        }


    async def ref_get_file(self, fid: str):
        try:
            return await self.ref_files.find_one({'_id': ObjectId(fid)})
        except Exception:
            return None


    async def ref_inc_download(self, fid: str, uid: int):
        try:
            await self.ref_files.update_one({'_id': ObjectId(fid)}, {'$inc': {'downloads': 1}})
        except Exception:
            pass
        first_time = False
        try:
            first_time = (await self.stats_col.count_documents(
                {'user_id': uid, 'action': 'ref_download',
                 'data.file_id': str(fid)})) == 0
        except Exception:
            pass
        await self.log(uid, 'ref_download', {'file_id': fid})
        try:
            await self.prestige_event(uid, 'file_download',
                                      {'first_time': first_time})
        except Exception:
            pass


    async def ref_delete_file(self, fid: str):
        # 🛡 AUDIT-R6 — خطای حذف نباید بلعیده شود: None = خطا، عدد = تعداد حذف‌شده
        # (قبلاً پنل «موفق» گزارش می‌داد درحالی‌که آیتم سر جایش بود).
        try:
            r = await self.ref_files.delete_one({'_id': ObjectId(fid)})
            return int(getattr(r, 'deleted_count', 0) or 0)
        except Exception as e:
            logger.error(f"ref_delete_file failed for {fid}: {e}")
            return None


    # ══════════════════════════════════════════════════
    #  سوالات تستی
    # ══════════════════════════════════════════════════

    async def search_questions_text(self, query_text: str, limit: int = 10,
                                    intake=None) -> list:
        """جستجوی آزادِ متنی (نه فیلترِ درس/موضوع) — برای Function Callingِ هوشیار.
        🌊 C1.5 — پارامتر دفاعی intake: None=رفتار قدیمی (مصرف فعلی:
        ابزار admin_search_questions مخصوص مالک)؛ اگر روزی مسیر دانشجویی
        اضافه شد، باید student_intake_filter پاس بدهد."""
        if not query_text:
            return []
        # 🛡 AUDIT-R3 — ورودی کاربر «متن» است نه الگو: بدون escape، `.*` یک
        # full-scan بی‌نهایت و `(` خطای Mongo می‌ساخت (نمونه‌ی global_search).
        rx = {'$regex': re.escape(query_text), '$options': 'i'}
        return await self.questions.find(
            and_query(approved_query(), {'$or': [{'question': rx}, {'explanation': rx}]}, self._intake_q(intake))
        ).limit(limit).to_list(limit)


    async def get_question_by_id(self, qid: str):
        try:
            return await self.questions.find_one({'_id': ObjectId(qid)})
        except Exception:
            return None


    async def get_daily_rotation_question(self):
        """
        FIX جدید — باگ قبلی: daily_question_job همیشه یک سوال ثابت
        می‌فرستاد (اولین نتیجه بدون sort). حالا بر اساس قدیمی‌ترین
        last_daily_sent چرخشی انتخاب می‌شود — یعنی واقعاً هر روز سوال
        عوض می‌شود و یک دور کامل بانک سوال طی می‌شود.
        """
        q = await self.questions.find(
            approved_query()
        ).sort('last_daily_sent', 1).limit(1).to_list(1)
        if not q:
            return None
        chosen = q[0]
        await self.questions.update_one(
            {'_id': chosen['_id']},
            {'$set': {'last_daily_sent': utc_now_iso()}}
        )
        return chosen


    # ══════════════════════════════════════════════════
    #  بانک سوالات — لایه‌ی Query برای سیستم تولید آزمون PDF
    #  (جدا از منطق تولید PDF؛ فقط دیتابیس را می‌شناسد)
    # ══════════════════════════════════════════════════

    async def get_qbank_lessons(self, intake=None) -> list:
        """درس‌هایی که واقعاً در بانک سوالِ تأییدشده سوال دارند.
        🌊 C1.5 — intake اختیاری: None=رفتار قدیمی، لیست=scope دید دانشجو."""
        return sorted([l for l in await self.questions.distinct(
            'lesson', and_query(approved_query(), self._intake_q(intake))) if l])


    async def get_qbank_chapters(self, lesson: str, intake=None) -> list:
        """
        فصل‌های موجود برای یک درس — فقط فصل‌هایی که واقعاً سوال دارند.
        اگه هیچ سوالی فصل نداشته باشه (چون هنوز این فیلد پر نشده)
        لیست خالی برمی‌گرده و ربات این مرحله رو خودکار رد می‌کنه —
        کاملاً سازگار با سوالات قدیمی که فیلد chapter ندارند.
        🌊 C1.5 — intake اختیاری (None=رفتار قدیمی).
        """
        chapters = await self.questions.distinct(
            'chapter', and_query(approved_query(), {'lesson': lesson, 'chapter': {'$nin': [None, '']}}, self._intake_q(intake))
        )
        return sorted([c for c in chapters if c])


    async def get_qbank_topics(self, lesson: str, chapter: str = None, intake=None) -> list:
        """مباحث موجود برای درس (و در صورت انتخاب، فصل) — فقط مباحث دارای سوال.
        🌊 C1.5 — intake اختیاری (None=رفتار قدیمی)."""
        match = and_query(approved_query(), {'lesson': lesson}, self._intake_q(intake))
        if chapter:
            match['chapter'] = chapter
        topics = await self.questions.distinct('topic', match)
        return sorted([t for t in topics if t])


    async def get_qbank_difficulties(self, lesson: str, chapter: str = None, topic: str = None,
                                     intake=None) -> list:
        """سطوح سختیِ واقعاً موجود برای این فیلتر (برای مرحله‌ی اختیاری انتخاب سختی).
        🌊 C1.5 — intake اختیاری (None=رفتار قدیمی)."""
        match = and_query(approved_query(), {'lesson': lesson}, self._intake_q(intake))
        if chapter: match['chapter'] = chapter
        if topic and topic != 'همه': match['topic'] = topic
        diffs = await self.questions.distinct('difficulty', match)
        return [d for d in diffs if d]


    async def count_qbank_questions(self, lesson: str, chapter: str = None,
                                     topic: str = None, difficulty: str = None,
                                     tags: list = None, intake=None) -> int:
        """تعداد سوالات موجود برای یک فیلتر — برای نمایش قبل از تولید PDF.
        🌊 C1.5 — intake اختیاری (None=رفتار قدیمی)."""
        match = self._exam_match(lesson, chapter, topic, difficulty, tags,
                                 intake=intake)
        return await self.questions.count_documents(match)


    def _exam_match(self, lesson, chapter=None, topic=None, difficulty=None,
                     tags=None, exclude_ids=None, intake=None) -> dict:
        # 🌊 C1.5 — intake اختیاری: None=بدون فیلتر (ادمین/داخلی)،
        # لیست student_intake_filter = سوالات سراسری + ورودی خود دانشجو
        match = and_query(approved_query(), {'lesson': lesson}, self._intake_q(intake))
        if chapter: match['chapter'] = chapter
        if topic and topic != 'همه': match['topic'] = topic
        if difficulty:
            key = canonical_difficulty(difficulty)
            match['difficulty'] = {'$in': [key, DIFFICULTY_LABELS[key]]}
        if tags: match['tags'] = {'$in': tags}
        if exclude_ids:
            try:
                match['_id'] = {'$nin': [ObjectId(i) for i in exclude_ids]}
            except Exception:
                pass
        return match


    async def get_exam_questions(self, lesson: str, chapter: str = None, topic: str = None,
                                  difficulty: str = None, tags: list = None, count: int = 20,
                                  randomize: bool = True, exclude_ids: list = None,
                                  intake=None) -> list:
        """
        هسته‌ی «Randomizer + Query» برای تولید آزمون:
        - فیلتر بر اساس درس/فصل/مبحث/سختی/تگ (هر کدام اختیاری)
        - randomize=True → انتخاب تصادفی با $sample (بدون تکرار داخل
          همان خروجی، چون $sample به‌طور طبیعی سندهای یکتا برمی‌گرداند)
        - randomize=False → ترتیب سیستماتیک بر اساس تاریخ ثبت (قدیمی‌ترین اول)
        - exclude_ids: هوک آماده برای قابلیت آینده‌ی «جلوگیری از تکرار
          سوالات بین آزمون‌های مختلف یک دانشجو» — کافیست شناسه‌ی
          سوالاتی که قبلاً دریافت کرده به این پارامتر داده شود.
        """
        match = self._exam_match(lesson, chapter, topic, difficulty, tags,
                                 exclude_ids, intake=intake)
        if randomize:
            pipeline = [{'$match': match}, {'$sample': {'size': count}}]
            return await self.questions.aggregate(pipeline).to_list(count)
        return await self.questions.find(match).sort('created_at', 1).to_list(count)


    async def get_users_map(self, uids: list) -> dict:
        """
        نگاشت {user_id: نام} برای نمایش «طراح سوال» در PDF — یک کوئری
        دسته‌ای به‌جای N کوئری جدا برای هر سوال.
        """
        if not uids:
            return {}
        docs = await self.users.find({'user_id': {'$in': list(set(uids))}}).to_list(len(set(uids)))
        return {d['user_id']: d.get('name', '') for d in docs}


    async def save_answer(self, uid: int, qid: str, selected: int, is_correct: bool):
        await self.answers.insert_one({
            'user_id': uid, 'question_id': qid,
            'selected': selected, 'is_correct': is_correct,
            'answered_at': utc_now_iso(),
        })
        inc = {'total_answers': 1}
        if is_correct: inc['correct_answers'] = 1
        await self.users.update_one({'user_id': uid}, {'$inc': inc})
        try:
            await self.questions.update_one(
                {'_id': ObjectId(qid)},
                {'$inc': {'attempt_count': 1, 'correct_count': 1 if is_correct else 0}}
            )
        except Exception: pass
        if not is_correct:
            try:
                q_doc = await self.questions.find_one({'_id': ObjectId(qid)})
                if q_doc:
                    await self.users.update_one(
                        {'user_id': uid}, {'$addToSet': {'weak_topics': q_doc['topic']}}
                    )
            except Exception: pass
        await self.log(uid, 'answer', {'qid': qid, 'correct': is_correct})


    async def get_lessons(self, term: str = None, intake=None):
        """
        دروس بانک سوال از bs_lessons (پنل محتوا) — سینک کامل.
        FIX جدید: پارامتر term اختیاری — برای دسته‌بندی ترم به ترم
        در بانک سوال (مثل بخش منابع علوم پایه)، نه نمایش تخت همه‌چی.
        🌊 C1.5 — پارامتر اختیاری intake: None = رفتار قدیمی (ادمین/داخلی)،
        لیست student_intake_filter = فقط نام درس‌های قابل‌مشاهده برای دانشجو.
        """
        q = {'term': term} if term else {}
        q.update(self._intake_q(intake))
        lessons = await self.bs_lessons.find(q).sort([('term', 1), ('order', 1)]).to_list(500)
        seen, names = set(), []
        for l in lessons:
            n = l.get('name', '').strip()
            if n and n not in seen:
                seen.add(n); names.append(n)
        return names


    async def get_topics(self, lesson: str = None, intake=None):
        """مباحث بانک سوال از bs_sessions همان درس.
        🌊 C1.5 — در حالت scoped (intake != None) روی *همه‌ی* lesson-docهای
        همنامِ داخل scope کار می‌کند (union): دیگر find_one({'name'}) نیست،
        چون یک نام می‌تواند هم سراسری هم ورودی باشد و find_one ممکن بود
        doc ورودی دیگر را برگرداند (نشت مباحث). intake=None = رفتار قدیمی."""
        if not lesson:
            sessions = await self.bs_sessions.find({}).to_list(2000)
        elif intake is not None:
            lesson_docs = await self.bs_lessons.find(
                dict({'name': lesson}, **self._intake_q(intake))).to_list(100)
            if not lesson_docs:
                return []
            lids = [str(d['_id']) for d in lesson_docs]
            sessions = await self.bs_sessions.find(
                {'lesson_id': {'$in': lids}}).sort('number', 1).to_list(1000)
        else:
            lesson_doc = await self.bs_lessons.find_one({'name': lesson})
            if not lesson_doc:
                return []
            sessions = await self.bs_sessions.find(
                {'lesson_id': str(lesson_doc['_id'])}
            ).sort('number', 1).to_list(500)
        seen, topics = set(), []
        for s in sessions:
            t = s.get('topic', '').strip()
            if t and t not in seen:
                seen.add(t); topics.append(t)
        return topics


    # ══════════════════════════════════════════════════
    #  برنامه
    # ══════════════════════════════════════════════════

    @staticmethod
    def _sched_minutes(hm: str) -> int | None:
        """HH:MM → دقیقه از نیمه‌شب؛ نامعتبر ⇒ None."""
        try:
            h, m = str(hm or '').strip().split(':')
            h, m = int(h), int(m)
            if 0 <= h < 24 and 0 <= m < 60:
                return h * 60 + m
        except (ValueError, AttributeError):
            pass
        return None

    async def schedule_find_conflicts(self, group: str, date: str,
                                      time: str, end_time: str = '',
                                      exclude_id: str = '',
                                      educational_group: str = None,
                                      term: str = None,
                                      stype: str = 'class') -> list:
        """🌊 W8/UX-05 — برنامه‌های هم‌گروهِ هم‌روز که بازه‌ی زمانی‌شان
        با بازه‌ی داده‌شده هم‌پوشانی دارد (هشدار، نه خطا).

        قوانین استاندارد عدم تداخل کاذب:
        ۱) فقط رکوردهای فعال (archived != True) و در همان ترم (term) بررسی می‌شوند.
        ۲) ساعت امتحان (exam) مستقل از ساعت کلاس هفتگی (class) است.
        ۳) کلاس مخصوص آقایان (male_only) با کلاس مخصوص بانوان (female_only) تداخل ندارد.
        ۴) فرمول بازه باز: start_a < end_b and start_b < end_a (کلاس ۰۸ تا ۱۰ با ۱۰ تا ۱۲ تداخل ندارد).
        """
        start = self._sched_minutes(time)
        if start is None:
            return []
        end = self._sched_minutes(end_time)
        if end is None or end <= start:
            end = start + 120
        group = (self.normalize_group(group) or 'هر دو').strip()
        target_edu = self.normalize_class_educational_group(educational_group, default='mixed')
        target_type_bucket = 'exam' if str(stype or 'class').strip() == 'exam' else 'class'

        cur = await self.schedules.find(
            {'date': date, 'is_weekly': {'$ne': True}}).to_list(200)
        out = []
        for s in cur or []:
            if s.get('archived'):
                continue
            if exclude_id and str(s.get('_id')) == str(exclude_id):
                continue
            if term and s.get('term') and str(s.get('term')).strip() != str(term).strip():
                continue
            s_type = str(s.get('type') or 'class').strip()
            s_bucket = 'exam' if s_type == 'exam' else 'class'
            if s_bucket != target_type_bucket:
                continue
            g = (self.normalize_group(s.get('group')) or 'هر دو').strip()
            if group != 'هر دو' and g != 'هر دو' and g != group:
                continue
            s_edu = self.normalize_class_educational_group(s.get('educational_group'), default='mixed')
            if (target_edu == 'male_only' and s_edu == 'female_only') or (
                target_edu == 'female_only' and s_edu == 'male_only'
            ):
                continue
            s0 = self._sched_minutes(s.get('time') or '')
            if s0 is None:
                continue
            s1 = self._sched_minutes(s.get('end_time') or '')
            if s1 is None or s1 <= s0:
                s1 = s0 + 120
            if start < s1 and s0 < end:
                out.append({'id': str(s.get('_id')),
                            'type': s.get('type', ''),
                            'lesson': s.get('lesson', ''),
                            'teacher': s.get('teacher', ''),
                            'time': s.get('time', ''),
                            'end_time': s.get('end_time', ''),
                            'group': g,
                            'educational_group': s_edu})
        return out

    async def add_schedule(self, stype: str, lesson: str, teacher: str,
                           date: str, time: str, location: str,
                           notes: str = '', group: str = 'هر دو', is_weekly: bool = False,
                           flex_type: str = 'fixed', flex_note: str = '', end_time: str = '',
                           credit: float = None, educational_group: str = 'mixed',
                           term: str = None, course_code: str = ''):
        """
        FIX جدید: flex_type — 'fixed' (ثابت) یا 'flexible' (منعطف).
        برای کلاس منعطف، flex_note آخرین زمان اعلام‌شده را نگه می‌دارد.
        🕒 range: end_time اختیاری HH:MM برای بازه (08:00 تا 10:00) — اگر خالی باشد تک‌ساعت حساب می‌شود.
        """
        group = self.normalize_group(group) or 'هر دو'
        edu_group = self.normalize_class_educational_group(educational_group, default='mixed')
        # normalize time/end_time: if time contains range like "08:00-10:00" split
        _etime = (end_time or "").strip()
        _stime = (time or "").strip()
        if _stime and ("-" in _stime or "تا" in _stime) and not _etime:
            try:
                from time_utils import en_digits as _en
                import re as _re
                raw = _en(_stime).replace('—','-').replace('–','-').replace('تا','-')
                times = _re.findall(r'(\d{1,2}:\d{2})', raw)
                if len(times) >= 2:
                    _stime = f"{int(times[0].split(':')[0]):02d}:{times[0].split(':')[1]}"
                    _etime = f"{int(times[1].split(':')[0]):02d}:{times[1].split(':')[1]}"
                elif len(times)==1 and '-' in raw:
                    # try 8-10 without colon
                    parts = raw.split('-')
                    if len(parts)==2:
                        b = _re.search(r'(\d{1,2})', parts[1])
                        if b:
                            _etime = f"{int(b.group(1)):02d}:00"
                            _stime = times[0]
            except Exception:
                pass
        doc = {
            'type': stype, 'lesson': lesson, 'teacher': teacher,
            'date': date, 'time': _stime, 'location': location,
            'notes': notes, 'group': group, 'educational_group': edu_group,
            'is_weekly': is_weekly, 'archived': False,
            'flex_type': flex_type, 'flex_note': flex_note,
            'created_at': utc_now_iso(), 'notified_days': [],
        }
        if term:
            doc['term'] = str(term).strip()
        if course_code:
            doc['course_code'] = str(course_code).strip()
        if _etime:
            doc['end_time'] = _etime
        if credit is not None:
            try:
                doc['credit'] = max(0.5, min(10.0, float(credit)))
            except (TypeError, ValueError):
                pass
        r = await self.schedules.insert_one(doc)
        return r.inserted_id


    async def update_schedule_time(self, sid: str, new_date: str, new_time: str, note: str = '', end_time: str = ''):
        """
        FIX جدید: تغییر زمان یک کلاس منعطف — برای اعلام به‌روز شدن زمان
        برگزاری به دانشجویان استفاده می‌شود.
        🕒 range: اگر end_time داده شد ذخیره می‌شود، در غیر این صورت پاک نمی‌شود تا داده قدیمی حفظ شود.
        """
        try:
            payload = {'date': new_date, 'time': new_time, 'flex_note': note,
                       'last_time_change': utc_now_iso()}
            if end_time is not None and str(end_time).strip() != "":
                payload['end_time'] = str(end_time).strip()
            elif end_time == "":
                # explicit empty -> remove? keep as empty to clear legacy range
                payload['end_time'] = ""
            await self.schedules.update_one(
                {'_id': ObjectId(sid)},
                {'$set': payload}
            )
            return True
        except Exception:
            return False


    async def get_schedule_by_id(self, sid: str):
        """
        FIX جدید (بخش اول — ویرایش برنامه): گرفتن یک برنامه با ID،
        برای نمایش اطلاعات فعلی قبل از ویرایش.
        """
        try:
            return await self.schedules.find_one({'_id': ObjectId(sid)})
        except Exception:
            return None


    async def update_schedule_field(self, sid: str, field: str, value) -> bool:
        """
        FIX جدید (بخش اول — ویرایش برنامه): ویرایش یک فیلد مشخص از یک
        برنامه‌ی موجود. حتماً از UPDATE استفاده می‌شود، نه INSERT —
        رکورد جدیدی ساخته نمی‌شود و ID برنامه ثابت می‌ماند.
        """
        allowed_fields = {'date', 'time', 'location', 'teacher', 'lesson', 'notes', 'group', 'educational_group', 'term', 'course_code'}
        if field not in allowed_fields:
            return False
        if field == 'group':
            value = self.normalize_group(value) or 'هر دو'
        elif field == 'educational_group':
            value = self.normalize_class_educational_group(value, default='mixed')
        try:
            result = await self.schedules.update_one(
                {'_id': ObjectId(sid)},
                {'$set': {field: value, 'last_edited_at': utc_now_iso()}}
            )
            return result.matched_count > 0
        except Exception:
            logger.exception('update_schedule_field failed')
            return False


    async def update_schedule_full(self, sid: str, lesson: str, teacher: str,
                                    date: str, time: str, location: str,
                                    notes: str = '', group: str = 'هر دو',
                                    flex_type: str = 'fixed', flex_note: str = '', end_time: str = '',
                                    credit: float = None, educational_group: str = None,
                                    term: str = None, course_code: str = None) -> bool:
        """
        FIX جدید (بخش اول — ویرایش برنامه): ویرایش کامل همه فیلدهای یک
        برنامه‌ی موجود با یک UPDATE واحد. رکورد جدید ساخته نمی‌شود و
        ID برنامه دست‌نخورده باقی می‌ماند.
        🕒 range: end_time اختیاری
        """
        try:
            group = self.normalize_group(group) or 'هر دو'
            payload = {
                'lesson': lesson, 'teacher': teacher, 'date': date, 'time': time,
                'location': location, 'notes': notes, 'group': group,
                'flex_type': flex_type, 'flex_note': flex_note,
                'last_edited_at': utc_now_iso(),
            }
            if educational_group is not None:
                payload['educational_group'] = self.normalize_class_educational_group(educational_group, default='mixed')
            if term is not None and str(term).strip():
                payload['term'] = str(term).strip()
            if course_code is not None:
                payload['course_code'] = str(course_code).strip()
            if end_time is not None:
                payload['end_time'] = str(end_time).strip()
            if credit is not None:
                try:
                    payload['credit'] = max(0.5, min(10.0, float(credit)))
                except (TypeError, ValueError):
                    pass
            result = await self.schedules.update_one(
                {'_id': ObjectId(sid)},
                {'$set': payload}
            )
            return result.matched_count > 0
        except Exception:
            logger.exception('update_schedule_full failed')
            return False


    async def get_schedules(self, stype: str = None, upcoming: bool = True, group: str = None,
                            term: str = None, educational_group: str = None,
                            include_archived: bool = False):
        from utils import now_tehran
        q = {}
        if stype:    q['type'] = stype
        if upcoming: q['date'] = {'$gte': now_tehran().strftime('%Y-%m-%d')}
        if group:
            aliases = self.group_aliases(group)
            q['$or'] = [
                {'group': {'$in': aliases}},
                {'group': 'هر دو'},
                {'group': 'هردو'},
                {'group': ''},
                {'group': None},
                {'group': {'$exists': False}},
            ]
        raw_items = await self.schedules.find(q).sort('date', 1).to_list(300)
        out = []
        for item in (raw_items or []):
            if not include_archived and item.get('archived'):
                continue
            if term and item.get('term') and str(item.get('term')).strip() != str(term).strip():
                continue
            if educational_group is not None:
                if not self.class_matches_user_educational_group(
                    item.get('educational_group'), educational_group
                ):
                    continue
            out.append(item)
        return out


    async def delete_schedule(self, sid: str):
        # 🛡 AUDIT-R6 — خطای حذف نباید بلعیده شود: None = خطا، عدد = تعداد حذف‌شده
        # (قبلاً پنل «موفق» گزارش می‌داد درحالی‌که آیتم سر جایش بود).
        try:
            r = await self.schedules.delete_one({'_id': ObjectId(sid)})
            return int(getattr(r, 'deleted_count', 0) or 0)
        except Exception as e:
            logger.error(f"delete_schedule failed for {sid}: {e}")
            return None


    async def schedule_notify_event(self, item: dict, event: str) -> dict:
        """صف واحد اعلان برنامه برای APIهای وب/مینی‌اپ.

        targetها از ترجیح دقیق نوع رویداد (exam/makeup/schedule) و گروه
        canonical می‌آیند. هم DM outbox و هم Inbox از همین payload ساخته
        می‌شوند تا create/update/cancel/flex بین سطوح مدیریتی همسان بماند.
        """
        if event not in {'created', 'updated', 'cancelled', 'time_changed'}:
            raise ValueError('schedule_event_invalid')
        item = dict(item or {})
        stype = item.get('type') or 'class'
        pref = {'exam': 'exam', 'makeup': 'makeup'}.get(stype, 'schedule')
        ntype = 'exam' if stype == 'exam' else ('makeup' if stype == 'makeup' else 'class')
        icon = {'class': '🏫', 'exam': '📝', 'makeup': '🔄'}.get(stype, '📅')
        label = {'class': 'کلاس', 'exam': 'امتحان', 'makeup': 'جبرانی'}.get(stype, 'برنامه')
        event_label = {
            'created': 'جدید', 'updated': 'به‌روزرسانی شد',
            'cancelled': 'لغو شد', 'time_changed': 'تغییر زمان',
        }[event]
        prefix = '❌' if event == 'cancelled' else ('🔔' if event == 'updated' else icon)
        title_plain = f'{prefix} {label} {event_label}'
        lesson = str(item.get('lesson') or '').strip()
        teacher = str(item.get('teacher') or '').strip()
        date = str(item.get('date') or '').strip()
        time = str(item.get('time') or '').strip()
        location = str(item.get('location') or '').strip()
        group = self.normalize_group(item.get('group')) or 'هر دو'
        note = str(item.get('flex_note') or item.get('notes') or item.get('note') or '').strip()

        html_lines = [f'{prefix} <b>{escape(label)} {escape(event_label)}</b>',
                      f'📚 {escape(lesson)}']
        plain_lines = [f'📚 {lesson}']
        if teacher:
            html_lines.append(f'👨‍🏫 {escape(teacher)}')
            plain_lines.append(f'👨‍🏫 {teacher}')
        # 🛡 AUDIT-FIX (جلالی): تاریخ میلادیِ ذخیره‌سازی هرگز خام به کاربر
        # نشان داده نمی‌شود — هم‌سبک مسیر ربات (schedule.py/bot.py).
        date_fa = format_date_fa(date, long=True, weekday=True, date_only=True,
                                 fallback=date) if date else ''
        time_fa = format_time_fa(time, fallback=time) if time else ''
        when = f'📅 {escape(date_fa)}' + (f'  ⏰ {escape(time_fa)}' if time_fa else '')
        html_lines.append(when)
        plain_lines.append(f'📅 {date_fa}' + (f'  ⏰ {time_fa}' if time_fa else ''))
        if location:
            html_lines.append(f'📍 {escape(location)}')
            plain_lines.append(f'📍 {location}')
        if group != 'هر دو':
            html_lines.append(f'👥 گروه {escape(group)}')
            plain_lines.append(f'👥 گروه {group}')
        if note and event == 'time_changed':
            html_lines.append(f'📝 {escape(note)}')
            plain_lines.append(f'📝 {note}')

        try:
            users = await self.notif_users(pref, group=group)
            documents = [{
                'type': f'schedule_{event}', 'chat_id': u['user_id'],
                'text': '\n'.join(html_lines), 'sent': False,
                'created_at': utc_now_iso(),
            } for u in users if u.get('user_id')]
            if documents:
                await self.bot_notifs.insert_many(documents)
            await self.inbox_add_many([{
                'user_id': u['user_id'], 'type': ntype,
                'title': title_plain, 'body': '\n'.join(plain_lines),
                'link': '/schedule?hl=' + quote(lesson),
            } for u in users if u.get('user_id')])
            return {'notified': len(documents), 'preference': pref, 'group': group}
        except Exception as exc:
            logger.warning('schedule notification failed (%s/%s): %s', stype, event, exc)
            return {'notified': 0, 'preference': pref, 'group': group}


    # ══════════════════════════════════════════════════
    #  📅 الگوهای هفتگی (شنبه-جمعه) — تکرار خودکار
    #  هر الگو یک کلاسِ هفتگی است که در expand به تاریخ‌های واقعی تبدیل می‌شود
    # ══════════════════════════════════════════════════

    async def get_schedule_templates(self, group: str = None, term: str = None,
                                     educational_group: str = None, include_archived: bool = False) -> list:
        q = {}
        if group:
            q['group'] = self.normalize_group(group)
        raw_items = await self.schedule_templates.find(q).sort([('weekday', 1), ('time', 1)]).to_list(500)
        out = []
        for item in (raw_items or []):
            if not include_archived and item.get('archived'):
                continue
            if term and item.get('term') and str(item.get('term')).strip() != str(term).strip():
                continue
            if educational_group is not None:
                if not self.class_matches_user_educational_group(
                    item.get('educational_group'), educational_group
                ):
                    continue
            out.append(item)
        return out

    async def clear_schedule_templates(self, group: str = None, term: str = None) -> int:
        q = {}
        if group:
            q['group'] = self.normalize_group(group)
        if term:
            q['term'] = str(term).strip()
        r = await self.schedule_templates.delete_many(q)
        return int(getattr(r, 'deleted_count', 0) or 0)

    async def bulk_upsert_schedule_templates(self, items: list, term: str = None) -> dict:
        """Upsert weekly templates. Each item: weekday(0=Sat)..6, time HH:MM, end_time HH:MM?, lesson, teacher, location, group, educational_group, flex_type."""
        from time_utils import parse_clock_time, TimeContractError, en_digits
        import re as _re
        if not term:
            try:
                term = (await self.get_current_term_config())['term']
            except Exception:
                term = ''
        inserted = 0
        updated = 0
        skipped = 0
        # dedup within batch by (weekday,time,end_time,lesson,group,educational_group)
        seen_keys = set()
        for raw in (items or []):
            try:
                wd = int(raw.get('weekday'))
                if not 0 <= wd <= 6:
                    skipped += 1
                    continue
                t_raw = str(raw.get('time') or '').strip()
                et_raw = str(raw.get('end_time') or raw.get('time_end') or '').strip()
                # support legacy "08:00-10:00" in time field
                if t_raw and ("-" in t_raw or "تا" in t_raw) and not et_raw:
                    # parse range
                    tmp = en_digits(t_raw).replace('—','-').replace('–','-').replace('تا','-')
                    times = _re.findall(r'(\d{1,2}:\d{2})', tmp)
                    if len(times) >= 2:
                        t_raw = f"{int(times[0].split(':')[0]):02d}:{times[0].split(':')[1]}"
                        et_raw = f"{int(times[1].split(':')[0]):02d}:{times[1].split(':')[1]}"
                    elif '-' in tmp:
                        parts = tmp.split('-')
                        if len(parts)==2:
                            # handle "8-10"
                            m1 = _re.search(r'(\d{1,2})', parts[0])
                            m2 = _re.search(r'(\d{1,2})', parts[1])
                            if m1 and m2:
                                t_raw = f"{int(m1.group(1)):02d}:00"
                                et_raw = f"{int(m2.group(1)):02d}:00"
                # normalize AM/PM confusion: schedule never at 01:00-05:00 AM, so 01-05 means 13-17
                def _fix_pm(hhmm: str) -> str:
                    if not hhmm:
                        return hhmm
                    try:
                        hh = int(hhmm.split(':')[0])
                        mm = hhmm.split(':')[1]
                        if 1 <= hh <= 5:
                            hh += 12
                            return f"{hh:02d}:{mm}"
                        return hhmm
                    except Exception:
                        return hhmm
                t = _fix_pm(en_digits(t_raw).strip())
                et = _fix_pm(en_digits(et_raw).strip()) if et_raw else ""
                parse_clock_time(t)
                if et:
                    parse_clock_time(et)
                    st = parse_clock_time(t)
                    en = parse_clock_time(et)
                    if en.hour*60+en.minute <= st.hour*60+st.minute:
                        skipped += 1
                        continue
                else:
                    synth = {"08:00":"10:00","10:00":"12:00","13:00":"15:00","15:00":"17:00","17:00":"19:00"}
                    if t in synth:
                        et = synth[t]
                lesson = str(raw.get('lesson') or '').strip()
                if not lesson:
                    skipped += 1
                    continue
                group = self.normalize_group(raw.get('group') or 'هر دو') or 'هر دو'
                edu_group = self.normalize_class_educational_group(raw.get('educational_group'), default='mixed')
                item_term = str(raw.get('term') or term or '').strip()
                flex_type = str(raw.get('flex_type') or 'fixed').strip().lower()
                if flex_type not in ('fixed', 'flexible'):
                    flex_type = 'flexible' if 'عمل' in lesson or 'آز' in lesson else 'fixed'
                key = (wd, t, et, lesson, group, edu_group, item_term)
                if key in seen_keys:
                    skipped += 1
                    continue
                seen_keys.add(key)
                doc = {
                    'weekday': wd,
                    'time': t,
                    'end_time': et,
                    'lesson': lesson[:120],
                    'teacher': str(raw.get('teacher') or '').strip()[:80],
                    'location': str(raw.get('location') or '').strip()[:80],
                    'group': group,
                    'educational_group': edu_group,
                    'term': item_term,
                    'course_code': str(raw.get('course_code') or '').strip()[:40],
                    'type': str(raw.get('type') or 'class').strip() or 'class',
                    'flex_type': flex_type,
                    'notes': str(raw.get('notes') or raw.get('note') or '').strip()[:300],
                    'archived': False,
                    'updated_at': utc_now_iso(),
                }
                if raw.get('credit') is not None:
                    try:
                        doc['credit'] = max(0.5, min(10.0, float(raw.get('credit'))))
                    except (TypeError, ValueError):
                        pass
                existing = await self.schedule_templates.find_one({
                    'weekday': wd, 'time': t, 'lesson': doc['lesson'],
                    'group': group, 'educational_group': edu_group,
                })
                if not existing and edu_group == 'mixed':
                    existing = await self.schedule_templates.find_one({
                        'weekday': wd, 'time': t, 'lesson': doc['lesson'], 'group': group,
                    })
                if existing:
                    await self.schedule_templates.update_one({'_id': existing['_id']}, {'$set': doc})
                    updated += 1
                else:
                    doc['created_at'] = utc_now_iso()
                    await self.schedule_templates.insert_one(doc)
                    inserted += 1
            except (TimeContractError, ValueError, TypeError, AttributeError):
                skipped += 1
                continue
        return {'inserted': inserted, 'updated': updated, 'skipped': skipped, 'total': inserted + updated}

    async def generate_schedules_from_templates(self, start_date: str, end_date: str, group: str = None,
                                                dry_run: bool = False, term: str = None) -> dict:
        """Expand weekly templates into dated schedules for range inclusive."""
        from time_utils import parse_gregorian_date, parse_jalali_date, en_digits, TimeContractError
        if not term:
            try:
                term = (await self.get_current_term_config())['term']
            except Exception:
                term = ''
        def _to_date(s: str):
            raw = str(s or '').strip()
            if not raw:
                raise TimeContractError('empty date')
            normalized = ''.join(c for c in en_digits(raw) if c.isprintable()).strip().replace('/', '-').replace('\\', '-')
            try:
                y = int(normalized.split('-', 1)[0])
                if 1200 <= y <= 1600:
                    return parse_jalali_date(raw)
                return parse_gregorian_date(normalized)
            except Exception:
                raise TimeContractError(f'invalid date: {s}')
        try:
            start = _to_date(start_date)
            end = _to_date(end_date)
        except TimeContractError as e:
            return {'ok': False, 'error': str(e)}
        if end < start:
            return {'ok': False, 'error': 'end_before_start'}
        templates = await self.get_schedule_templates(group=group, term=term)
        if not templates:
            return {'ok': False, 'error': 'no_templates'}
        created = 0
        skipped = 0
        preview = []
        cur = start
        while cur <= end:
            wd = (cur.weekday() - 5) % 7  # 0=Sat
            day_str = cur.isoformat()
            for tpl in templates:
                if int(tpl.get('weekday')) != wd:
                    continue
                edu_group = self.normalize_class_educational_group(tpl.get('educational_group'), default='mixed')
                tpl_term = str(tpl.get('term') or term or '').strip()
                q_exist = {
                    'date': day_str,
                    'time': tpl.get('time'),
                    'lesson': tpl.get('lesson'),
                    'group': tpl.get('group'),
                    'type': tpl.get('type', 'class'),
                }
                if tpl.get('end_time'):
                    q_exist['end_time'] = tpl.get('end_time')
                exists = await self.schedules.find_one(q_exist)
                if not exists and tpl.get('end_time'):
                    alt = await self.schedules.find_one({
                        'date': day_str,
                        'time': tpl.get('time'),
                        'lesson': tpl.get('lesson'),
                        'group': tpl.get('group'),
                        'type': tpl.get('type', 'class'),
                    })
                    if alt:
                        exists = alt
                if exists and self.normalize_class_educational_group(exists.get('educational_group'), default='mixed') == edu_group:
                    skipped += 1
                    continue
                preview.append({
                    'date': day_str,
                    'weekday': wd,
                    'time': tpl.get('time'),
                    'end_time': tpl.get('end_time',''),
                    'lesson': tpl.get('lesson'),
                    'teacher': tpl.get('teacher', ''),
                    'location': tpl.get('location', ''),
                    'group': tpl.get('group'),
                    'educational_group': edu_group,
                    'term': tpl_term,
                    'type': tpl.get('type', 'class'),
                    'flex_type': tpl.get('flex_type', 'fixed'),
                })
                if not dry_run:
                    doc = {
                        'type': tpl.get('type', 'class'),
                        'lesson': tpl.get('lesson'),
                        'teacher': tpl.get('teacher', ''),
                        'date': day_str,
                        'time': tpl.get('time'),
                        'end_time': tpl.get('end_time',''),
                        'location': tpl.get('location', ''),
                        'notes': tpl.get('notes', ''),
                        'group': tpl.get('group'),
                        'educational_group': edu_group,
                        'term': tpl_term,
                        'course_code': str(tpl.get('course_code') or ''),
                        'from_template': True,
                        'archived': False,
                        'is_weekly': False,
                        'flex_type': tpl.get('flex_type', 'fixed'),
                        'flex_note': '',
                        'created_at': utc_now_iso(),
                        'notified_days': [],
                    }
                    if tpl.get('credit') is not None:
                        doc['credit'] = tpl.get('credit')
                    # keep time field clean (no range)
                    await self.schedules.insert_one(doc)
                    created += 1
            cur = cur + timedelta(days=1)
        return {'ok': True, 'created': created if not dry_run else 0, 'skipped': skipped, 'preview': preview[:50], 'total_matched': len(preview), 'dry_run': dry_run}

    async def upcoming_exams(self, days: int = 7, group: str = None):
        """Return near exams, optionally limited to a student's group.

        Empty/missing and ``هر دو`` group values are shared schedule entries and
        must remain visible to every student. ``group`` is optional so existing
        bot/admin callers keep their previous all-groups behaviour.
        """
        from utils import now_tehran
        today = now_tehran().strftime('%Y-%m-%d')
        future = (now_tehran() + timedelta(days=max(0, days))).strftime('%Y-%m-%d')
        query = {
            'type': 'exam',
            'date': {'$gte': today, '$lte': future},
        }
        normalized_group = self.normalize_group(group)
        if normalized_group:
            query['$or'] = [
                {'group': {'$in': self.group_aliases(normalized_group)}},
                {'group': 'هر دو'},
                {'group': 'هردو'},
                {'group': ''},
                {'group': None},
                {'group': {'$exists': False}},
            ]
        return await self.schedules.find(query).sort('date', 1).to_list(20)


    async def get_exams_for_reminder(self, remind_days: int):
        target = (today_tehran() + timedelta(days=remind_days)).isoformat()
        key    = f'd{remind_days}'
        return await self.schedules.find({
            'type': 'exam', 'date': target, 'notified_days': {'$ne': key},
        }).to_list(50)


    async def mark_exam_notified(self, sid: str, remind_days: int):
        key = f'd{remind_days}'
        try:
            await self.schedules.update_one(
                {'_id': ObjectId(sid)}, {'$addToSet': {'notified_days': key}}
            )
        except Exception: pass


    # ══════════════════════════════════════════════════
    #  🎓 سیستم انتخاب گروه درس‌به‌درس دانشجو (Per-Course Group Selection)
    # ══════════════════════════════════════════════════

    @classmethod
    def compute_majority_group(cls, selections: list, fallback_group: str = '1') -> dict:
        """محاسبه سبک و در لحظه‌ی گروه اکثریت دانشجو از روی انتخاب‌های درس‌به‌درس.

        قانون اکثریت و تساوی (Tie-breaker):
        ۱) شمارش تعداد درس‌های انتخابی در گروه ۱ و گروه ۲ (اگر یکی بیشتر بود، همان گروه اکثریت است).
        ۲) در صورت تساوی تعداد درس‌ها (مثلاً ۵ درس گروه ۱ و ۵ درس گروه ۲): مجموع واحدها (credit) مقایسه می‌شود.
        ۳) در صورت تساوی مجدد واحدها (یا عدم ثبت انتخاب واحد): گروه قبلی/ثبت‌نام دانشجو حفظ می‌شود.
        """
        norm_fallback = cls.normalize_group(fallback_group)
        if norm_fallback not in ('1', '2'):
            norm_fallback = '1'

        count_1 = 0
        count_2 = 0
        credits_1 = 0.0
        credits_2 = 0.0
        seen_lessons = set()

        for item in (selections or []):
            if not isinstance(item, dict):
                continue
            lesson = str(item.get('lesson') or '').strip()
            if not lesson or lesson in seen_lessons:
                continue
            grp = cls.normalize_group(item.get('group'))
            if grp not in ('1', '2'):
                continue
            seen_lessons.add(lesson)
            try:
                cred = float(item.get('credit') if item.get('credit') is not None else 1.0)
                if cred <= 0:
                    cred = 1.0
            except (TypeError, ValueError):
                cred = 1.0
            if grp == '1':
                count_1 += 1
                credits_1 += cred
            elif grp == '2':
                count_2 += 1
                credits_2 += cred

        total = count_1 + count_2
        if total == 0:
            return {
                'computed_group': norm_fallback,
                'count_1': 0,
                'count_2': 0,
                'credits_1': 0.0,
                'credits_2': 0.0,
                'group1_courses': 0,
                'group2_courses': 0,
                'group1_credits': 0.0,
                'group2_credits': 0.0,
                'total_selected': 0,
                'tie_broken_by': 'no_selection',
            }

        if count_1 > count_2:
            computed = '1'
            reason = 'course_count_majority'
        elif count_2 > count_1:
            computed = '2'
            reason = 'course_count_majority'
        else:
            # تساوی تعداد درس‌ها (مثلاً ۵ به ۵) → گام اول: مقایسه تعداد واحدها
            if round(credits_1, 2) > round(credits_2, 2):
                computed = '1'
                reason = 'credit_tiebreaker'
            elif round(credits_2, 2) > round(credits_1, 2):
                computed = '2'
                reason = 'credit_tiebreaker'
            else:
                # گام دوم تساوی: حفظ گروه قبلی/ثبت‌نام دانشجو
                computed = norm_fallback
                reason = 'fallback_tiebreaker'

        return {
            'computed_group': computed,
            'count_1': count_1,
            'count_2': count_2,
            'credits_1': round(credits_1, 2),
            'credits_2': round(credits_2, 2),
            'group1_courses': count_1,
            'group2_courses': count_2,
            'group1_credits': round(credits_1, 2),
            'group2_credits': round(credits_2, 2),
            'total_selected': total,
            'tie_broken_by': reason,
        }

    @staticmethod
    def _parse_hhmm_minutes(val: str) -> int | None:
        if not val:
            return None
        import re as _re
        from time_utils import en_digits as _en
        m = _re.search(r'(\d{1,2}):(\d{2})', _en(str(val)))
        if not m:
            return None
        hh, mm = int(m.group(1)), int(m.group(2))
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return hh * 60 + mm
        return None

    @classmethod
    def detect_schedule_conflicts(cls, items: list, active_term: str = None,
                                  user_educational_group: str = None) -> list:
        """تشخیص تداخل زمانی استاندارد بین دو درس مختلف در یک روز (یا یک روز هفته).

        قوانین قطعی برای جلوگیری از تداخل کاذب:
        ۱) رکوردهای آرشیوشده (archived=True) و رکوردهای متعلق به ترم‌های دیگر نادیده گرفته می‌شوند.
        ۲) ساعت امتحان (exam) کاملاً مستقل از ساعت کلاس هفتگی (class/makeup) است و هرگز با کلاس تداخل نمی‌خورد.
        ۳) کلاس مخصوص آقایان (male_only) هرگز با کلاس مخصوص بانوان (female_only) تداخل ندارد.
        ۴) اگر دو کلاس تاریخ مشخص (date) و متفاوت دارند (هفته‌های متفاوت)، با هم تداخل ندارند.
        ۵) فرمول استاندارد هم‌پوشانی بازه باز: start_a < end_b and start_b < end_a
           (بنابراین کلاس ۰۸:۰۰ تا ۱۰:۰۰ با کلاس ۱۰:۰۰ تا ۱۲:۰۰ هیچ تداخلی ندارد).
        """
        WEEKDAY_FA = ['شنبه', 'یکشنبه', 'دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنجشنبه', 'جمعه']
        normalized_rows = []
        for it in (items or []):
            if not isinstance(it, dict):
                continue
            if it.get('archived'):
                continue
            it_term = str(it.get('term') or it.get('academic_term') or '').strip()
            if active_term and it_term and it_term != str(active_term).strip():
                continue
            edu_grp = cls.normalize_class_educational_group(it.get('educational_group'), default='mixed')
            if user_educational_group and user_educational_group != 'unknown':
                if not cls.class_matches_user_educational_group(edu_grp, user_educational_group):
                    continue

            stype = str(it.get('type') or 'class').strip()
            if stype not in ('class', 'makeup', 'exam'):
                continue
            type_bucket = 'exam' if stype == 'exam' else 'class'
            lesson = str(it.get('lesson') or it.get('course_name') or '').strip()
            if not lesson:
                continue
            start_str = str(it.get('time') or it.get('start_time') or '').strip()
            end_str = str(it.get('end_time') or it.get('time_end') or '').strip()
            if start_str and ('-' in start_str or 'تا' in start_str) and not end_str:
                parts = start_str.replace('تا', '-').split('-', 1)
                start_str = parts[0].strip()
                end_str = parts[1].strip() if len(parts) > 1 else ''
            st_min = cls._parse_hhmm_minutes(start_str)
            if st_min is None:
                continue
            en_min = cls._parse_hhmm_minutes(end_str)
            if en_min is None or en_min <= st_min:
                en_min = st_min + 120  # پیش‌فرض ۲ ساعت برای کلاس دانشگاهی

            date_str = str(it.get('date') or '').strip()
            wd = it.get('weekday')
            if wd is not None and str(wd).strip() != '':
                try:
                    wd = int(wd)
                except (TypeError, ValueError):
                    wd = None
            elif date_str:
                try:
                    from time_utils import parse_gregorian_date
                    dt_obj = parse_gregorian_date(date_str)
                    wd = (dt_obj.weekday() - 5) % 7
                except Exception:
                    wd = None

            day_label = ''
            if date_str:
                day_label = format_date_fa(date_str, date_only=True, weekday=True, fallback=date_str)
            elif wd is not None and 0 <= wd < 7:
                day_label = WEEKDAY_FA[wd]
            else:
                continue

            normalized_rows.append({
                'lesson': lesson,
                'course_code': str(it.get('course_code') or '').strip(),
                'group': cls.normalize_group(it.get('group') or it.get('group_code')) or 'هر دو',
                'educational_group': edu_grp,
                'term': it_term,
                'teacher': str(it.get('teacher') or it.get('instructor_name') or '').strip(),
                'day_label': day_label,
                'date': date_str,
                'weekday': wd,
                'start_min': st_min,
                'end_min': en_min,
                'time_label': f"{start_str[:5]}" + (f" تا {end_str[:5]}" if end_str else ""),
                'type': stype,
                'type_bucket': type_bucket,
            })

        conflicts = []
        seen_pairs = set()
        n = len(normalized_rows)
        for i in range(n):
            a = normalized_rows[i]
            for j in range(i + 1, n):
                b = normalized_rows[j]
                # ۱) نوع یکسان (کلاس با امتحان هرگز مقایسه نمی‌شود)
                if a['type_bucket'] != b['type_bucket']:
                    continue
                # ۲) ترم یکسان (اگر هر دو ترم صریح دارند)
                if a['term'] and b['term'] and a['term'] != b['term']:
                    continue
                # ۳) عدم تداخل بین گروه آقایان و گروه بانوان
                if (a['educational_group'] == 'male_only' and b['educational_group'] == 'female_only') or (
                    a['educational_group'] == 'female_only' and b['educational_group'] == 'male_only'
                ):
                    continue
                # ۴) یک درس با خودش تداخل حساب نشود
                if a['lesson'] == b['lesson'] and (not a['course_code'] or not b['course_code'] or a['course_code'] == b['course_code']):
                    continue
                # ۵) بررسی تطابق روز / تاریخ:
                if a['type_bucket'] == 'exam':
                    if not a['date'] or a['date'] != b['date']:
                        continue
                else:
                    # برای کلاس‌ها: اگر هر دو تاریخ مشخص دارند، باید در یک تاریخ باشند
                    if a['date'] and b['date']:
                        if a['date'] != b['date']:
                            continue
                    else:
                        if a['weekday'] is None or b['weekday'] is None or a['weekday'] != b['weekday']:
                            continue

                # ۶) فرمول استاندارد هم‌پوشانی: start_a < end_b and start_b < end_a
                if a['start_min'] < b['end_min'] and b['start_min'] < a['end_min']:
                    pair_lessons = tuple(sorted([a['lesson'], b['lesson']]))
                    day_id = a['weekday'] if a['weekday'] is not None else a['date']
                    dedup_key = (a['type_bucket'], pair_lessons, day_id, min(a['start_min'], b['start_min']), max(a['start_min'], b['start_min']))
                    if dedup_key in seen_pairs:
                        continue
                    seen_pairs.add(dedup_key)
                    lbl_day = WEEKDAY_FA[a['weekday']] if (a['weekday'] is not None and 0 <= a['weekday'] < 7 and a['type_bucket'] == 'class' and (not a['date'] or not b['date'])) else a['day_label']
                    conflicts.append({
                        'lesson_a': a['lesson'],
                        'group_a': a['group'],
                        'educational_group_a': a['educational_group'],
                        'time_a': a['time_label'],
                        'lesson_b': b['lesson'],
                        'group_b': b['group'],
                        'educational_group_b': b['educational_group'],
                        'time_b': b['time_label'],
                        'day_label': lbl_day,
                        'date': a['date'] if a['date'] == b['date'] else '',
                        'type': a['type_bucket'],
                        'message': (
                            f"تداخل زمانی در {lbl_day}: درس «{a['lesson']}» "
                            f"(گروه {a['group']}، ساعت {a['time_label']}) با درس «{b['lesson']}» "
                            f"(گروه {b['group']}، ساعت {b['time_label']}) هم‌زمان است."
                        ),
                    })
        return conflicts

    async def get_current_term_config(self) -> dict:
        """دریافت تنظیمات ترم جاری (نام ترم، تاریخ پایان امتحانات، وضعیت یادآوری انتخاب واحد)."""
        from time_utils import gregorian_to_jalali, today_tehran
        saved_term = str(await self.get_setting('current_academic_term', '') or '').strip()
        if not saved_term:
            try:
                t_d = today_tehran()
                j_d = gregorian_to_jalali(t_d.year, t_d.month, t_d.day)
                jy, jm = int(j_d.year), int(j_d.month)
                half = 1 if jm <= 6 else 2
                saved_term = f"{jy}-{half}"
            except Exception:
                saved_term = "1405-1"

        exams_end_date = str(await self.get_setting('term_exams_end_date', '') or '').strip()
        auto_detected_end = ''
        if not exams_end_date:
            try:
                last_exam = await self.schedules.find(
                    {'type': 'exam'}
                ).sort('date', -1).limit(1).to_list(1)
                if last_exam and last_exam[0].get('date'):
                    auto_detected_end = str(last_exam[0]['date']).strip()
            except Exception:
                pass

        second_reminder = bool(await self.get_setting('course_selection_reminder_second_enabled', False))
        try:
            second_days = max(1, min(30, int(await self.get_setting('course_selection_reminder_second_days', 3) or 3)))
        except (TypeError, ValueError):
            second_days = 3

        effective_end = exams_end_date or auto_detected_end
        return {
            'term': saved_term,
            'exams_end_date': exams_end_date,
            'auto_detected_exams_end_date': auto_detected_end,
            'effective_exams_end_date': effective_end,
            'effective_exams_end_date_fa': format_date_fa(effective_end, date_only=True, fallback=effective_end) if effective_end else '',
            'second_reminder_enabled': second_reminder,
            'second_reminder_days': second_days,
        }

    async def set_current_term_config(
        self,
        term: str = None,
        exams_end_date: str = None,
        second_reminder_enabled: bool = None,
        second_reminder_days: int = None,
        archive_previous: bool = True,
    ) -> dict:
        """ذخیره تنظیمات ترم جاری توسط ادمین + آرشیو خودکار انتخاب واحدهای ترم‌های قبل در صورت تغییر ترم."""
        from time_utils import parse_gregorian_date, parse_jalali_date, en_digits
        cur_cfg = await self.get_current_term_config()
        old_term = cur_cfg['term']
        new_term = str(term).strip() if term is not None and str(term).strip() else old_term

        if term is not None and str(term).strip():
            await self.set_setting('current_academic_term', new_term)

        if exams_end_date is not None:
            raw_d = en_digits(str(exams_end_date).strip())
            if not raw_d:
                await self.set_setting('term_exams_end_date', '')
            else:
                norm_d = raw_d.replace('/', '-')
                parts = norm_d.split('-')
                if len(parts) == 3 and 1300 <= int(parts[0]) <= 1500:
                    g_date = parse_jalali_date(raw_d)
                    await self.set_setting('term_exams_end_date', g_date.isoformat())
                else:
                    g_date = parse_gregorian_date(norm_d)
                    await self.set_setting('term_exams_end_date', g_date.isoformat())

        if second_reminder_enabled is not None:
            await self.set_setting('course_selection_reminder_second_enabled', bool(second_reminder_enabled))

        if second_reminder_days is not None:
            await self.set_setting('course_selection_reminder_second_days', max(1, min(30, int(second_reminder_days))))

        archived_count = 0
        if archive_previous and new_term != old_term:
            archived_count = await self.archive_previous_term_selections(new_term)

        updated = await self.get_current_term_config()
        updated['archived_previous_selections'] = archived_count
        return updated

    async def archive_previous_term_selections(self, active_term: str) -> int:
        """آرشیو کردن انتخاب‌های ترم‌های قبل بدون پاک کردن تاریخچه."""
        if not active_term:
            return 0
        try:
            r = await self.course_selections.update_many(
                {'term': {'$ne': active_term}, 'archived': {'$ne': True}},
                {'$set': {'archived': True, 'archived_at': utc_now_iso()}},
            )
            return int(getattr(r, 'modified_count', 0) or 0)
        except Exception:
            logger.exception('archive_previous_term_selections failed')
            return 0

    async def upsert_course_offering(
        self,
        lesson: str,
        group: str,
        teacher: str = '',
        credit: float = 1.0,
        term: str = None,
        schedule_summary: str = '',
        weekday: int = None,
        time: str = '',
        end_time: str = '',
        location: str = '',
        educational_group: str = 'mixed',
        course_code: str = '',
        class_code: str = '',
        exam_date: str = '',
        exam_time: str = '',
        source_image: str = '',
        extraction_confidence: float = None,
    ) -> dict:
        """ثبت یا ویرایش یک گروه ارائه‌شده برای یک درس در ترم جاری با پشتیبانی کامل از کد درس و گروه آموزشی (آقایان/بانوان/مشترک)."""
        if not term:
            term = (await self.get_current_term_config())['term']
        lesson = str(lesson or '').strip()[:120]
        if not lesson:
            raise ValueError('lesson_required')
        norm_group = self.normalize_group(group) or 'هر دو'
        if norm_group not in ('1', '2', '3', '4', 'هر دو'):
            norm_group = 'هر دو'
        edu_grp = self.normalize_class_educational_group(educational_group, default='mixed')
        try:
            cred = max(0.5, min(10.0, float(credit if credit is not None else 1.0)))
        except (TypeError, ValueError):
            cred = 1.0
        doc = {
            'term': term,
            'lesson': lesson,
            'course_code': str(course_code or '').strip()[:40],
            'class_code': str(class_code or '').strip()[:40],
            'group': norm_group,
            'educational_group': edu_grp,
            'teacher': str(teacher or '').strip()[:100],
            'credit': cred,
            'schedule_summary': str(schedule_summary or '').strip()[:200],
            'weekday': int(weekday) if weekday is not None and str(weekday).strip() != '' else None,
            'time': str(time or '').strip()[:10],
            'end_time': str(end_time or '').strip()[:10],
            'exam_date': str(exam_date or '').strip()[:20],
            'exam_time': str(exam_time or '').strip()[:10],
            'location': str(location or '').strip()[:100],
            'archived': False,
            'updated_at': utc_now_iso(),
        }
        if source_image:
            doc['source_image'] = str(source_image).strip()[:120]
        if extraction_confidence is not None:
            try:
                doc['extraction_confidence'] = round(float(extraction_confidence), 2)
            except (TypeError, ValueError):
                pass
        existing = await self.course_offerings.find_one({
            'term': term, 'lesson': lesson, 'group': norm_group, 'educational_group': edu_grp,
        })
        if not existing and edu_grp == 'mixed':
            cand = await self.course_offerings.find_one({'term': term, 'lesson': lesson, 'group': norm_group})
            if cand and self.normalize_class_educational_group(cand.get('educational_group'), default='mixed') == 'mixed':
                existing = cand
        if existing:
            await self.course_offerings.update_one({'_id': existing['_id']}, {'$set': doc})
        else:
            await self.course_offerings.update_one(
                {'term': term, 'lesson': lesson, 'group': norm_group, 'educational_group': edu_grp},
                {'$set': doc, '$setOnInsert': {'created_at': utc_now_iso()}},
                upsert=True,
            )
        return doc

    async def delete_course_offering(self, lesson: str, group: str = None, term: str = None,
                                     educational_group: str = None) -> int:
        raw_id = str(lesson or '').strip()
        if not group and len(raw_id) == 24:
            try:
                r = await self.course_offerings.delete_one({'_id': ObjectId(raw_id)})
                if int(getattr(r, 'deleted_count', 0) or 0) > 0:
                    return int(r.deleted_count)
            except Exception:
                pass
        if not term:
            term = (await self.get_current_term_config())['term']
        q = {'term': term, 'lesson': raw_id}
        if group:
            q['group'] = self.normalize_group(group)
        if educational_group:
            q['educational_group'] = self.normalize_class_educational_group(educational_group)
        r = await self.course_offerings.delete_many(q)
        return int(getattr(r, 'deleted_count', 0) or 0)

    async def get_term_course_offerings(self, term: str = None, educational_group: str = None,
                                        include_all_educational_groups: bool = False) -> list:
        """استخراج فهرست یکپارچه درس‌های ارائه‌شده در ترم جاری به تفکیک گروه‌ها، اساتید و گروه آموزشی (آقایان/بانوان/مشترک).

        منابع تجمیع:
        ۱) جدول course_offerings (ثبت مستقیم یا منتشرشده از Staging Vision)
        ۲) الگوهای هفتگی (schedule_templates)
        ۳) برنامه‌های کلاسی ثبت‌شده در جدول schedules (فقط در صورتی که برای آن درس الگوی هفتگی یا offering صریح وجود نداشته باشد تا جابه‌جایی‌های تک‌جلسه‌ای باعث تداخل کاذب نشوند)
        """
        WEEKDAY_FA = ['شنبه', 'یکشنبه', 'دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنجشنبه', 'جمعه']
        if not term:
            term = (await self.get_current_term_config())['term']

        from utils import now_tehran
        today_str = now_tehran().strftime('%Y-%m-%d')

        explicit_docs, tpl_docs, sched_docs = await asyncio.gather(
            self.course_offerings.find({'term': term}).to_list(500),
            self.schedule_templates.find({}).sort([('weekday', 1), ('time', 1)]).to_list(500),
            self.schedules.find({'type': 'class', 'date': {'$gte': today_str}}).sort('date', 1).to_list(500),
        )
        if not explicit_docs and not tpl_docs and not sched_docs:
            sched_docs = await self.schedules.find({'type': 'class'}).sort('date', -1).limit(200).to_list(200)

        def _doc_matches_scope(d: dict) -> bool:
            if d.get('archived'):
                return False
            d_term = str(d.get('term') or '').strip()
            if d_term and d_term != str(term).strip():
                return False
            if include_all_educational_groups or educational_group is None:
                return True
            return self.class_matches_user_educational_group(d.get('educational_group'), educational_group)

        explicit_docs = [d for d in (explicit_docs or []) if _doc_matches_scope(d)]
        tpl_docs = [d for d in (tpl_docs or []) if _doc_matches_scope(d)]
        sched_docs = [d for d in (sched_docs or []) if _doc_matches_scope(d)]

        courses_map: dict[str, dict] = {}

        def _ensure_course(lesson_name: str) -> dict:
            if lesson_name not in courses_map:
                courses_map[lesson_name] = {
                    'lesson': lesson_name,
                    'course_code': '',
                    'credit': 1.0,
                    'educational_groups': set(),
                    'groups_data': {
                        '1': {'group': '1', 'teachers': [], 'sessions': [], 'explicit': False, 'educational_group': 'mixed', 'course_code': '', 'exam_date': '', 'exam_time': ''},
                        '2': {'group': '2', 'teachers': [], 'sessions': [], 'explicit': False, 'educational_group': 'mixed', 'course_code': '', 'exam_date': '', 'exam_time': ''},
                    },
                    'seen_groups': set(),
                    'has_shared': False,
                    'has_explicit_or_tpl': False,
                }
            return courses_map[lesson_name]

        def _add_entry(
            lesson_name: str,
            grp_raw: str,
            teacher: str,
            credit_val,
            session_info: dict = None,
            is_explicit: bool = False,
            from_template: bool = False,
            edu_grp_raw: str = 'mixed',
            course_code: str = '',
            exam_date: str = '',
            exam_time: str = '',
        ):
            lesson_name = str(lesson_name or '').strip()
            if not lesson_name:
                return
            c = _ensure_course(lesson_name)
            if is_explicit or from_template:
                c['has_explicit_or_tpl'] = True
            if course_code and not c['course_code']:
                c['course_code'] = str(course_code).strip()
            edu_grp = self.normalize_class_educational_group(edu_grp_raw, default='mixed')
            c['educational_groups'].add(edu_grp)
            if credit_val is not None:
                try:
                    cf = float(credit_val)
                    if cf > 0:
                        c['credit'] = cf
                except (TypeError, ValueError):
                    pass
            norm_g = self.normalize_group(grp_raw) or 'هر دو'
            if norm_g in ('1', '2', '3', '4'):
                if norm_g not in c['groups_data']:
                    c['groups_data'][norm_g] = {
                        'group': norm_g, 'teachers': [], 'sessions': [],
                        'explicit': False, 'educational_group': edu_grp,
                        'course_code': str(course_code or '').strip(),
                        'exam_date': str(exam_date or '').strip(),
                        'exam_time': str(exam_time or '').strip(),
                    }
                target_groups = [norm_g]
                c['seen_groups'].add(norm_g)
            else:
                target_groups = ['1', '2']
                c['has_shared'] = True

            for g in target_groups:
                gd = c['groups_data'][g]
                if is_explicit and norm_g in ('1', '2', '3', '4'):
                    gd['explicit'] = True
                    gd['educational_group'] = edu_grp
                    if course_code:
                        gd['course_code'] = str(course_code).strip()
                    if exam_date:
                        gd['exam_date'] = str(exam_date).strip()
                    if exam_time:
                        gd['exam_time'] = str(exam_time).strip()
                elif gd.get('educational_group') == 'mixed' and edu_grp in ('male_only', 'female_only'):
                    gd['educational_group'] = edu_grp
                t_clean = str(teacher or '').strip()
                if t_clean and t_clean not in gd['teachers']:
                    if is_explicit and norm_g in ('1', '2', '3', '4'):
                        gd['teachers'].insert(0, t_clean)
                    else:
                        gd['teachers'].append(t_clean)
                if session_info:
                    sig = (session_info.get('day_label'), session_info.get('time'), session_info.get('end_time'))
                    if not any((s.get('day_label'), s.get('time'), s.get('end_time')) == sig for s in gd['sessions']):
                        gd['sessions'].append(session_info)

        # ۱) ابتدا رکوردهای صریح course_offerings
        for doc in (explicit_docs or []):
            wd = doc.get('weekday')
            day_lbl = WEEKDAY_FA[int(wd)] if wd is not None and 0 <= int(wd) < 7 else ''
            s_info = None
            if day_lbl or doc.get('time') or doc.get('schedule_summary'):
                s_info = {
                    'weekday': int(wd) if wd is not None else None,
                    'day_label': day_lbl or str(doc.get('schedule_summary') or ''),
                    'time': str(doc.get('time') or ''),
                    'end_time': str(doc.get('end_time') or ''),
                    'location': str(doc.get('location') or ''),
                    'educational_group': self.normalize_class_educational_group(doc.get('educational_group'), default='mixed'),
                    'term': term,
                }
            _add_entry(
                doc.get('lesson'),
                doc.get('group'),
                doc.get('teacher', ''),
                doc.get('credit'),
                s_info,
                is_explicit=True,
                edu_grp_raw=doc.get('educational_group', 'mixed'),
                course_code=doc.get('course_code', ''),
                exam_date=doc.get('exam_date', ''),
                exam_time=doc.get('exam_time', ''),
            )

        # ۲) الگوهای هفتگی (schedule_templates)
        for tpl in (tpl_docs or []):
            wd = tpl.get('weekday')
            day_lbl = WEEKDAY_FA[int(wd)] if wd is not None and 0 <= int(wd) < 7 else ''
            s_info = {
                'weekday': int(wd) if wd is not None else None,
                'day_label': day_lbl,
                'time': str(tpl.get('time') or ''),
                'end_time': str(tpl.get('end_time') or ''),
                'location': str(tpl.get('location') or ''),
                'educational_group': self.normalize_class_educational_group(tpl.get('educational_group'), default='mixed'),
                'term': term,
            }
            _add_entry(
                tpl.get('lesson'),
                tpl.get('group'),
                tpl.get('teacher', ''),
                tpl.get('credit'),
                s_info,
                from_template=True,
                edu_grp_raw=tpl.get('educational_group', 'mixed'),
                course_code=tpl.get('course_code', ''),
            )

        # ۳) برنامه‌های کلاسی (schedules) — فقط برای درس‌هایی که در course_offerings یا schedule_templates الگوی هفتگی ندارند
        # تا جابه‌جایی تک‌جلسه‌ای یک تاریخ خاص به عنوان دو کلاس هفتگی هم‌زمان تلقی نشود (رفع ریشه‌ای تداخل کاذب بخش ۴)
        seen_sched_wd = set()
        for sch in (sched_docs or []):
            lsn_name = str(sch.get('lesson') or '').strip()
            if not lsn_name:
                continue
            existing_c = courses_map.get(lsn_name)
            if existing_c and existing_c.get('has_explicit_or_tpl'):
                # اگر درس از قبل الگوی هفتگی دارد، فقط در صورتی که گروه جدیدی در schedules دیده شده اضافه کن
                norm_sg = self.normalize_group(sch.get('group')) or 'هر دو'
                if norm_sg in existing_c['seen_groups'] or norm_sg == 'هر دو':
                    continue
            d_str = str(sch.get('date') or '')
            day_lbl = ''
            wd = None
            if d_str:
                try:
                    from time_utils import parse_gregorian_date
                    dt_obj = parse_gregorian_date(d_str)
                    wd = (dt_obj.weekday() - 5) % 7
                    day_lbl = WEEKDAY_FA[wd]
                except Exception:
                    day_lbl = d_str
            dedup_wd_key = (lsn_name, self.normalize_group(sch.get('group')) or 'هر دو', wd)
            if wd is not None and dedup_wd_key in seen_sched_wd:
                continue
            if wd is not None:
                seen_sched_wd.add(dedup_wd_key)
            s_info = {
                'weekday': wd,
                'date': d_str,
                'day_label': day_lbl,
                'time': str(sch.get('time') or ''),
                'end_time': str(sch.get('end_time') or ''),
                'location': str(sch.get('location') or ''),
                'educational_group': self.normalize_class_educational_group(sch.get('educational_group'), default='mixed'),
                'term': term,
            }
            _add_entry(
                lsn_name,
                sch.get('group'),
                sch.get('teacher', ''),
                sch.get('credit'),
                s_info,
                edu_grp_raw=sch.get('educational_group', 'mixed'),
                course_code=sch.get('course_code', ''),
            )

        out = []
        for lesson_name in sorted(courses_map.keys()):
            c = courses_map[lesson_name]
            seen = sorted(c['seen_groups'])
            # اگر درسی فقط به صورت مشترک «هر دو» ثبت شده و هیچ تفکیک گروه ۱ و ۲ ندارد، نیاز به انتخاب گروه ۱/۲ ندارد
            if len(seen) == 0 and c['has_shared']:
                continue
            if len(seen) == 1 and not c['has_shared']:
                only_g = seen[0]
                active_groups = [only_g]
                single_group = True
                auto_group = only_g
            elif len(seen) > 1:
                active_groups = seen
                single_group = False
                auto_group = None
            else:
                active_groups = ['1', '2']
                single_group = False
                auto_group = None

            groups_list = []
            for g in active_groups:
                gd = c['groups_data'].get(g) or {'group': g, 'teachers': [], 'sessions': [], 'educational_group': 'mixed'}
                teacher_str = '، '.join(gd['teachers'][:2]) if gd['teachers'] else ''
                summary_parts = []
                for s in gd['sessions'][:2]:
                    t_part = s.get('time') or ''
                    if s.get('end_time'):
                        t_part = f"{t_part} تا {s['end_time']}"
                    dl = s.get('day_label') or ''
                    if dl and t_part:
                        summary_parts.append(f"{dl} {t_part}")
                    elif dl or t_part:
                        summary_parts.append(dl or t_part)
                sched_summary = ' · '.join(summary_parts)
                edu_g = gd.get('educational_group') or 'mixed'
                edu_badge = ''
                if include_all_educational_groups:
                    if edu_g == 'male_only':
                        edu_badge = ' (آقایان)'
                    elif edu_g == 'female_only':
                        edu_badge = ' (بانوان)'
                label = f"گروه {g}{edu_badge}" + (f" – {teacher_str}" if teacher_str else "")
                groups_list.append({
                    'group': g,
                    'educational_group': edu_g,
                    'course_code': gd.get('course_code') or c.get('course_code') or '',
                    'exam_date': gd.get('exam_date') or '',
                    'exam_time': gd.get('exam_time') or '',
                    'teacher': teacher_str,
                    'label': label,
                    'schedule_summary': sched_summary,
                    'sessions': gd['sessions'][:4],
                })

            edu_set = c['educational_groups']
            course_edu = next(iter(edu_set)) if len(edu_set) == 1 else 'mixed'
            out.append({
                'lesson': lesson_name,
                'course_code': c.get('course_code') or '',
                'credit': c['credit'],
                'educational_group': course_edu,
                'single_group': single_group,
                'auto_selected_group': auto_group,
                'groups': groups_list,
            })
        return out

    async def flag_mismatched_student_selections(self, uid: int, new_educational_group: str, term: str = None) -> int:
        """بررسی انتخاب واحدهای قبلی دانشجو پس از تغییر گروه آموزشی (بدون حذف خودکار!).
        هر انتخاب قبلی که مخصوص گروه آموزشی مقابل باشد با educational_group_mismatch=True علامت‌گذاری می‌شود."""
        uid = int(uid)
        if not term:
            term = (await self.get_current_term_config())['term']
        ug = self.normalize_user_educational_group(new_educational_group)
        if ug not in ('male', 'female'):
            return 0
        docs = await self.course_selections.find({
            'user_id': uid, 'term': term, 'archived': {'$ne': True},
        }).to_list(200)
        if not docs:
            return 0
        all_offerings = await self.course_offerings.find({'term': term}).to_list(500)
        flagged = 0
        for sel in docs:
            lsn = str(sel.get('lesson') or '').strip()
            grp = self.normalize_group(sel.get('group'))
            matching_offs = [
                o for o in (all_offerings or [])
                if str(o.get('lesson') or '').strip() == lsn and self.normalize_group(o.get('group')) == grp and not o.get('archived')
            ]
            mismatch = False
            if matching_offs:
                # اگر تمام رکوردهای این درس+گروه در دیتابیس مخصوص جنس مخالف باشد، مغایرت دارد
                if all(not self.class_matches_user_educational_group(o.get('educational_group'), ug) for o in matching_offs):
                    mismatch = True
            sel_filt = {'_id': sel['_id']} if '_id' in sel else {'user_id': uid, 'term': term, 'lesson': lsn}
            await self.course_selections.update_one(
                sel_filt,
                {'$set': {
                    'educational_group_mismatch': mismatch,
                    'mismatch_reason': 'گروه درسی انتخابی با گروه آموزشی جدید شما مغایرت دارد و نیازمند بررسی است.' if mismatch else '',
                }},
            )
            if mismatch:
                flagged += 1
        return flagged

    async def get_student_course_selections(self, uid: int, term: str = None) -> dict:
        """دریافت انتخاب واحدهای فعلی دانشجو در ترم جاری + کاتالوگ درس‌ها (فیلترشده با گروه آموزشی دانشجو) + گروه اکثریت."""
        uid = int(uid)
        term_cfg = await self.get_current_term_config()
        active_term = term or term_cfg['term']
        user = await self.get_user(uid, use_cache=False) or {}
        edu_info = self.extract_user_educational_group_info(user)
        user_edu = edu_info['educational_group']  # 'male' | 'female' | 'unknown'

        registered_group = self.normalize_group(user.get('registered_group') or user.get('group') or '1')
        if registered_group not in ('1', '2'):
            registered_group = '1'
        computed_group = self.normalize_group(user.get('computed_group') or user.get('group') or registered_group)
        if computed_group not in ('1', '2'):
            computed_group = registered_group

        all_offerings, filtered_offerings, docs = await asyncio.gather(
            self.get_term_course_offerings(active_term, include_all_educational_groups=True),
            self.get_term_course_offerings(active_term, educational_group=(user_edu if user_edu != 'unknown' else 'unknown')),
            self.course_selections.find({
                'user_id': uid,
                'term': active_term,
                'archived': {'$ne': True},
            }).sort('lesson', 1).to_list(200),
        )

        has_gender_specific_catalog = any(
            o.get('educational_group') in ('male_only', 'female_only')
            or any(g.get('educational_group') in ('male_only', 'female_only') for g in (o.get('groups') or []))
            for o in (all_offerings or [])
        )
        offerings = filtered_offerings if user_edu in ('male', 'female') else (
            filtered_offerings if has_gender_specific_catalog else all_offerings
        )

        # نقشه انتخاب‌های ذخیره‌شده
        saved_map = {}
        mismatched_selections = []
        for d in (docs or []):
            lsn = str(d.get('lesson') or '').strip()
            grp = self.normalize_group(d.get('group'))
            if lsn and grp in ('1', '2', '3', '4'):
                mismatch = bool(d.get('educational_group_mismatch'))
                row_obj = {
                    'lesson': lsn,
                    'course_code': str(d.get('course_code') or ''),
                    'group': grp,
                    'educational_group': str(d.get('educational_group') or 'mixed'),
                    'teacher': str(d.get('teacher') or ''),
                    'credit': float(d.get('credit') if d.get('credit') is not None else 1.0),
                    'educational_group_mismatch': mismatch,
                    'mismatch_reason': str(d.get('mismatch_reason') or ''),
                    'updated_at': d.get('updated_at'),
                }
                saved_map[lsn] = row_obj
                if mismatch:
                    mismatched_selections.append(row_obj)

        majority = self.compute_majority_group(list(saved_map.values()), fallback_group=registered_group)
        return {
            'term': active_term,
            'term_config': term_cfg,
            'has_selections': len(saved_map) > 0,
            'selections': list(saved_map.values()),
            'selections_map': {k: v['group'] for k, v in saved_map.items()},
            'mismatched_selections': mismatched_selections,
            'has_educational_group_mismatch': len(mismatched_selections) > 0,
            'offerings': offerings,
            'computed_group': majority['computed_group'] if saved_map else computed_group,
            'registered_group': registered_group,
            'majority': majority,
            'educational_group_info': edu_info,
            'educational_group': user_edu,
            'needs_educational_group_confirmation': bool(edu_info['needs_confirmation']),
            'has_gender_specific_catalog': has_gender_specific_catalog,
        }

    async def save_student_course_selections(self, uid: int, selections: list, term: str = None) -> dict:
        """ذخیره انتخاب واحد درس‌به‌درس دانشجو + اعمال فیلتر مرکزی گروه آموزشی + محاسبه خودکار گروه اکثریت."""
        uid = int(uid)
        term_cfg = await self.get_current_term_config()
        active_term = term or term_cfg['term']
        user = await self.get_user(uid, use_cache=False) or {}
        edu_info = self.extract_user_educational_group_info(user)
        user_edu = edu_info['educational_group']

        registered_group = self.normalize_group(user.get('registered_group') or user.get('group') or '1')
        if registered_group not in ('1', '2'):
            registered_group = '1'

        offerings = await self.get_term_course_offerings(
            active_term,
            educational_group=(user_edu if user_edu in ('male', 'female') else None),
        )
        offering_map = {o['lesson']: o for o in offerings}

        now_iso = utc_now_iso()
        clean_selections = []
        seen_lessons = set()

        incoming_map = {}
        for item in (selections or []):
            if not isinstance(item, dict):
                continue
            lsn = str(item.get('lesson') or '').strip()[:120]
            grp = self.normalize_group(item.get('group'))
            if lsn and grp in ('1', '2', '3', '4'):
                incoming_map[lsn] = (grp, item)

        for o in offerings:
            if o.get('single_group') and o.get('auto_selected_group') in ('1', '2', '3', '4'):
                lsn = o['lesson']
                if lsn not in incoming_map and incoming_map:
                    incoming_map[lsn] = (o['auto_selected_group'], {'lesson': lsn, 'group': o['auto_selected_group']})

        for lsn, (grp, raw_item) in incoming_map.items():
            if lsn in seen_lessons:
                continue
            seen_lessons.add(lsn)
            off = offering_map.get(lsn) or {}
            try:
                cred = float(raw_item.get('credit') if raw_item.get('credit') is not None else (off.get('credit') or 1.0))
                if cred <= 0:
                    cred = 1.0
            except (TypeError, ValueError):
                cred = 1.0
            teacher = str(raw_item.get('teacher') or '').strip()
            edu_grp_sel = 'mixed'
            course_code = str(raw_item.get('course_code') or off.get('course_code') or '').strip()
            if off.get('groups'):
                for g_obj in off['groups']:
                    if g_obj.get('group') == grp:
                        if not teacher and g_obj.get('teacher'):
                            teacher = g_obj['teacher']
                        edu_grp_sel = g_obj.get('educational_group') or off.get('educational_group') or 'mixed'
                        if not course_code and g_obj.get('course_code'):
                            course_code = g_obj['course_code']
                        break
            doc = {
                'user_id': uid,
                'term': active_term,
                'lesson': lsn,
                'course_code': course_code,
                'group': grp,
                'educational_group': edu_grp_sel,
                'educational_group_mismatch': False,
                'mismatch_reason': '',
                'teacher': teacher[:100],
                'credit': cred,
                'offering_id': f"{active_term}::{lsn}::{grp}::{edu_grp_sel}",
                'archived': False,
                'updated_at': now_iso,
            }
            await self.course_selections.update_one(
                {'user_id': uid, 'term': active_term, 'lesson': lsn},
                {'$set': doc, '$setOnInsert': {'created_at': now_iso}},
                upsert=True,
            )
            clean_selections.append(doc)

        if clean_selections:
            await self.course_selections.delete_many({
                'user_id': uid,
                'term': active_term,
                'archived': {'$ne': True},
                'lesson': {'$nin': [x['lesson'] for x in clean_selections]},
            })
        else:
            await self.course_selections.delete_many({
                'user_id': uid,
                'term': active_term,
                'archived': {'$ne': True},
            })

        majority = self.compute_majority_group(clean_selections, fallback_group=registered_group)
        new_group = majority['computed_group']

        await self.update_user(uid, {
            'registered_group': registered_group,
            'computed_group': new_group,
            'group': new_group,
            'course_selection_term': active_term,
            'course_selection_count': len(clean_selections),
            'course_selection_updated_at': now_iso,
        })

        session_rows_for_conflict = []
        for sel in clean_selections:
            off = offering_map.get(sel['lesson'])
            if not off:
                continue
            for g_obj in (off.get('groups') or []):
                if g_obj.get('group') == sel['group']:
                    for sess in (g_obj.get('sessions') or []):
                        session_rows_for_conflict.append({
                            'lesson': sel['lesson'],
                            'course_code': sel.get('course_code') or '',
                            'group': sel['group'],
                            'educational_group': g_obj.get('educational_group') or 'mixed',
                            'term': active_term,
                            'teacher': g_obj.get('teacher', ''),
                            'weekday': sess.get('weekday'),
                            'date': sess.get('date') if not sess.get('weekday') is not None else '',
                            'time': sess.get('time'),
                            'end_time': sess.get('end_time'),
                            'type': 'class',
                        })
        conflicts = self.detect_schedule_conflicts(
            session_rows_for_conflict,
            active_term=active_term,
            user_educational_group=(user_edu if user_edu in ('male', 'female') else None),
        )

        return {
            'ok': True,
            'term': active_term,
            'selected_count': len(clean_selections),
            'computed_group': new_group,
            'registered_group': registered_group,
            'majority': majority,
            'educational_group': user_edu,
            'educational_group_info': edu_info,
            'selections': clean_selections,
            'conflicts': conflicts,
        }

    async def get_personalized_schedules(self, uid: int, stype: str = None, upcoming: bool = True, term: str = None) -> dict:
        """ساخت برنامه کلاسی و امتحانی دانشجو دقیقاً از روی انتخاب‌های درس‌به‌درس و گروه آموزشی (آقایان/بانوان) او."""
        uid = int(uid)
        sel_state = await self.get_student_course_selections(uid, term=term)
        active_term = sel_state['term']
        user_edu = sel_state.get('educational_group') or 'unknown'
        edu_filter = user_edu if user_edu in ('male', 'female') else None
        sel_map = sel_state['selections_map']
        sel_teacher_map = {s['lesson']: s.get('teacher', '') for s in sel_state['selections']}
        offerings = sel_state['offerings']
        offered_lessons = [o['lesson'] for o in offerings]
        effective_group = sel_state['computed_group']

        if not sel_map:
            items = await self.get_schedules(
                stype=stype, upcoming=upcoming, group=effective_group,
                term=active_term, educational_group=edu_filter,
            )
            conflicts = self.detect_schedule_conflicts(
                items, active_term=active_term, user_educational_group=edu_filter,
            )
            return {
                'items': items,
                'has_custom_selection': False,
                'selected_count': 0,
                'total_offered_count': len(offered_lessons),
                'unselected_lessons': offered_lessons,
                'computed_group': effective_group,
                'registered_group': sel_state['registered_group'],
                'majority': sel_state['majority'],
                'educational_group': user_edu,
                'educational_group_info': sel_state.get('educational_group_info'),
                'needs_educational_group_confirmation': sel_state.get('needs_educational_group_confirmation', False),
                'mismatched_selections': sel_state.get('mismatched_selections', []),
                'conflicts': conflicts,
                'term': active_term,
            }

        all_items = await self.get_schedules(
            stype=stype, upcoming=upcoming, group=None,
            term=active_term, educational_group=edu_filter,
        )
        filtered = []
        for item in (all_items or []):
            lsn = str(item.get('lesson') or '').strip()
            item_grp = self.normalize_group(item.get('group')) or 'هر دو'
            if lsn in sel_map:
                chosen_grp = sel_map[lsn]
                if item_grp in (chosen_grp, 'هر دو', ''):
                    enriched = dict(item)
                    if not enriched.get('teacher') and sel_teacher_map.get(lsn):
                        enriched['teacher'] = sel_teacher_map[lsn]
                    enriched['selected_group'] = chosen_grp
                    filtered.append(enriched)
            elif lsn not in offered_lessons and item_grp in ('هر دو', ''):
                filtered.append(dict(item))
            elif item.get('type') == 'exam' and lsn not in offered_lessons:
                if item_grp in (effective_group, 'هر دو', ''):
                    filtered.append(dict(item))

        unselected_lessons = [lsn for lsn in offered_lessons if lsn not in sel_map]
        conflicts = self.detect_schedule_conflicts(
            filtered, active_term=active_term, user_educational_group=edu_filter,
        )
        return {
            'items': filtered,
            'has_custom_selection': True,
            'selected_count': len(sel_map),
            'total_offered_count': len(offered_lessons),
            'unselected_lessons': unselected_lessons,
            'computed_group': effective_group,
            'registered_group': sel_state['registered_group'],
            'majority': sel_state['majority'],
            'educational_group': user_edu,
            'educational_group_info': sel_state.get('educational_group_info'),
            'needs_educational_group_confirmation': sel_state.get('needs_educational_group_confirmation', False),
            'mismatched_selections': sel_state.get('mismatched_selections', []),
            'conflicts': conflicts,
            'term': active_term,
        }

    async def get_course_selection_admin_stats(self, term: str = None) -> dict:
        """آمار مدیریتی انتخاب واحد برای پنل ادمین (تعداد تکمیل‌شدگان، تفکیک گروه اکثریت، گروه آموزشی و درس‌ها)."""
        term_cfg = await self.get_current_term_config()
        active_term = term or term_cfg['term']
        offerings = await self.get_term_course_offerings(active_term, include_all_educational_groups=True)
        total_reachable = await self.count_reachable_users()

        pipeline = [
            {'$match': {'term': active_term, 'archived': {'$ne': True}}},
            {'$group': {
                '_id': {'lesson': '$lesson', 'group': '$group'},
                'count': {'$sum': 1},
            }},
        ]
        user_distinct = await self.course_selections.distinct(
            'user_id', {'term': active_term, 'archived': {'$ne': True}}
        )
        agg_rows = await self.course_selections.aggregate(pipeline).to_list(500)

        per_lesson: dict[str, dict] = {}
        for row in agg_rows:
            key = row.get('_id') or {}
            lsn = key.get('lesson') or ''
            grp = key.get('group') or ''
            if not lsn:
                continue
            per_lesson.setdefault(lsn, {'lesson': lsn, 'group_1': 0, 'group_2': 0, 'group_3': 0})
            if grp == '1':
                per_lesson[lsn]['group_1'] += int(row.get('count') or 0)
            elif grp == '2':
                per_lesson[lsn]['group_2'] += int(row.get('count') or 0)
            elif grp == '3':
                per_lesson[lsn]['group_3'] += int(row.get('count') or 0)

        g1_users = await self.users.count_documents({'approved': True, 'blocked_bot': {'$ne': True}, 'group': '1'})
        g2_users = await self.users.count_documents({'approved': True, 'blocked_bot': {'$ne': True}, 'group': '2'})
        male_users = await self.users.count_documents({'approved': True, 'blocked_bot': {'$ne': True}, 'educational_group': 'male', 'group_verified': True})
        female_users = await self.users.count_documents({'approved': True, 'blocked_bot': {'$ne': True}, 'educational_group': 'female', 'group_verified': True})
        unknown_edu_users = max(0, total_reachable - male_users - female_users)

        return {
            'term': active_term,
            'term_config': term_cfg,
            'total_students': total_reachable,
            'completed_students': len(user_distinct),
            'selected_students': len(user_distinct),
            'pending_students': max(0, total_reachable - len(user_distinct)),
            'unselected_students': max(0, total_reachable - len(user_distinct)),
            'group_1_students': g1_users,
            'group1_count': g1_users,
            'group_2_students': g2_users,
            'group2_count': g2_users,
            'male_students': male_users,
            'female_students': female_users,
            'unknown_educational_group_students': unknown_edu_users,
            'offerings_count': len(offerings),
            'per_lesson': list(per_lesson.values()),
        }

    # ══════════════════════════════════════════════════
    #  🖼 بخش ۳: سیستم Staging استخراج انتخاب واحد از چند تصویر (Vision + Dedup/Diff + Publish)
    # ══════════════════════════════════════════════════

    @staticmethod
    def _clean_persian_course_title(name: str) -> str:
        import re as _re
        from time_utils import en_digits as _en
        s = _en(str(name or '')).strip()
        s = s.replace('ي', 'ی').replace('ك', 'ک').replace('\u200c', ' ')
        s = _re.sub(r'\s+', ' ', s)
        return s[:120]

    @classmethod
    def normalize_extracted_course_row(
        cls,
        raw: dict,
        default_term: str = '',
        default_edu_group: str = 'unknown',
        source_image: str = '',
    ) -> dict | None:
        """نرمال‌سازی و اعتبارسنجی یک ردیف استخراج‌شده از تصویر انتخاب واحد بدون حدس زدن فیلدهای غایب."""
        from time_utils import en_digits as _en
        if not isinstance(raw, dict):
            return None
        course_name = cls._clean_persian_course_title(
            raw.get('course_name') or raw.get('lesson') or raw.get('title') or ''
        )
        if not course_name:
            return None
        course_code = _en(str(raw.get('course_code') or raw.get('code') or '')).strip()[:40]
        class_code = _en(str(raw.get('class_code') or '')).strip()[:40]
        group_code = cls.normalize_group(_en(str(raw.get('group_code') or raw.get('group') or '')))
        if group_code not in ('1', '2', '3', '4', 'هر دو'):
            group_code = _en(str(raw.get('group_code') or '')).strip()[:10] or '1'

        instructor = cls._clean_persian_course_title(
            raw.get('instructor_name') or raw.get('teacher') or ''
        )[:100]
        wd = raw.get('weekday')
        if wd is not None and str(wd).strip() != '':
            try:
                wd = int(wd)
                if not (0 <= wd <= 6):
                    wd = None
            except (TypeError, ValueError):
                wd = None
        else:
            wd = None

        start_time = _en(str(raw.get('start_time') or raw.get('time') or '')).strip()[:10]
        end_time = _en(str(raw.get('end_time') or '')).strip()[:10]
        exam_date = _en(str(raw.get('exam_date') or '')).strip()[:20]
        exam_time = _en(str(raw.get('exam_time') or '')).strip()[:10]
        term = _en(str(raw.get('academic_term') or raw.get('term') or default_term or '')).strip()[:40]
        edu_grp = cls.normalize_class_educational_group(
            raw.get('educational_group') or default_edu_group, default='unknown'
        )
        src_img = str(raw.get('source_image') or source_image or '').strip()[:120]
        section_type = str(raw.get('section_type') or 'taken_courses').strip()
        try:
            conf = round(max(0.0, min(1.0, float(raw.get('extraction_confidence') if raw.get('extraction_confidence') is not None else 0.9))), 2)
        except (TypeError, ValueError):
            conf = 0.9
        try:
            credit = float(raw.get('credit') if raw.get('credit') is not None and str(raw.get('credit')).strip() != '' else 1.0)
            if credit <= 0 or credit > 12:
                credit = 1.0
        except (TypeError, ValueError):
            credit = 1.0

        return {
            'course_name': course_name,
            'course_code': course_code,
            'class_code': class_code,
            'group_code': group_code,
            'credit': round(credit, 2),
            'instructor_name': instructor,
            'weekday': wd,
            'start_time': start_time,
            'end_time': end_time,
            'exam_date': exam_date,
            'exam_time': exam_time,
            'academic_term': term,
            'educational_group': edu_grp,
            'source_image': src_img,
            'section_type': section_type,
            'extraction_confidence': conf,
        }

    @classmethod
    def reconcile_staged_course_extractions(cls, raw_items: list, academic_term: str = '') -> dict:
        """موتور تطبیق چند تصویر (دختران و پسران) و جلوگیری از تکرار در فضای Staging:
        - مقایسه بر اساس کلید ترکیبی (academic_term, course_code_or_name, group_code, class_code) نه صرفاً نام درس!
        - اگر یک درس با کد درس و گروه درس یکسان و مشخصات سازگار هم در تصویر آقایان (male_only) و هم در تصویر بانوان (female_only) وجود داشته باشد ← به عنوان درس مشترک (mixed) ادغام می‌شود.
        - اگر یک درس (مثلاً آئین زندگی یا تربیت بدنی ۲) در تصویر آقایان گروه ۲ و در تصویر بانوان گروه ۱ یا ۳ (یا استاد/ساعت متفاوت) داشته باشد ← هر دو رکورد به صورت مستقل با برچسب male_only و female_only حفظ می‌شوند.
        - رکوردهای دقیقاً تکراری از یک گروه آموزشی ادغام می‌شوند و موارد متناقض با needs_review=True علامت‌گذاری می‌شوند.
        """
        normalized = []
        for idx, r in enumerate(raw_items or []):
            n = cls.normalize_extracted_course_row(r, default_term=academic_term)
            if n:
                n['item_id'] = str(r.get('item_id') or f"item_{idx + 1}")
                normalized.append(n)

        # گام ۱: گروه‌بندی بر اساس کلید کاتالوگ (term, course_code || course_name, group_code, class_code)
        by_section_key: dict[tuple, list[dict]] = {}
        for item in normalized:
            code_or_name = item['course_code'] or item['course_name']
            key = (
                item['academic_term'] or academic_term,
                code_or_name,
                item['group_code'],
                item['class_code'],
            )
            by_section_key.setdefault(key, []).append(item)

        reconciled_items = []
        merged_shared_count = 0
        deduplicated_count = 0
        distinct_gender_count = 0
        conflict_review_count = 0

        # بررسی اینکه کدام دروس دارای چند گروه متفاوت بین آقایان و بانوان هستند
        course_gender_groups: dict[str, set] = {}
        for item in normalized:
            ck = item['course_code'] or item['course_name']
            course_gender_groups.setdefault(ck, set()).add((item['educational_group'], item['group_code']))

        seq = 0
        for key, group_rows in by_section_key.items():
            if len(group_rows) == 1:
                row = dict(group_rows[0])
                seq += 1
                row['item_id'] = row.get('item_id') or f"stg_{seq}"
                ck = row['course_code'] or row['course_name']
                has_other_gender_diff_group = len({g for _, g in course_gender_groups.get(ck, set())}) > 1
                row['merge_status'] = 'distinct_gender_section' if has_other_gender_diff_group else 'single_source'
                if has_other_gender_diff_group:
                    distinct_gender_count += 1
                row['needs_review'] = bool(row['educational_group'] == 'unknown' or row['extraction_confidence'] < 0.75)
                row['review_note'] = 'گروه آموزشی تصویر نامشخص است' if row['educational_group'] == 'unknown' else ''
                row['source_images'] = [row['source_image']] if row.get('source_image') else []
                reconciled_items.append(row)
                continue

            # چند ردیف با کلید (term, course_code, group_code, class_code) یکسان آمده‌اند
            # بررسی سازگاری استاد و ساعت کلاس بین آن‌ها
            instructors = {r['instructor_name'] for r in group_rows if r.get('instructor_name')}
            times = {(r['weekday'], r['start_time'], r['end_time']) for r in group_rows if r.get('start_time') or r.get('weekday') is not None}
            edu_groups = {r['educational_group'] for r in group_rows if r.get('educational_group') and r.get('educational_group') != 'unknown'}

            has_conflict = (len(instructors) > 1) or (len(times) > 1)
            if has_conflict and ('male_only' in edu_groups and 'female_only' in edu_groups):
                # یک کد درس و یک شماره گروه ولی برای آقایان و بانوان استاد یا ساعت متفاوت دارد!
                # نباید ادغام شوند؛ به تفکیک گروه آموزشی نگه داشته می‌شوند
                for sub_edu in ('male_only', 'female_only', 'mixed', 'unknown'):
                    sub_rows = [r for r in group_rows if r['educational_group'] == sub_edu]
                    if not sub_rows:
                        continue
                    base = dict(sub_rows[0])
                    seq += 1
                    base['item_id'] = f"stg_{seq}"
                    base['merge_status'] = 'distinct_gender_section'
                    base['needs_review'] = True
                    base['review_note'] = 'کد و گروه درس مشترک ولی استاد/ساعت بین تصویر آقایان و بانوان متفاوت است.'
                    base['source_images'] = sorted({r['source_image'] for r in sub_rows if r.get('source_image')})
                    distinct_gender_count += 1
                    conflict_review_count += 1
                    reconciled_items.append(base)
                continue

            # ادغام فیلدهای تکمیلی (مثلاً واحد از تصویر پرتال + استاد/ساعت از تصویر برنامه)
            merged = dict(group_rows[0])
            seq += 1
            merged['item_id'] = f"stg_{seq}"
            for r in group_rows[1:]:
                for fld in ('course_code', 'class_code', 'instructor_name', 'start_time', 'end_time', 'exam_date', 'exam_time'):
                    if not merged.get(fld) and r.get(fld):
                        merged[fld] = r[fld]
                if merged.get('weekday') is None and r.get('weekday') is not None:
                    merged['weekday'] = r['weekday']
                if merged.get('credit', 1.0) == 1.0 and r.get('credit', 1.0) != 1.0:
                    merged['credit'] = r['credit']
                merged['extraction_confidence'] = max(merged.get('extraction_confidence', 0.0), r.get('extraction_confidence', 0.0))

            merged['source_images'] = sorted({r['source_image'] for r in group_rows if r.get('source_image')})
            if ('male_only' in edu_groups and 'female_only' in edu_groups) or ('mixed' in edu_groups):
                merged['educational_group'] = 'mixed'
                merged['merge_status'] = 'merged_shared'
                merged_shared_count += 1
            elif len(edu_groups) == 1:
                merged['educational_group'] = next(iter(edu_groups))
                merged['merge_status'] = 'deduplicated_exact'
                deduplicated_count += len(group_rows) - 1
            else:
                merged['educational_group'] = 'unknown'
                merged['merge_status'] = 'deduplicated_exact'
                deduplicated_count += len(group_rows) - 1

            merged['needs_review'] = bool(has_conflict or merged['educational_group'] == 'unknown')
            if has_conflict:
                conflict_review_count += 1
                merged['review_note'] = (
                    f"تفاوت در اطلاعات استخراج‌شده بین تصاویر (اساتید: {'، '.join(instructors) or '—'}) — نیازمند بررسی ادمین."
                )
            else:
                merged['review_note'] = ''
            reconciled_items.append(merged)

        return {
            'academic_term': academic_term,
            'items': reconciled_items,
            'summary': {
                'raw_count': len(normalized),
                'staged_count': len(reconciled_items),
                'merged_shared_count': merged_shared_count,
                'distinct_gender_count': distinct_gender_count,
                'deduplicated_count': deduplicated_count,
                'conflict_review_count': conflict_review_count,
            },
        }

    async def create_course_import_staging_batch(
        self,
        raw_items: list,
        academic_term: str = None,
        intake: str = '',
        source_images: list = None,
        created_by: int = None,
    ) -> dict:
        """ایجاد یک بسته Staging جدید از خروجی استخراج چند تصویر برای بازبینی ادمین پیش از انتشار."""
        import uuid
        from datetime import timezone
        if not academic_term:
            academic_term = (await self.get_current_term_config())['term']
        reconciled = self.reconcile_staged_course_extractions(raw_items, academic_term=academic_term)
        batch_id = f"stg_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"
        now_iso = utc_now_iso()
        doc = {
            'batch_id': batch_id,
            'academic_term': academic_term,
            'intake': str(intake or '').strip(),
            'status': 'staged',  # 'staged' | 'published' | 'rolled_back' | 'rejected'
            'source_images': list(source_images or []),
            'items': reconciled['items'],
            'summary': reconciled['summary'],
            'created_by': int(created_by or 0),
            'created_at': now_iso,
            'updated_at': now_iso,
            'published_at': None,
            'published_by': None,
            'published_snapshot': None,
        }
        await self.course_import_staging.insert_one(doc)
        doc.pop('_id', None)
        return doc

    async def get_course_import_staging_batch(self, batch_id: str) -> dict | None:
        doc = await self.course_import_staging.find_one({'batch_id': str(batch_id or '').strip()})
        if doc:
            doc = dict(doc)
            doc['id'] = str(doc.pop('_id', ''))
        return doc

    async def list_course_import_staging_batches(self, academic_term: str = None, status: str = None, limit: int = 20) -> list:
        q = {}
        if academic_term:
            q['academic_term'] = str(academic_term).strip()
        if status:
            q['status'] = str(status).strip()
        docs = await self.course_import_staging.find(q).sort('created_at', -1).to_list(max(1, min(100, int(limit or 20))))
        out = []
        for d in (docs or []):
            row = dict(d)
            row['id'] = str(row.pop('_id', ''))
            row.pop('published_snapshot', None)
            out.append(row)
        return out

    async def update_course_import_staging_item(
        self,
        batch_id: str,
        item_id: str,
        updates: dict,
        actor_id: int = None,
    ) -> dict | None:
        """ویرایش، تأیید یا حذف یک ردیف در فضای Staging توسط ادمین."""
        batch = await self.course_import_staging.find_one({'batch_id': str(batch_id or '').strip()})
        if not batch or batch.get('status') != 'staged':
            return None
        items = list(batch.get('items') or [])
        found = False
        new_items = []
        for it in items:
            if str(it.get('item_id')) != str(item_id):
                new_items.append(it)
                continue
            found = True
            if updates.get('_delete'):
                continue
            merged = dict(it)
            for k in (
                'course_name', 'course_code', 'class_code', 'group_code', 'credit',
                'instructor_name', 'weekday', 'start_time', 'end_time',
                'exam_date', 'exam_time', 'educational_group', 'needs_review', 'review_note',
            ):
                if k in updates:
                    merged[k] = updates[k]
            norm = self.normalize_extracted_course_row(
                merged,
                default_term=batch.get('academic_term', ''),
                default_edu_group=merged.get('educational_group', 'mixed'),
                source_image=merged.get('source_image', ''),
            )
            if norm:
                norm['item_id'] = it.get('item_id')
                norm['merge_status'] = it.get('merge_status', 'edited_by_admin')
                norm['source_images'] = it.get('source_images', [])
                norm['needs_review'] = bool(updates.get('needs_review', False))
                norm['review_note'] = str(updates.get('review_note') or '')
                new_items.append(norm)
        if not found:
            return None
        now_iso = utc_now_iso()
        await self.course_import_staging.update_one(
            {'batch_id': batch['batch_id']},
            {'$set': {'items': new_items, 'updated_at': now_iso, 'updated_by': int(actor_id or 0)}},
        )
        return await self.get_course_import_staging_batch(batch_id)

    async def publish_course_import_staging_batch(
        self,
        batch_id: str,
        actor_id: int = None,
        selected_item_ids: list = None,
    ) -> dict:
        """انتشار Transactional و قابل بازگشت (Rollback-safe) رکوردهای تأییدشده از Staging به دیتابیس اصلی."""
        batch = await self.course_import_staging.find_one({'batch_id': str(batch_id or '').strip()})
        if not batch:
            raise ValueError('staging_batch_not_found')
        if batch.get('status') == 'published':
            raise ValueError('staging_batch_already_published')

        term = str(batch.get('academic_term') or (await self.get_current_term_config())['term']).strip()
        items = list(batch.get('items') or [])
        if selected_item_ids:
            sel_set = {str(x) for x in selected_item_ids}
            items = [it for it in items if str(it.get('item_id')) in sel_set]
        if not items:
            raise ValueError('no_items_to_publish')

        # تهیه Snapshot قبل از انتشار برای قابلیت بازگردانی کامل (Rollback)
        prev_offerings = await self.course_offerings.find({'term': term}).to_list(1000)
        prev_templates = await self.schedule_templates.find({'term': term}).to_list(1000)
        snapshot = {
            'term': term,
            'offerings': [
                {k: v for k, v in d.items() if k != '_id'}
                for d in (prev_offerings or [])
            ],
            'templates': [
                {k: v for k, v in d.items() if k != '_id'}
                for d in (prev_templates or [])
            ],
        }

        published_offerings = 0
        published_templates = 0
        WEEKDAY_FA = ['شنبه', 'یکشنبه', 'دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنجشنبه', 'جمعه']

        for it in items:
            edu_grp = self.normalize_class_educational_group(it.get('educational_group'), default='mixed')
            if edu_grp == 'unknown':
                edu_grp = 'mixed'
            wd = it.get('weekday')
            st = str(it.get('start_time') or '').strip()
            et = str(it.get('end_time') or '').strip()
            sched_sum = ''
            if wd is not None and 0 <= int(wd) < 7:
                sched_sum = WEEKDAY_FA[int(wd)] + (f" {st}" if st else "") + (f" تا {et}" if et else "")
            await self.upsert_course_offering(
                lesson=it['course_name'],
                group=it['group_code'],
                teacher=it.get('instructor_name', ''),
                credit=it.get('credit', 1.0),
                term=term,
                schedule_summary=sched_sum,
                weekday=wd,
                time=st,
                end_time=et,
                educational_group=edu_grp,
                course_code=it.get('course_code', ''),
                class_code=it.get('class_code', ''),
                exam_date=it.get('exam_date', ''),
                exam_time=it.get('exam_time', ''),
                source_image=it.get('source_image', ''),
                extraction_confidence=it.get('extraction_confidence'),
            )
            published_offerings += 1

            # اگر روز هفته و ساعت شروع در تصویر وجود داشته است، در الگوی هفتگی همان ترم هم ثبت شود
            if wd is not None and st:
                res_tpl = await self.bulk_upsert_schedule_templates([{
                    'weekday': wd,
                    'time': st,
                    'end_time': et,
                    'lesson': it['course_name'],
                    'teacher': it.get('instructor_name', ''),
                    'group': it['group_code'],
                    'educational_group': edu_grp,
                    'term': term,
                    'course_code': it.get('course_code', ''),
                    'credit': it.get('credit', 1.0),
                }], term=term)
                published_templates += int(res_tpl.get('total') or 0)

        now_iso = utc_now_iso()
        await self.course_import_staging.update_one(
            {'batch_id': batch['batch_id']},
            {'$set': {
                'status': 'published',
                'published_at': now_iso,
                'published_by': int(actor_id or 0),
                'published_snapshot': snapshot,
                'updated_at': now_iso,
            }},
        )
        return {
            'ok': True,
            'batch_id': batch['batch_id'],
            'academic_term': term,
            'published_offerings': published_offerings,
            'published_templates': published_templates,
        }

    async def rollback_course_import_staging_batch(self, batch_id: str, actor_id: int = None) -> dict:
        """بازگردانی کامل (Rollback) یک بسته منتشرشده به وضعیت قبل از انتشار."""
        batch = await self.course_import_staging.find_one({'batch_id': str(batch_id or '').strip()})
        if not batch or batch.get('status') != 'published':
            raise ValueError('batch_not_published')
        snapshot = batch.get('published_snapshot') or {}
        term = str(snapshot.get('term') or batch.get('academic_term') or '').strip()
        if not term:
            raise ValueError('missing_snapshot_term')

        await self.course_offerings.delete_many({'term': term})
        for off_doc in (snapshot.get('offerings') or []):
            await self.course_offerings.insert_one(dict(off_doc))

        await self.schedule_templates.delete_many({'term': term})
        for tpl_doc in (snapshot.get('templates') or []):
            await self.schedule_templates.insert_one(dict(tpl_doc))

        now_iso = utc_now_iso()
        await self.course_import_staging.update_one(
            {'batch_id': batch['batch_id']},
            {'$set': {
                'status': 'rolled_back',
                'rolled_back_at': now_iso,
                'rolled_back_by': int(actor_id or 0),
                'updated_at': now_iso,
            }},
        )
        return {
            'ok': True,
            'batch_id': batch['batch_id'],
            'academic_term': term,
            'restored_offerings': len(snapshot.get('offerings') or []),
            'restored_templates': len(snapshot.get('templates') or []),
        }

    # ══════════════════════════════════════════════════
    #  🧹 بخش ۴: شناسایی و آرشیو ایمن رکوردهای تکراری/منسوخ برنامه
    # ══════════════════════════════════════════════════

    async def audit_and_cleanup_schedule_anomalies(
        self,
        dry_run: bool = True,
        active_term: str = None,
    ) -> dict:
        """شناسایی و آرشیو ایمن رکوردهای تکراری، نامعتبر یا منسوخ در schedules و schedule_templates بدون حذف تاریخچه."""
        if not active_term:
            active_term = (await self.get_current_term_config())['term']
        now_iso = utc_now_iso()

        sched_docs = await self.schedules.find({}).to_list(5000)
        tpl_docs = await self.schedule_templates.find({}).to_list(2000)

        duplicate_sched_ids = []
        invalid_time_sched_ids = []
        stale_term_sched_ids = []
        seen_sched_keys = {}

        for s in (sched_docs or []):
            if s.get('archived'):
                continue
            sid = s.get('_id')
            s_term = str(s.get('term') or '').strip()
            if s_term and s_term != active_term:
                stale_term_sched_ids.append(sid)
                continue
            st_min = self._parse_hhmm_minutes(s.get('time') or '')
            en_min = self._parse_hhmm_minutes(s.get('end_time') or '')
            if st_min is not None and en_min is not None and en_min <= st_min:
                invalid_time_sched_ids.append(sid)
                continue
            key = (
                str(s.get('date') or ''),
                str(s.get('time') or ''),
                str(s.get('lesson') or '').strip(),
                self.normalize_group(s.get('group')) or 'هر دو',
                self.normalize_class_educational_group(s.get('educational_group'), default='mixed'),
                str(s.get('type') or 'class'),
            )
            if key in seen_sched_keys:
                duplicate_sched_ids.append(sid)
            else:
                seen_sched_keys[key] = sid

        duplicate_tpl_ids = []
        seen_tpl_keys = {}
        for t in (tpl_docs or []):
            if t.get('archived'):
                continue
            tid = t.get('_id')
            key = (
                t.get('weekday'),
                str(t.get('time') or ''),
                str(t.get('lesson') or '').strip(),
                self.normalize_group(t.get('group')) or 'هر دو',
                self.normalize_class_educational_group(t.get('educational_group'), default='mixed'),
                str(t.get('term') or active_term),
            )
            if key in seen_tpl_keys:
                duplicate_tpl_ids.append(tid)
            else:
                seen_tpl_keys[key] = tid

        archived_schedules = 0
        archived_templates = 0
        if not dry_run:
            for sid in (duplicate_sched_ids + invalid_time_sched_ids + stale_term_sched_ids):
                await self.schedules.update_one(
                    {'_id': sid},
                    {'$set': {'archived': True, 'archived_at': now_iso, 'archive_reason': 'schedule_cleanup_v2'}},
                )
                archived_schedules += 1
            for tid in duplicate_tpl_ids:
                await self.schedule_templates.update_one(
                    {'_id': tid},
                    {'$set': {'archived': True, 'archived_at': now_iso, 'archive_reason': 'template_duplicate_cleanup_v2'}},
                )
                archived_templates += 1

        return {
            'ok': True,
            'dry_run': bool(dry_run),
            'active_term': active_term,
            'duplicate_schedules_found': len(duplicate_sched_ids),
            'invalid_time_schedules_found': len(invalid_time_sched_ids),
            'stale_term_schedules_found': len(stale_term_sched_ids),
            'duplicate_templates_found': len(duplicate_tpl_ids),
            'archived_schedules': archived_schedules,
            'archived_templates': archived_templates,
        }

    async def run_term_course_selection_reminder(
        self,
        bot=None,
        force: bool = False,
        is_second_reminder: bool = False,
    ) -> dict:
        """ارسال خودکار پیام یادآوری انتخاب واحد پس از پایان امتحانات هر ترم.

        - فقط زمانی اجرا می‌شود که تاریخ امروز از `effective_exams_end_date` گذشته باشد (یا `force=True` توسط ادمین).
        - فقط به دانشجوهایی ارسال می‌شود که اعلان `course_selection` برایشان روشن است و هنوز در این ترم انتخاب واحد نکرده‌اند.
        - هر دانشجو در هر ترم فقط یک بار پیام اول را می‌گیرد (و اگر `second_reminder_enabled` روشن باشد، پس از N روز حداکثر یک بار یادآوری دوم).
        - اگر دانشجو ربات را بلاک کرده باشد (`Forbidden`), خطا گرفته شده و `mark_user_blocked` صدا زده می‌شود.
        """
        from utils import now_tehran
        term_cfg = await self.get_current_term_config()
        active_term = term_cfg['term']
        end_date = term_cfg.get('effective_exams_end_date') or ''
        today_str = now_tehran().strftime('%Y-%m-%d')

        if not force:
            if not end_date:
                return {'ok': True, 'triggered': False, 'sent': 0, 'skipped': 0, 'blocked': 0, 'reason': 'no_exams_end_date'}
            if today_str <= end_date:
                return {'ok': True, 'triggered': False, 'sent': 0, 'skipped': 0, 'blocked': 0, 'reason': 'exams_not_finished_yet', 'exams_end_date': end_date}

        # آرشیو انتخاب‌های ترم‌های قدیمی‌تر
        await self.archive_previous_term_selections(active_term)

        # دانشجوهایی که در این ترم انتخاب واحد ثبت کرده‌اند نیازی به یادآوری ندارند
        completed_uids = set(await self.course_selections.distinct(
            'user_id', {'term': active_term, 'archived': {'$ne': True}}
        ))

        eligible_users = await self.notif_users('course_selection')
        now_dt = now_utc()
        now_iso = utc_now_iso()
        second_enabled = bool(term_cfg.get('second_reminder_enabled')) or is_second_reminder
        second_days = int(term_cfg.get('second_reminder_days') or 3)

        sent = 0
        skipped = 0
        skipped_has_selection = 0
        skipped_already_reminded = 0
        blocked = 0
        failed = 0
        inbox_docs = []

        for u in (eligible_users or []):
            uid = u.get('user_id')
            if not uid:
                skipped += 1
                continue
            if uid in completed_uids:
                skipped += 1
                skipped_has_selection += 1
                continue

            full_u = await self.get_user(uid, use_cache=False) or {}
            rem_map = dict(full_u.get('course_selection_reminders') or {})
            term_state = rem_map.get(active_term) if isinstance(rem_map, dict) else None
            count_so_far = int((term_state or {}).get('count') or 0)
            first_at_str = (term_state or {}).get('first_at') or ''

            if count_so_far >= 2:
                skipped += 1
                skipped_already_reminded += 1
                continue
            if count_so_far == 1:
                if not second_enabled:
                    skipped += 1
                    skipped_already_reminded += 1
                    continue
                if not is_second_reminder:
                    try:
                        from time_utils import parse_machine_datetime
                        elapsed_days = (now_dt - parse_machine_datetime(first_at_str)).total_seconds() / 86400.0
                        if elapsed_days < second_days:
                            skipped += 1
                            skipped_already_reminded += 1
                            continue
                    except Exception:
                        skipped += 1
                        skipped_already_reminded += 1
                        continue

            student_name = escape(str(full_u.get('name') or 'دانشجوی عزیز').strip())
            is_second = (count_so_far == 1)
            msg_html = (
                f"سلام {student_name}! 👋\n"
                + ("امتحانات تموم شد، خسته نباشی! 🎓\n\n" if not is_second else "یه یادآوری دوستانه برای برنامه ترم جدید! 📅\n\n")
                + "انتخاب واحدت رو انجام دادی؟ بیا توی بخش <b>«برنامه»</b>، گروه هر درست رو انتخاب کن "
                "تا برنامه کلاسی این ترمت رو دقیق و شخصی‌سازی‌شده برات بچینیم ✨"
            )
            plain_body = (
                "امتحانات تموم شد، خسته نباشی! انتخاب واحدت رو انجام دادی؟ "
                "بیا توی بخش برنامه، گروه هر درست رو انتخاب کن تا برنامه کلاسی این ترمت رو دقیق برات بچینیم."
            )

            delivered = False
            if bot is not None:
                try:
                    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                    kb_rows = [
                        [InlineKeyboardButton("🎓 انتخاب واحدم رو وارد می‌کنم", callback_data='schedule:course_select')],
                    ]
                    await bot.send_message(
                        chat_id=uid,
                        text=msg_html,
                        parse_mode='HTML',
                        reply_markup=InlineKeyboardMarkup(kb_rows),
                    )
                    delivered = True
                except Exception as exc:
                    err_s = str(exc)
                    if 'Forbidden' in err_s or 'blocked' in err_s.lower() or 'deactivated' in err_s.lower() or 'chat not found' in err_s.lower():
                        await self.mark_user_blocked(uid, True, reason='blocked_by_user')
                        blocked += 1
                        continue
                    failed += 1
                    continue
            else:
                # صف ارسال ربات (bot_notifs) برای مواقعی که از وب‌ادمین بدون نمونه مستقیم bot صدا زده می‌شود
                await self.bot_notifs.insert_one({
                    'type': 'course_selection',
                    'chat_id': uid,
                    'text': msg_html,
                    'link': '/schedule?select=1',
                    'sent': False,
                    'created_at': now_iso,
                })
                delivered = True

            if delivered:
                sent += 1
                new_state = {
                    'count': count_so_far + 1,
                    'first_at': first_at_str or now_iso,
                    'last_at': now_iso,
                }
                rem_map[active_term] = new_state
                await self.update_user(uid, {
                    'course_selection_reminders': rem_map,
                })
                inbox_docs.append({
                    'user_id': uid,
                    'type': 'course_selection',
                    'title': '🎓 یادآوری انتخاب واحد ترم جدید',
                    'body': plain_body,
                    'link': '/schedule?select=1',
                })

        if inbox_docs and hasattr(self, 'inbox_add_many'):
            try:
                await self.inbox_add_many(inbox_docs)
            except Exception:
                pass

        return {
            'ok': True,
            'triggered': True,
            'term': active_term,
            'sent': sent,
            'skipped': skipped,
            'skipped_has_selection': skipped_has_selection,
            'skipped_already_reminded': skipped_already_reminded,
            'blocked': blocked,
            'failed': failed,
        }



    # ══════════════════════════════════════════════════
    #  FAQ
    # ══════════════════════════════════════════════════

    async def faq_get_all(self):
        return await self.faq.find({}).sort('order', 1).to_list(100)


    async def faq_add(self, question: str, answer: str, category: str = 'عمومی'):
        count = await self.faq.count_documents({})
        result = await self.faq.insert_one({
            'question': question, 'answer': answer, 'category': category,
            'order': count, 'created_at': utc_now_iso(),
        })
        return result.inserted_id


    async def faq_get(self, fid: str):
        try:
            return await self.faq.find_one({'_id': ObjectId(fid)})
        except Exception:
            return None


    async def faq_delete(self, fid: str):
        # 🛡 AUDIT-R6 — خطای حذف نباید بلعیده شود: None = خطا، عدد = تعداد حذف‌شده
        # (قبلاً پنل «موفق» گزارش می‌داد درحالی‌که آیتم سر جایش بود).
        try:
            r = await self.faq.delete_one({'_id': ObjectId(fid)})
            return int(getattr(r, 'deleted_count', 0) or 0)
        except Exception as e:
            logger.error(f"faq_delete failed for {fid}: {e}")
            return None


    async def faq_update(self, fid: str, data: dict):
        """ویرایش سؤال متداول — فیلدهای مجاز: question/answer/category/order."""
        allowed = {'question', 'answer', 'category', 'order'}
        payload = {k: v for k, v in (data or {}).items() if k in allowed}
        if not payload:
            return False
        # اعتبارسنجی سبک
        if 'question' in payload and not str(payload['question']).strip():
            return False
        if 'answer' in payload and not str(payload['answer']).strip():
            return False
        if 'category' in payload:
            payload['category'] = str(payload['category']).strip() or 'عمومی'
        try:
            r = await self.faq.update_one({'_id': ObjectId(fid)}, {'$set': payload})
            return bool(r.matched_count)
        except Exception as e:
            logger.error(f"faq_update failed for {fid}: {e}")
            return False


    async def seed_subscription_copyright_faqs(self):
        """
        FIX مهم: faq.py._get_faq_data فقط وقتی دیتابیس FAQ کاملاً
        خالیه از DEFAULT_FAQS (فallback کد) استفاده می‌کند؛ به محض
        این‌که دیتابیس حتی یک سؤال داشته باشد، فقط همان چیزی که در
        دیتابیس است نمایش داده می‌شود و بقیه‌ی دسته‌ها (که فقط در کد
        بودند) کلاً از دید کاربر محو می‌شوند.
        قبلاً این تابع فقط دو دسته‌ی جدید («خرید اشتراک»،
        «قوانین و کپی‌رایت») را درج می‌کرد — که همین باعث شد بقیه‌ی
        دسته‌ها (علوم پایه، رفرنس، بانک سوال، برنامه، پروفایل، تیکت،
        مشکلات فنی) روی نصب واقعی ناپدید شوند. حالا همه‌ی دسته‌های
        DEFAULT_FAQS را sync می‌کند (upsert-by-question، سؤالات
        دستیِ ادمین در دسته‌های دیگر دست‌نخورده می‌مانند).
        """
        from faq import DEFAULT_FAQS
        for cat, items in DEFAULT_FAQS.items():
            for question, answer in items:
                existing = await self.faq.find_one({'question': question})
                if existing:
                    await self.faq.update_one(
                        {'_id': existing['_id']}, {'$set': {'answer': answer, 'category': cat}}
                    )
                else:
                    await self.faq_add(question, answer, cat)
        logger.info("❓ همه‌ی سؤالات پیش‌فرض FAQ همگام‌سازی شدند")


    async def faq_get_categories(self):
        return await self.faq.distinct('category') or []


    # ══════════════════════════════════════════════════
    #  🍴 موج C2 — Fork/Override (Global ← Intake Customize)
    #  مدل: جلسه/کتاب سراسری = BASE؛ نسخه‌ی اختصاصی ورودی = FORK
    #  (fork_of = شناسه‌ی base + intake = کد ورودی مالکِ fork).
    #  نمای دانشجو = baseهای forkنخورده ∪ forkهای ورودی خودش —
    #  جایگزینی آیتم‌محور؛ سراسری هرگز با ادیت ورودی‌خاص آلوده نمی‌شود.
    # ══════════════════════════════════════════════════

    async def session_superseded_by_fork(self, session_id: str, intake: str):
        """اگر برای جلسه‌ی پایه fork این ورودی موجود است → سند fork، وگرنه None."""
        if not intake:
            return None
        try:
            return await self.bs_sessions.find_one(
                {'fork_of': str(session_id), 'intake': intake})
        except Exception:
            return None


    async def book_superseded_by_fork(self, book_id: str, intake: str):
        """همان قاعده برای کتاب‌های رفرنس."""
        if not intake:
            return None
        try:
            return await self.ref_books.find_one(
                {'fork_of': str(book_id), 'intake': intake,
                 'archived': {'$ne': True}})
        except Exception:
            return None


    @staticmethod
    def bs_effective_view(sessions, allowed, lesson_intake_of):
        """⭐ ماموریت ۶ — قاعده‌ی واحد «نمای مؤثر» (برای همه‌ی لایه‌ها):
        sessions با allowed intakeها فیلتر می‌شوند؛ baseای که برای همان
        ورودی fork (غیرآرشیو) دارد سایه‌اندازی می‌شود. lesson_intake_of:
        {lesson_id: intake} برای ارث والد.
        همچنین اگر در یک درس، دو رکورد فعال با شماره و عنوان یکسان (مثلاً یکی بدون فیلد intake و یکی با فیلد intake همان ورودی) وجود داشته باشد،
        نسخه‌ی اختصاصی/جدیدتر جایگزین می‌شود تا هرگز دو جلسه‌ی تکراری نمایش داده نشود."""
        allowed = set(allowed if isinstance(allowed, (list, tuple, set)) else [allowed])

        def _si(s):
            explicit = str(s.get('intake') or '').strip() if ('intake' in s and s.get('intake') is not None) else ''
            if explicit:
                return explicit
            return str(lesson_intake_of.get(str(s.get('lesson_id') or ''), '') or '').strip()

        forked_bases = {str(s.get('fork_of')) for s in sessions
                        if s.get('fork_of') and not s.get('archived')
                        and _si(s) in allowed}
        filtered = [s for s in sessions
                    if _si(s) in allowed and str(s['_id']) not in forked_bases
                    and not s.get('archived')]

        # حذف تکرارهای ناخواسته در یک درس زمانی که دو سند هم‌شماره و هم‌عنوان در همان دید مؤثر افتاده‌اند
        # (مثلاً یکی با intake صریح و یکی ارث‌برنده از درس یا سراسری)
        by_num_topic = {}
        deduped = []
        for s in filtered:
            lid = str(s.get('lesson_id') or '')
            num = s.get('number')
            topic = str(s.get('topic') or '').strip()
            key = (lid, num, topic)
            if key not in by_num_topic:
                by_num_topic[key] = len(deduped)
                deduped.append(s)
            else:
                prev_idx = by_num_topic[key]
                prev_s = deduped[prev_idx]
                # اولویت با جلسه‌ای است که fork_of دارد یا intake صریح غیرخالی دارد
                s_score = (1 if s.get('fork_of') else 0, 1 if str(s.get('intake') or '').strip() else 0, str(s.get('created_at') or ''))
                p_score = (1 if prev_s.get('fork_of') else 0, 1 if str(prev_s.get('intake') or '').strip() else 0, str(prev_s.get('created_at') or ''))
                if s_score > p_score:
                    deduped[prev_idx] = s
        return deduped


    async def bs_get_sessions_effective(self, lesson_id: str, intake=None):
        """نمای مؤثر جلسات یک درس.
        حتی وقتی intake=None باشد (پیش‌نمایش ادمین ارشد در 📚 منابع)، قاعده‌ی
        bs_effective_view بر اساس intake خود درس اجرا می‌شود تا base و fork یا
        رکوردهای تکراری هم‌زمان به صورت دو جلسه‌ی تکراری نمایش داده نشوند."""
        sessions = await self.bs_get_sessions(lesson_id)
        lesson = await self.bs_get_lesson(lesson_id) or {}
        li = str(lesson.get('intake') or '').strip()
        li_map = {str(lesson_id): li}
        if intake is None:
            return self.bs_effective_view(sessions, li, li_map)
        return self.bs_effective_view(sessions, intake, li_map)


    @staticmethod
    def bs_logical_id(session_doc) -> str:
        """⭐ ماموریت ۶ — هویت پایدار منطقی: fork همان هویت base را دارد
        (fork_of یا _id). برای cache/کلید بیرونی لایه‌ها."""
        if not session_doc:
            return ''
        return str(session_doc.get('fork_of') or session_doc.get('_id', ''))


    async def bs_override_counts(self, lesson_id: str) -> dict:
        """⭐ ماموریت ۶ (R2) — شمارش overrideهای فعال هر جلسه‌ی سراسریِ
        این درس: {base_id: n}. برای نشان «⭐n» در سطل سراسری."""
        out = {}
        try:
            cursor = self.bs_sessions.find(
                {'lesson_id': str(lesson_id), 'fork_of': {'$type': 'string'},
                 'archived': {'$ne': True}},
                {'fork_of': 1})
            async for s in cursor:
                k = str(s.get('fork_of'))
                out[k] = out.get(k, 0) + 1
        except Exception:
            return {}
        return out


    async def bs_copy_content_item(self, content_id: str, to_session: str) -> str:
        """⭐ ماموریت ۶ — کپی افزودنیِ یک فایل سراسری به fork (واگرایی R5):
        وقتی فایلی فقط در base هست و عملیات روی fork انجام می‌شود."""
        c = await self.bs_get_content_item(content_id)
        if not c or not to_session:
            return ''
        r = await self.bs_content.insert_one({
            'session_id': to_session,
            'type': c.get('type', 'pdf'),
            'file_id': c.get('file_id', ''),
            'description': c.get('description', ''),
            'extra_info': c.get('extra_info', ''),
            'order': c.get('order', 0),
            'uploaded_at': utc_now_iso(),
            'downloads': 0,
            'notif_sent': True,
            'fork_of': str(c['_id']),
            'original_file_name': c.get('original_file_name', ''),
            'display_file_name': c.get('display_file_name', ''),
            'display_name': c.get('display_name', c.get('display_file_name', '')),
            'file_extension': c.get('file_extension', ''),
            'mime_type': c.get('mime_type', ''),
            'file_size': c.get('file_size', 0),
            'branding_enabled': c.get('branding_enabled', False),
        })
        return str(r.inserted_id)


    async def bs_merge_base_new_content(self, fork_id: str) -> int:
        """⭐ ماموریت ۶ (R5) — افزودن فایل‌های جدیدِ base به fork (فقط
        افزودنی؛ هیچ فایلی بازنویسی/حذف نمی‌شود). خروجی = تعداد افزوده‌شده."""
        fork = await self.bs_get_session(fork_id)
        if not fork or not fork.get('fork_of'):
            return 0
        base_id = fork['fork_of']
        have = {str(c.get('fork_of')) async for c in
                self.bs_content.find({'session_id': fork_id}, {'fork_of': 1})}
        added = 0
        for c in (await self.bs_get_content(base_id)):
            if str(c['_id']) not in have:
                await self.bs_copy_content_item(str(c['_id']), fork_id)
                added += 1
        return added


    async def ref_override_counts(self, subject_id: str) -> dict:
        """⭐ ماموریت ۶ (R2) — قرینه‌ی bs_override_counts برای کتاب‌ها."""
        out = {}
        try:
            cursor = self.ref_books.find(
                {'subject_id': str(subject_id), 'fork_of': {'$type': 'string'},
                 'archived': {'$ne': True}},
                {'fork_of': 1})
            async for b in cursor:
                k = str(b.get('fork_of'))
                out[k] = out.get(k, 0) + 1
        except Exception:
            return {}
        return out


    async def bs_base_new_content_count(self, fork_id: str) -> int:
        """⭐ ماموریت ۶ (R5) — چند فایلِ جدید سراسریِ base هست که این fork
        هنوز ندارد (واگرایی افزودنی). 0 = همگام/ fork نیست."""
        fork = await self.bs_get_session(fork_id)
        if not fork or not fork.get('fork_of'):
            return 0
        base_ids = {str(c['_id']) async for c in
                    self.bs_content.find({'session_id': fork['fork_of']}, {'_id': 1})}
        have = {str(c.get('fork_of')) async for c in
                self.bs_content.find({'session_id': fork_id}, {'fork_of': 1})}
        return len(base_ids - have)


    async def ref_get_books_effective(self, subject_id: str, intake=None):
        """نمای مؤثر کتاب‌های یک موضوع (همان قاعده‌ی جلسات)."""
        books = await self.ref_get_books(subject_id)
        if intake is None:
            return books
        allowed = set(intake if isinstance(intake, (list, tuple, set)) else [intake])
        subject = await self.ref_get_subject(subject_id) or {}
        si_root = subject.get('intake') or ''

        def _bi(b):
            return (b.get('intake') if 'intake' in b else si_root) or ''

        forked_bases = {str(b.get('fork_of')) for b in books
                        if b.get('fork_of') and not b.get('archived')
                        and _bi(b) in allowed and _bi(b) != ''}
        return [b for b in books
                if _bi(b) in allowed and str(b['_id']) not in forked_bases
                and not b.get('archived')]


    async def bs_ensure_override(self, session_id: str, intake: str):
        """⭐ ماموریت ۶ — Copy-on-Write: ساخت/بازیابی اتمیک override یک
        جلسه‌ی «سراسری» برای یک ورودی. برخلاف bs_fork_session قدیمی،
        ساخت سند fork با find_one_and_update(upsert) اتمیک است (R3) و
        کپی فایل‌ها فقط وقتی انجام می‌شود که fork هنوز محتوا ندارد
        (ایدمپوتنت — رقابتِ دو فراخوانی ⇒ فقط یک برنده محتوا را کپی
        می‌کند؛ بازنده سند موجود را می‌گیرد). فایل‌ها file_id تلگرام را
        «ارجاع» می‌کنند (بدون آپلود مجدد)، notif_sent=True تا اعلان
        تکراری نرود، downloads=0.
        خروجی: (fork_id, created) یا (None, False) اگر ورودی نامعتبر/
        جلسه سراسری نباشد. forkهای archived نادیده گرفته می‌شوند."""
        base = await self.bs_get_session(session_id)
        if not base or not intake:
            return None, False
        if (await self.session_intake(session_id)) != '':
            return None, False
        # fast-path بدون نوشتن: fork موجود را برگردان (بدون created)
        existing = await self.bs_sessions.find_one({
            'fork_of': session_id, 'intake': intake,
            'archived': {'$ne': True}})
        if existing:
            return str(existing['_id']), False
        # اتمیک: در رقابت فقط یک درج موفق است؛ بازنده سند موجود را می‌گیرد
        fork = await self.bs_sessions.find_one_and_update(
            {'fork_of': session_id, 'intake': intake},
            {'$setOnInsert': {
                'lesson_id': base.get('lesson_id', ''),
                'number': base.get('number', 0),
                'topic': base.get('topic', ''),
                'teacher': base.get('teacher', ''),
                'intake': intake, 'fork_of': session_id,
                'created_at': utc_now_iso(),
            }},
            upsert=True, return_document=True)
        new_sid = str(fork['_id'])
        # fork آرشیوشده (A/C قدیمی) کلید یکتای (fork_of,intake) را در اختیار
        # دارد ⇒ به‌جای درجِ ممنوع، همان احیا می‌شود (بدون حذف داده)
        if fork.get('archived'):
            await self.bs_sessions.update_one(
                {'_id': fork['_id']},
                {'$set': {'archived': False, 'resurrected_at': utc_now_iso()}})
            fork['archived'] = False
        # کپی محتوا فقط برای برنده‌ی واقعی (fork بدون فایل) — ایدمپوتنت
        have = await self.bs_content.count_documents({'session_id': new_sid})
        created = True
        if have == 0:
            for c in (await self.bs_get_content(session_id)):
                await self.bs_content.insert_one({
                    'session_id': new_sid,
                    'type': c.get('type', 'pdf'),
                    'file_id': c.get('file_id', ''),
                    'description': c.get('description', ''),
                    'extra_info': c.get('extra_info', ''),
                    'order': c.get('order', 0),
                    'uploaded_at': utc_now_iso(),
                    'downloads': 0,
                    'notif_sent': True,
                    'fork_of': str(c['_id']),
                    # carry file naming fields
                    'original_file_name': c.get('original_file_name', ''),
                    'display_file_name': c.get('display_file_name', ''),
                    'display_name': c.get('display_name', c.get('display_file_name', '')),
                    'file_extension': c.get('file_extension', ''),
                    'mime_type': c.get('mime_type', ''),
                    'file_size': c.get('file_size', 0),
                    'branding_enabled': c.get('branding_enabled', False),
                })
        else:
            created = False
        return new_sid, created


    async def bs_fork_session(self, session_id: str, intake: str):
        """سازگاری قدیمی (ماموریت ۶): فقط شناسه‌ی fork (None = نامعتبر)."""
        fork_id, _ = await self.bs_ensure_override(session_id, intake)
        return fork_id


    async def bs_unfork_session(self, fork_id: str):
        """بازگردانی به نسخه‌ی سراسری: حذف fork + محتوایش؛ خروجی = شناسه‌ی base."""
        fork = await self.bs_get_session(fork_id)
        if not fork or not fork.get('fork_of'):
            return False
        base_id = fork['fork_of']
        await self.bs_sessions.delete_one({'_id': fork['_id']})
        await self.bs_content.delete_many({'session_id': fork_id})
        return base_id


    async def ref_ensure_override(self, book_id: str, intake: str):
        """⭐ ماموریت ۶ — همان CoW اتمیک برای کتاب رفرنس (قرینه‌ی
        bs_ensure_override). خروجی: (fork_id, created)."""
        base = await self.ref_get_book(book_id)
        if not base or not intake:
            return None, False
        if (await self.ref_book_intake(book_id)) != '':
            return None, False
        existing = await self.ref_books.find_one({
            'fork_of': book_id, 'intake': intake,
            'archived': {'$ne': True}})
        if existing:
            return str(existing['_id']), False
        count = await self.ref_books.count_documents(
            {'subject_id': base.get('subject_id', '')})
        fork = await self.ref_books.find_one_and_update(
            {'fork_of': book_id, 'intake': intake},
            {'$setOnInsert': {
                'subject_id': base.get('subject_id', ''),
                'name': base.get('name', ''),
                'order': count,
                'intake': intake, 'fork_of': book_id,
                'created_at': utc_now_iso(),
            }},
            upsert=True, return_document=True)
        new_bid = str(fork['_id'])
        if fork.get('archived'):
            await self.ref_books.update_one(
                {'_id': fork['_id']},
                {'$set': {'archived': False, 'resurrected_at': utc_now_iso()}})
            fork['archived'] = False
        have = await self.ref_files.count_documents({'book_id': new_bid})
        created = True
        if have == 0:
            for f in (await self.ref_get_files(book_id)):
                await self.ref_files.insert_one({
                    'book_id': new_bid,
                    'lang': f.get('lang', 'fa'),
                    'volume': f.get('volume', 1),
                    'description': f.get('description', ''),
                    'file_id': f.get('file_id', ''),
                    'order': f.get('order', 0),
                    'uploaded_at': utc_now_iso(),
                    'downloads': 0,
                    'notif_sent': True,
                    'fork_of': str(f['_id']),
                    # carry file naming fields
                    'original_file_name': f.get('original_file_name', ''),
                    'display_file_name': f.get('display_file_name', ''),
                    'display_name': f.get('display_name', f.get('display_file_name', '')),
                    'file_extension': f.get('file_extension', ''),
                    'mime_type': f.get('mime_type', ''),
                    'file_size': f.get('file_size', 0),
                    'branding_enabled': f.get('branding_enabled', False),
                })
        else:
            created = False
        return new_bid, created


    async def ref_fork_book(self, book_id: str, intake: str):
        """سازگاری قدیمی (ماموریت ۶): فقط شناسه‌ی fork (None = نامعتبر)."""
        fork_id, _ = await self.ref_ensure_override(book_id, intake)
        return fork_id


    async def ref_unfork_book(self, fork_id: str):
        """بازگردانی کتاب به نسخه‌ی سراسری؛ خروجی = شناسه‌ی base."""
        fork = await self.ref_get_book(fork_id)
        if not fork or not fork.get('fork_of'):
            return False
        base_id = fork['fork_of']
        await self.ref_books.delete_one({'_id': fork['_id']})
        await self.ref_files.delete_many({'book_id': fork_id})
        return base_id


    async def bs_session_has_forks(self, session_id: str) -> bool:
        """آیا این جلسه نسخه‌ی اختصاصی (fork) دارد؟ — گارد حذف base (Q1)."""
        try:
            return bool(await self.bs_sessions.find_one(
                {'fork_of': str(session_id), 'archived': {'$ne': True}}))
        except Exception:
            return False


    async def ref_book_has_forks(self, book_id: str) -> bool:
        """همان گارد برای کتاب‌های رفرنس."""
        try:
            return bool(await self.ref_books.find_one(
                {'fork_of': str(book_id), 'archived': {'$ne': True}}))
        except Exception:
            return False


    # ── ابزار Move (بازتخصیص آیتم‌های قدیمیِ سراسری به یک ورودی) ──
    async def bs_move_lesson_intake(self, lesson_id: str, intake: str):
        """انتقال درس به سطل ورودی (فقط ادمین ارشد در سطح API صدا می‌زند).
        خروجی: (status, info) — status در {'ok','err'}."""
        lesson = await self.bs_get_lesson(lesson_id)
        if not lesson:
            return ('err', 'not_found')
        intake = intake or ''
        dup = await self.bs_lessons.find_one({
            'term': lesson.get('term', ''), 'name': lesson.get('name', ''),
            'intake': intake, '_id': {'$ne': lesson['_id']}})
        if dup:
            return ('err', 'duplicate')
        old = lesson.get('intake') or ''
        await self.bs_update_lesson(lesson_id, {'intake': intake})
        return ('ok', old)


    async def ref_move_subject_intake(self, subject_id: str, intake: str):
        subject = await self.ref_get_subject(subject_id)
        if not subject:
            return ('err', 'not_found')
        intake = intake or ''
        dup = await self.ref_subjects.find_one({
            'name': subject.get('name', ''), 'intake': intake,
            '_id': {'$ne': subject['_id']}})
        if dup:
            return ('err', 'duplicate')
        old = subject.get('intake') or ''
        await self.ref_update_subject(subject_id, {'intake': intake})
        return ('ok', old)



    # ══════════════════════════════════════════════════
    #  FIX جدید: سیستم گزارش ایراد سوال/جزوه (content_reports)
    # ══════════════════════════════════════════════════

    REPORT_REASONS = {
        'wrong_answer':  'پاسخ اشتباه',
        'wrong_option':  'گزینه اشتباه',
        'incomplete':    'متن ناقص',
        'broken_file':   'فایل خراب',
        'outdated':      'محتوای قدیمی',
        'other':         'سایر',
    }


    # ── §W9 — محدودیتِ نرخ و آستانهٔ تشدیدِ گزارش ────────────────────
    #
    #  اعداد از اندازه‌گیریِ واقعی آمده‌اند، نه حدس:
    #
    #  • نوشتنِ هر گزارش ~۲٫۶ms و ~۴۸۷ بایت است. یعنی یک کاربر می‌تواند
    #    در یک دقیقه ~۲۳٬۰۰۰ گزارش بنویسد. فضای دیسک گلوگاه نیست
    #    (۱۰٬۰۰۰ گزارش ≈ ۴٫۶MB).
    #
    #  • گلوگاهِ واقعی «فن‌اوتِ اعلان» است: هر گزارش به مدیر + ادمین‌های
    #    محتوا + بازبین‌ها + طراح پیام می‌فرستد. ۱۰۰ گزارشِ اسپم یعنی
    #    صدها پیامِ تلگرام و عملاً از کار افتادنِ کانالِ اطلاع‌رسانی.
    #
    #  پس سقف روی «تعداد گزارش در بازهٔ زمانی» گذاشته شده، نه روی حجم.
    #  ۲۰ گزارش در ساعت برای استفادهٔ سالم بیش از حد کافی است (کاربرِ
    #  عادی در یک جلسهٔ تمرین چند سؤال را گزارش می‌کند، نه ده‌ها تا) و
    #  هم‌زمان فن‌اوت را مهار می‌کند.
    #
    #  هر دو عدد طبق §۱۴ از تنظیماتِ سراسری خوانده می‌شوند تا بدونِ
    #  استقرارِ مجدد قابلِ تغییر باشند.
    REPORT_RATE_DEFAULT_MAX = 20        # گزارش
    REPORT_RATE_DEFAULT_WINDOW_MIN = 60  # دقیقه

    #  آستانهٔ تشدید. چون گزارشِ تکراریِ یک کاربر مسدود است، هر گزارش
    #  یعنی یک کاربرِ متمایز — پس این عدد واقعاً «چند نفر مستقل» است.
    #  یک سؤالِ سالم معمولاً ۰ تا ۱ گزارش می‌گیرد.
    REPORT_SEVERITY_DEFAULTS = {"flagged": 3, "high": 10, "critical": 20}

    async def report_rate_limit(self) -> tuple:
        """(سقف، پنجره به دقیقه) — ۰ یعنی محدودیت خاموش."""
        raw_max = await self.get_setting("report_rate_max",
                                         self.REPORT_RATE_DEFAULT_MAX)
        raw_win = await self.get_setting("report_rate_window_min",
                                         self.REPORT_RATE_DEFAULT_WINDOW_MIN)
        try:
            return max(0, int(raw_max)), max(1, int(raw_win))
        except (TypeError, ValueError):
            return (self.REPORT_RATE_DEFAULT_MAX,
                    self.REPORT_RATE_DEFAULT_WINDOW_MIN)

    async def report_recent_count(self, reporter_id: int,
                                  window_min: int) -> int:
        """شمارشِ گزارش‌های همین کاربر در بازهٔ اخیر."""
        since = (now_utc() - timedelta(minutes=int(window_min))).isoformat()
        return await self.content_reports.count_documents(
            {"reporter_id": int(reporter_id), "created_at": {"$gte": since}})

    async def report_severity_thresholds(self) -> dict:
        """آستانه‌های تشدید — قابلِ تنظیم از پنل (§۱۴)."""
        out = dict(self.REPORT_SEVERITY_DEFAULTS)
        for key in out:
            raw = await self.get_setting(f"report_severity_{key}", None)
            if raw is None:
                continue
            try:
                out[key] = max(1, int(raw))
            except (TypeError, ValueError):
                pass
        return out

    async def report_severity_of(self, open_count: int,
                                 thresholds: dict = None) -> str:
        """نگاشتِ تعدادِ گزارشِ باز به سطحِ شدت."""
        th = thresholds or await self.report_severity_thresholds()
        n = int(open_count or 0)
        if n >= th.get("critical", 20):
            return "critical"
        if n >= th.get("high", 10):
            return "high"
        if n >= th.get("flagged", 3):
            return "flagged"
        return "normal"

    async def create_content_report(self, target_type: str, target_id: str,
                                     reporter_id: int, reporter_name: str,
                                     reason: str, note: str = '',
                                     designer_id: int = None) -> int:
        """
        ثبت گزارش جدید — target_type: 'question' یا 'resource'.
        designer_id: آیدی طراح سوال (اگه target سوال باشد) برای اطلاع‌رسانی مستقیم.
        """
        # 🐛 §W8 — گزارشِ تکراریِ همان کاربر روی همان سؤال.
        #
        # پیش‌تر هر بار تپ روی «گزارش» یک رکوردِ تازه می‌ساخت، پس یک
        # دانشجو می‌توانست ده‌ها گزارشِ یکسان بسازد و آمارِ طراح را
        # بی‌معنا کند. حالا اگر گزارشِ بازِ همان کاربر روی همان هدف
        # وجود داشته باشد، همان برگردانده می‌شود (idempotent).
        existing = await self.content_reports.find_one({
            'target_type': target_type, 'target_id': target_id,
            'reporter_id': reporter_id,
            'status': {'$in': ['new', 'reviewing']},
        })
        if existing:
            try:
                return int(existing.get('report_id') or 0)
            except (TypeError, ValueError):
                return 0

        # §W9 — سقفِ نرخ. عمداً *بعد* از چکِ تکراری است تا تپِ دوباره روی
        # همان سؤال سهمیه مصرف نکند. برگرداندنِ ۰ یعنی «رد شد» و لایه‌ی
        # بالا پیام مناسب نشان می‌دهد.
        rate_max, window_min = await self.report_rate_limit()
        if rate_max:
            recent = await self.report_recent_count(reporter_id, window_min)
            if recent >= rate_max:
                logger.warning(
                    "report rate limit hit reporter_id=%s recent=%s max=%s",
                    reporter_id, recent, rate_max)
                return 0

        # 🔴 FIX-R1 (مورد ۵) — بوت‌استرپ شمارنده از max(report_id) موجود.
        #
        # ریشه‌ی «دکمه‌های بررسی/حل/رد بی‌اثر»: شمارنده‌ی اتمیک
        # db_counters روی دیتابیسی که قبلاً گزارش داشت (با طرحِ قدیمیِ
        # count+1) از ۱ شروع می‌شد؛ گزارشِ جدید report_id تکراری با
        # گزارشِ قدیمی می‌گرفت و find_one/update_one روی report_id به
        # سندِ قدیمی (اولین تطابق) می‌خورد، نه گزارشِ جدیدی که ادمین
        # روش کلیک کرده بود. نتیجه: پیام «ثبت شد» ولی هیچ تغییری نه در
        # ربات و نه در پنل. اینجا قبل از هر درج، شمارنده حداقل به
        # max(existing)+1 برداده می‌شود (idempotent و race-tolerant).
        try:
            highest = await self.content_reports.find_one(
                sort=[('report_id', -1)], projection={'report_id': 1})
            highest_id = int((highest or {}).get('report_id') or 0)
        except Exception:
            highest_id = 0
        if highest_id:
            await self.db_counters.update_one(
                {'_id': 'content_report_id', 'seq': {'$lt': highest_id}},
                {'$set': {'seq': highest_id}}
            )

        # شمارنده‌ی اتمی — `count_documents()+1` زیرِ دو گزارشِ هم‌زمان
        # شناسه‌ی تکراری می‌داد.
        seq = await self.db_counters.find_one_and_update(
            {'_id': 'content_report_id'}, {'$inc': {'seq': 1}},
            upsert=True, return_document=ReturnDocument.AFTER)
        report_id = int(seq.get('seq') or 1)
        await self.content_reports.insert_one({
            'report_id':    report_id,
            'target_type':  target_type,
            'target_id':    target_id,
            'reporter_id':  reporter_id,
            'reporter_name': reporter_name,
            'reason':       reason,
            'note':         note,
            'designer_id':  designer_id,
            'status':       'new',   # new, reviewing, resolved, rejected
            'created_at':   utc_now_iso(),
            'resolved_at':  None,
            'resolved_by':  None,
            'status_history': [
                {'status': 'new', 'at': utc_now_iso(), 'by': reporter_id}
            ],
        })
        return report_id


    async def get_content_report(self, report_id) -> dict:
        """🔍 FIX-R1 — جستجو با هر دو شکل: report_id (int/str عددی) یا ObjectId.

        گزارش‌های legacy ممکن است report_id نداشته باشند یا به‌صورت رشته
        ذخیره شده باشند؛ در آن حالت جستجو با _id (ObjectId hex) انجام
        می‌شود تا هیچ گزارشی «غیرقابل تغییر» نماند."""
        q = self._report_key_query(report_id)
        if q:
            return await self.content_reports.find_one(q)
        return None


    def _report_key_query(self, key) -> dict | None:
        """ساخت فیلتر یکتا برای یک گزارش: ObjectId یا report_id عددی.

        برخوردِ report_id های تکراری (legacy) همین‌جا خنثی می‌شود:
        جستجو بر اساس _id همیشه یکتاست؛ جستجو بر اساس report_id فقط
        وقتی استفاده می‌شود که _id در دسترس نباشد."""
        if key is None:
            return None
        if isinstance(key, ObjectId):
            return {'_id': key}
        s = str(key).strip()
        if not s:
            return None
        if ObjectId.is_valid(s) and not s.isdigit():
            # ObjectId hex (نه عدد خالص — «۱۲ رقمی تمام عددی» هم می‌تواند
            # report_id باشد، پس اول عددی امتحان می‌شود)
            try:
                return {'_id': ObjectId(s)}
            except Exception:
                pass
        try:
            return {'report_id': int(s)}
        except (TypeError, ValueError):
            return None


    async def get_content_reports(self, status: str = None, limit: int = 50,
                                  skip: int = 0) -> list:
        q = {'status': status} if status else {}
        return await self.content_reports.find(q).sort('created_at', -1) \
            .skip(max(0, int(skip))).limit(max(1, int(limit))).to_list(max(1, int(limit)))


    async def content_reports_count(self, status: str = None) -> int:
        q = {'status': status} if status else {}
        return await self.content_reports.count_documents(q)


    async def update_report_status(self, report_id, status: str,
                                   resolved_by: int = None) -> dict:
        """🔴 FIX-R1 (مورد ۵) — تغییر وضعیت با کلید یکتا + گزارش نتیجه.

        قبلاً (a) فقط با report_id (که می‌تواند تکراری/legacy باشد)
        آپدیت می‌کرد، (b) matched_count را چک نمی‌کرد و «موفق» الکی
        برمی‌گرداند و (c) هیچ سابقه‌ای از تغییر وضعیت نداشت.
        حالا: آپدیت با _id (یا report_id به‌عنوان fallback)، خروجی
        {'updated': bool, 'prev_status': str} و ثبت status_history."""
        if status not in ('new', 'reviewing', 'resolved', 'rejected'):
            raise ValueError('invalid_status')
        q = self._report_key_query(report_id)
        if not q:
            return {'updated': False, 'prev_status': None}
        prev = await self.content_reports.find_one(q)
        if not prev:
            return {'updated': False, 'prev_status': None}
        prev_status = prev.get('status', 'new')
        now = utc_now_iso()
        update_data = {
            'status': status,
            'status_changed_at': now,
            'status_changed_by': resolved_by,
        }
        if status in ('resolved', 'rejected'):
            update_data['resolved_at'] = now
            update_data['resolved_by'] = resolved_by
        else:
            # بازگشت از resolved/rejected به new/reviewing
            update_data['resolved_at'] = None
            update_data['resolved_by'] = None
        # سابقه‌ی تغییر وضعیت (audit) — سقف‌دار تا سند رشد نکند
        history = list(prev.get('status_history') or [])
        history.append({'status': status, 'at': now, 'by': resolved_by})
        update_data['status_history'] = history[-20:]
        res = await self.content_reports.update_one(
            {'_id': prev['_id']}, {'$set': update_data}
        )
        updated = bool(res.matched_count)
        # 👑 P1 — اولین گذار به resolved ⇒ پاداش «گزارش مفید» به گزارش‌دهنده
        # 🧠 N1.2 — سینک‌فیکس: گزارش‌دهنده هیچ‌جا نمی‌فهمید گزارشش بررسی
        # شده؛ حالا تک‌منبع زنده (Inbox + DM + Deep Link به «گزارش‌های من»).
        if updated and status == 'resolved' and prev_status != 'resolved' \
                and prev.get('reporter_id'):
            try:
                rep_uid = int(prev['reporter_id'])
                await self.prestige_event(rep_uid,
                    'report_useful', {'report_id': prev.get('report_id')})
            except Exception:
                pass
            try:
                await self.notify_user(rep_uid, 'report_resolved',
                    title='🩺 گزارشت بررسی شد',
                    body='گزارش محتوایی که فرستادی بررسی و تأیید شد '
                         '— چشم‌بازای حسرت ممنونه 🙏',
                    link='/me/reports',
                    dm=('🩺 <b>گزارشت بررسی شد</b>\n\n'
                        'گزارش محتوایی که فرستادی بررسی و تأیید شد. '
                        'از وسواس مثبتی که داری مرسی 🙏'))
            except Exception:
                pass
        return {'updated': updated, 'prev_status': prev_status}


    async def content_report_target_info(self, report_doc: dict) -> dict:
        """🔴 FIX-R1 (مورد ۵) — اطلاعات خوانا از «هدفِ» گزارش.

        به‌جای نمایش ObjectId خام، برای هر گزارش:
          • question: متن سؤال، درس، مبحث، گزینه‌ها، گزینه صحیح
          • resource: نام فایل (display_name)، نوع، درس، جلسه، استاد
        اگر هدف حذف شده باشد target_missing=True برمی‌گردد (نه خطا)."""
        out = {
            'target_missing': False,
            'title': '',
            'type_label': '',
            'lesson': '',
            'session': '',
            'teacher': '',
            'detail': '',
        }
        if not report_doc:
            return out
        ttype = report_doc.get('target_type')
        tid = report_doc.get('target_id') or ''
        if ttype == 'question':
            q = await self.get_question_by_id(tid) if tid else None
            if not q:
                out['target_missing'] = True
                return out
            options = q.get('options') or []
            correct = q.get('correct_answer')
            try:
                correct_idx = int(correct) if correct is not None else None
            except (TypeError, ValueError):
                correct_idx = None
            correct_text = ''
            if correct_idx is not None and 0 <= correct_idx < len(options):
                correct_text = str(options[correct_idx])
            out.update({
                'title': (q.get('question') or '')[:160],
                'type_label': 'سؤال',
                'lesson': q.get('lesson') or '',
                'session': q.get('topic') or '',
                'detail': f"گزینه صحیح ثبت‌شده: {correct_text or '—'}"
                          f" · {len(options)} گزینه",
                'question_options': [str(o)[:120] for o in options[:6]],
                'correct_answer': correct_text,
                'question_id': tid,
            })
            return out
        # resource (فایل آموزشی)
        item = await self.bs_get_content_item(tid) if tid else None
        if not item:
            out['target_missing'] = True
            return out
        path = await self.bs_get_content_full_path(tid) or {}
        ctype = (item.get('type') or '').strip()
        type_fa = {'video': 'ویدیو کلاس', 'ppt': 'پاورپوینت', 'pdf': 'جزوه PDF',
                   'note': 'نکات', 'test': 'تست', 'voice': 'ویس استاد'}.get(ctype, ctype or '—')
        name = (item.get('display_name') or item.get('display_file_name')
                or item.get('original_file_name')
                or item.get('description') or '')
        out.update({
            'title': (name or 'فایل بدون نام')[:160],
            'type_label': f'فایل ({type_fa})',
            'lesson': path.get('lesson_name') or '',
            'session': path.get('topic') or '',
            'teacher': path.get('teacher') or '',
            'detail': (item.get('description') or '').strip()[:300],
            'content_id': tid,
        })
        return out


    async def get_reviewers(self) -> list:
        """همه کاربرانی که نقش reviewer (خرخون) دارند — از منبع واحد RBAC"""
        if hasattr(self, 'user_ids_by_role'):
            return await self.user_ids_by_role('reviewer', limit=200)
        docs = await self.admin_roles.find({'role': 'reviewer'}).to_list(100)
        return [d['_id'] for d in docs]


    async def content_reports_stats(self) -> dict:
        new_count       = await self.content_reports.count_documents({'status': 'new'})
        reviewing_count = await self.content_reports.count_documents({'status': 'reviewing'})
        resolved_count  = await self.content_reports.count_documents({'status': 'resolved'})
        rejected_count  = await self.content_reports.count_documents({'status': 'rejected'})
        return {
            'new': new_count, 'reviewing': reviewing_count,
            'resolved': resolved_count, 'rejected': rejected_count,
        }


    async def faq_search_text(self, query_text: str, limit: int = 8) -> list:
        """جستجوی آزادِ متنی توی FAQ — برای Function Callingِ هوشیار."""
        if not query_text:
            return []
        # 🛡 AUDIT-R3 — ورودی کاربر «متن» است نه الگو: بدون escape، `.*` یک
        # full-scan بی‌نهایت و `(` خطای Mongo می‌ساخت (نمونه‌ی global_search).
        rx = {'$regex': re.escape(query_text), '$options': 'i'}
        return await self.faq.find(
            {'$or': [{'question': rx}, {'answer': rx}]}
        ).limit(limit).to_list(limit)


    # ══════════════════════════════════════════════════
    #  بانک فایل سؤال — metadata روی Telegram file_id
    # ══════════════════════════════════════════════════

    async def qbank_file_list(self, intake: str = None, limit: int = 100) -> list:
        """فهرست فایل‌های QBank با فیلتر صریح intake.

        None یعنی caller عمدی همه‌ی سطل‌ها را خواسته؛ رشته‌ی خالی فقط
        سطل سراسری است تا scope ناخواسته widen نشود.
        """
        query = {} if intake is None else {'intake': str(intake or '')}
        return await self.qbank_files.find(query).sort('created_at', -1).limit(limit).to_list(limit)


    async def qbank_file_get(self, file_id: str):
        try:
            return await self.qbank_files.find_one({'_id': ObjectId(file_id)})
        except Exception:
            return None


    async def qbank_file_add(self, *, intake: str, lesson: str, topic: str,
                             description: str, filename: str, mime_type: str,
                             size: int, telegram_file_id: str, uploaded_by: int,
                             file_type: str = 'document'):
        # کالکشن qbank_files تا تأیید مهاجرت واقعی حذف نمی‌شود؛ فقط نوشتن تازه بسته است.
        raise RuntimeError('legacy_qbank_frozen')


    async def qbank_file_delete(self, file_id: str) -> bool:
        try:
            result = await self.qbank_files.delete_one({'_id': ObjectId(file_id)})
            return bool(result.deleted_count)
        except Exception:
            return False


    async def qbank_file_mark_downloaded(self, file_id: str) -> bool:
        try:
            result = await self.qbank_files.update_one(
                {'_id': ObjectId(file_id)}, {'$inc': {'downloads': 1}})
            return bool(result.matched_count)
        except Exception:
            return False
