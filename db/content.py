# -*- coding: utf-8 -*-
"""
🗄️ HUMSYAR DB layer — 🌊 موج Q2/W12: ماژولارسازی database.py
این ماژول بخشی از mixinهای کلاس DB است؛ facade در database.py بدون تغییر
رفتار، همه‌ی importهای قبلی را سالم نگه می‌دارد.
"""
import os
import logging
import asyncio
import difflib
from datetime import datetime, timedelta
from bson import ObjectId
import motor.motor_asyncio

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
            'order': count, 'created_at': datetime.now().isoformat(),
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
        return await self.bs_sessions.find({'lesson_id': lesson_id}).sort('number', 1).to_list(200)


    async def bs_add_session(self, lesson_id: str, number: int, topic: str, teacher: str):
        existing = await self.bs_sessions.find_one({'lesson_id': lesson_id, 'number': number})
        if existing:
            await self.bs_sessions.update_one(
                {'_id': existing['_id']},
                {'$set': {'topic': topic, 'teacher': teacher}}
            )
            return str(existing['_id'])
        r = await self.bs_sessions.insert_one({
            'lesson_id': lesson_id, 'number': number, 'topic': topic,
            'teacher': teacher, 'created_at': datetime.now().isoformat(),
        })
        return str(r.inserted_id)


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


    async def bs_add_content(self, session_id: str, ctype: str, file_id: str,
                             description: str = '', extra_info: str = ''):
        count = await self.bs_content.count_documents({'session_id': session_id})
        r = await self.bs_content.insert_one({
            'session_id': session_id, 'type': ctype, 'file_id': file_id,
            'description': description, 'extra_info': extra_info,
            'order': count, 'uploaded_at': datetime.now().isoformat(), 'downloads': 0,
            'notif_sent': False,   # FIX جدید: برای batch نوتیف منابع جدید
        })
        return r.inserted_id


    # ══════════════════════════════════════════════════
    #  FIX جدید: نوتیف دسته‌ای منابع جدید (هر N ساعت)
    # ══════════════════════════════════════════════════

    async def get_unnotified_resources(self) -> list:
        """
        محتوای جدیدی که هنوز برای آن نوتیف ارسال نشده.
        FIX جدید: علاوه بر bs_content (منابع علوم‌پایه)، فایل‌های
        رفرنس (ref_files) هم اضافه شدند — طبق تصمیم صریح ادمین.
        بانک سوال (qbank_files) عمداً اضافه نشده و وارد این سیستم
        نمی‌شود. هر آیتم با کلید داخلی '_source' مشخص می‌شود که از
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
        try:
            await self.bs_content.delete_one({'_id': ObjectId(cid)})
        except Exception:
            pass


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
            'order': count, 'created_at': datetime.now().isoformat(),
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


    async def ref_add_book(self, subject_id: str, name: str):
        count = await self.ref_books.count_documents({'subject_id': subject_id})
        r = await self.ref_books.insert_one({
            'subject_id': subject_id, 'name': name,
            'order': count, 'created_at': datetime.now().isoformat(),
        })
        return r.inserted_id


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


    async def ref_add_file(self, book_id: str, lang: str, file_id: str,
                           volume: int = 1, description: str = ''):
        # FIX جدید: notif_sent اضافه شد تا این فایل وارد صف نوتیف
        # «منابع جدید» (همون jobـی که برای bs_content کار می‌کند) بشود.
        # چه فایل کاملاً جدید باشد چه جایگزین‌شدن یک جلد/زبان موجود،
        # از نظر دانشجو محتوای تازه است و باید در صف قرار بگیرد.
        existing = await self.ref_files.find_one({'book_id': book_id, 'lang': lang, 'volume': volume})
        if existing:
            await self.ref_files.update_one({'_id': existing['_id']}, {'$set': {
                'file_id': file_id, 'description': description,
                'uploaded_at': datetime.now().isoformat(),
                'notif_sent': False,
            }})
            return str(existing['_id'])
        count = await self.ref_files.count_documents({'book_id': book_id})
        r = await self.ref_files.insert_one({
            'book_id': book_id, 'lang': lang, 'volume': volume,
            'description': description, 'file_id': file_id,
            'uploaded_at': datetime.now().isoformat(), 'downloads': 0, 'order': count,
            'notif_sent': False,
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
        try:
            await self.ref_files.delete_one({'_id': ObjectId(fid)})
        except Exception:
            pass


    # ══════════════════════════════════════════════════
    #  بانک سوال
    # ══════════════════════════════════════════════════

    async def add_qbank_file(self, lesson: str, topic: str, file_id: str,
                             description: str, file_type: str = 'document',
                             intake: str = ''):
        r = await self.qbank_files.insert_one({
            'lesson': lesson, 'topic': topic, 'file_id': file_id,
            'file_type': file_type, 'description': description,
            'intake': intake or '',
            'upload_date': datetime.now().isoformat(), 'downloads': 0,
        })
        return r.inserted_id


    async def get_qbank_files(self, lesson: str = None, topic: str = None,
                              intake=None):
        q = {}
        if lesson: q['lesson'] = lesson
        if topic:  q['topic']  = topic
        q.update(self._intake_q(intake))
        return await self.qbank_files.find(q).sort('upload_date', -1).to_list(100)


    async def get_qbank_file(self, fid: str):
        try:
            return await self.qbank_files.find_one({'_id': ObjectId(fid)})
        except Exception:
            return None


    async def inc_qbank_download(self, fid: str, uid: int):
        try:
            await self.qbank_files.update_one({'_id': ObjectId(fid)}, {'$inc': {'downloads': 1}})
        except Exception:
            pass
        first_time = False
        try:
            first_time = (await self.stats_col.count_documents(
                {'user_id': uid, 'action': 'qbank_download',
                 'data.file_id': str(fid)})) == 0
        except Exception:
            pass
        await self.log(uid, 'qbank_download', {'file_id': fid})
        try:
            await self.prestige_event(uid, 'file_download',
                                      {'first_time': first_time})
        except Exception:
            pass


    async def delete_qbank_file(self, fid: str):
        try:
            await self.qbank_files.delete_one({'_id': ObjectId(fid)})
        except Exception:
            pass


    # ══════════════════════════════════════════════════
    #  سوالات تستی
    # ══════════════════════════════════════════════════

    async def add_question(self, lesson: str, topic: str, difficulty: str,
                           question: str, options: list, correct: int,
                           explanation: str, creator: int, auto_approve: bool = False,
                           chapter: str = '', tags: list = None,
                           question_image: str = None, answer_image: str = None,
                           intake: str = ''):
        """
        FIX/بهبود (بانک سوالات حرفه‌ای): فیلدهای جدید و اختیاری اضافه شد —
        chapter (فصل)، tags (تگ‌ها)، question_image/answer_image (شناسه
        فایل تصویر در تلگرام). همه‌ی این‌ها اختیاری و ۱۰۰٪ سازگار با
        نسخه‌ی قبلی هستند: هر فراخوانی قدیمی add_question بدون این
        آرگومان‌ها دقیقاً مثل قبل کار می‌کند.
        """
        r = await self.questions.insert_one({
            'lesson': lesson, 'topic': topic, 'difficulty': difficulty,
            'chapter': chapter or '', 'tags': tags or [],
            'question': question, 'options': options, 'correct_answer': correct,
            'explanation': explanation, 'creator_id': creator,
            'question_image': question_image, 'answer_image': answer_image,
            'intake': intake or '',
            'approved': auto_approve, 'created_at': datetime.now().isoformat(),
            'attempt_count': 0, 'correct_count': 0,
        })
        return r.inserted_id


    async def get_questions(self, lesson: str = None, topic: str = None,
                            difficulty: str = None, limit: int = 1,
                            exclude: list = None, intake=None):
        q = {'approved': True}
        if lesson:    q['lesson'] = lesson
        if topic and topic != 'همه': q['topic'] = topic
        if difficulty: q['difficulty'] = difficulty
        q.update(self._intake_q(intake))
        if exclude:
            try: q['_id'] = {'$nin': [ObjectId(i) for i in exclude]}
            except Exception: pass
        return await self.questions.find(q).limit(limit).to_list(limit)


    async def search_questions_text(self, query_text: str, limit: int = 10,
                                    intake=None) -> list:
        """جستجوی آزادِ متنی (نه فیلترِ درس/موضوع) — برای Function Callingِ هوشیار.
        🌊 C1.5 — پارامتر دفاعی intake: None=رفتار قدیمی (مصرف فعلی:
        ابزار admin_search_questions مخصوص مالک)؛ اگر روزی مسیر دانشجویی
        اضافه شد، باید student_intake_filter پاس بدهد."""
        if not query_text:
            return []
        rx = {'$regex': query_text, '$options': 'i'}
        return await self.questions.find(
            dict({'approved': True, '$or': [{'question': rx}, {'explanation': rx}]},
                 **self._intake_q(intake))
        ).limit(limit).to_list(limit)


    # ══════════════════════════════════════════════════
    #  ⚠️ قابلیتِ جدید: تشخیصِ سوالِ تکراری قبل از ثبت. عمداً بدونِ هوش
    #  مصنوعی پیاده شده (فقط شباهتِ متنیِ محلی با difflib) — چون این یه
    #  چکِ کیفیِ مهمه که نباید هیچ‌وقت به دردسترس‌بودنِ AI وابسته باشه؛
    #  حتی اگه سرویسِ AI کاملاً قطع باشه، این قابلیت بدونِ کم‌وکاستی کار
    #  می‌کنه.
    # ══════════════════════════════════════════════════

    async def find_similar_questions(self, lesson: str, topic: str, text: str,
                                      threshold: float = 0.72, limit: int = 3) -> list:
        if not text:
            return []
        candidates = await self.questions.find(
            {'lesson': lesson, 'topic': topic}, {'question': 1, 'options': 1, 'correct_answer': 1}
        ).to_list(500)
        scored = []
        norm = text.strip().lower()
        for c in candidates:
            other = (c.get('question') or '').strip().lower()
            if not other:
                continue
            ratio = difflib.SequenceMatcher(None, norm, other).ratio()
            if ratio >= threshold:
                scored.append((ratio, c))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [{'ratio': r, **c} for r, c in scored[:limit]]


    async def get_weak_questions(self, uid: int, limit: int = 1):
        user = await self.get_user(uid)
        weak = user.get('weak_topics', []) if user else []
        # 🌊 C1 — حتی سوالات ضعف هم در همان scope ورودی دانشجو هستند
        sf = self._intake_q(self.student_intake_filter(
            (user or {}).get('intake', '')))
        if not weak: return await self.get_questions(
            limit=limit, intake=self.student_intake_filter(
                (user or {}).get('intake', '')))
        q = {'approved': True, 'topic': {'$in': weak}}
        q.update(sf)
        return await self.questions.find(q
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
            {'approved': True}
        ).sort('last_daily_sent', 1).limit(1).to_list(1)
        if not q:
            return None
        chosen = q[0]
        await self.questions.update_one(
            {'_id': chosen['_id']},
            {'$set': {'last_daily_sent': datetime.now().isoformat()}}
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
            'lesson', dict({'approved': True}, **self._intake_q(intake))) if l])


    async def get_qbank_chapters(self, lesson: str, intake=None) -> list:
        """
        فصل‌های موجود برای یک درس — فقط فصل‌هایی که واقعاً سوال دارند.
        اگه هیچ سوالی فصل نداشته باشه (چون هنوز این فیلد پر نشده)
        لیست خالی برمی‌گرده و ربات این مرحله رو خودکار رد می‌کنه —
        کاملاً سازگار با سوالات قدیمی که فیلد chapter ندارند.
        🌊 C1.5 — intake اختیاری (None=رفتار قدیمی).
        """
        chapters = await self.questions.distinct(
            'chapter', dict({'approved': True, 'lesson': lesson,
                             'chapter': {'$nin': [None, '']}},
                            **self._intake_q(intake))
        )
        return sorted([c for c in chapters if c])


    async def get_qbank_topics(self, lesson: str, chapter: str = None, intake=None) -> list:
        """مباحث موجود برای درس (و در صورت انتخاب، فصل) — فقط مباحث دارای سوال.
        🌊 C1.5 — intake اختیاری (None=رفتار قدیمی)."""
        match = dict({'approved': True, 'lesson': lesson}, **self._intake_q(intake))
        if chapter:
            match['chapter'] = chapter
        topics = await self.questions.distinct('topic', match)
        return sorted([t for t in topics if t])


    async def get_qbank_difficulties(self, lesson: str, chapter: str = None, topic: str = None,
                                     intake=None) -> list:
        """سطوح سختیِ واقعاً موجود برای این فیلتر (برای مرحله‌ی اختیاری انتخاب سختی).
        🌊 C1.5 — intake اختیاری (None=رفتار قدیمی)."""
        match = dict({'approved': True, 'lesson': lesson}, **self._intake_q(intake))
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
        match = {'approved': True, 'lesson': lesson}
        match.update(self._intake_q(intake))
        if chapter: match['chapter'] = chapter
        if topic and topic != 'همه': match['topic'] = topic
        if difficulty: match['difficulty'] = difficulty
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


    async def pending_questions(self):
        return await self.questions.find({'approved': False}).to_list(50)


    async def approve_question(self, qid: str):
        qdoc = None
        try:
            qdoc = await self.questions.find_one({'_id': ObjectId(qid)})
            was_approved = bool((qdoc or {}).get('approved'))
            await self.questions.update_one({'_id': ObjectId(qid)}, {'$set': {'approved': True}})
        except Exception:
            was_approved = True
        # 👑 P1 — پاداش طراح سؤال (فقط کاربر واقعی و فقط در گذار اول به تأیید)
        # 🧠 N1.2 — سینک‌فیکس: رویداد موجود، اما خبر کاربری نداشت (نه DM
        # نه Inbox). خبر + پاداش از همین تک‌گذار خارج می‌شود (تک‌منبع).
        try:
            creator = (qdoc or {}).get('creator_id')
            ctype = (qdoc or {}).get('creator_type') or ''
            if not was_approved and creator and ctype not in ('bot', 'ai'):
                await self.prestige_event(int(creator), 'question_approved',
                                          {'qid': str(qid)})
        except Exception:
            pass
        # 🧠 N1.2 — خبر در try جدا: شکست XP نباید اعلان را ببلعد
        try:
            creator = (qdoc or {}).get('creator_id')
            ctype = (qdoc or {}).get('creator_type') or ''
            if not was_approved and creator and ctype not in ('bot', 'ai'):
                qlink = f'/learn/my-questions?hl={qid}'
                await self.notify_user(int(creator), 'question_approved',
                    title='✍️ سؤالت تأیید شد!',
                    body='سؤال پیشنهادیت به بانک سؤال اضافه شد '
                         '— از مشارکتت ممنونیم 💚',
                    link=qlink,
                    dm=('✍️ <b>سؤالت تأیید شد!</b>\n\n'
                        'سؤال پیشنهادیت به بانک سؤال اضافه شد '
                        '— از مشارکتت ممنونیم 💚'))
        except Exception:
            pass


    async def delete_question(self, qid: str):
        try:
            await self.questions.delete_one({'_id': ObjectId(qid)})
        except Exception: pass


    async def add_questions_bulk(self, items: list, creator: int,
                                 intake: str = '', auto_approve: bool = False) -> dict:
        """🌊 موج Q-Import — درج گروهی سؤال (مصرف: درون‌ریزی وب‌ادمین).
        هر آیتم با همان اعتبارسنجی add_question تک‌تکی: متن ≥۵، گزینه‌ها ۲..۶،
        ایندکس صحیح داخل محدوده، سختی easy|medium|hard. آیتم‌های معیوب رد و
        گزارش می‌شوند و بقیه درج می‌شوند (تراکنش همه‌یا‌هیچ نیست — گزارش دقیق).
        خروجی: {inserted, failed:[{i, error}]}"""
        docs, failed = [], []
        for i, it in enumerate(items or []):
            try:
                q   = (it.get('question') or '').strip()
                ops = [str(o).strip()[:300] for o in (it.get('options') or [])]
                ops = [o for o in ops if o]
                cor = it.get('correct', 0)
                dif = (it.get('difficulty') or '').strip()
                if len(q) < 5: raise ValueError('متن سؤال خیلی کوتاه است')
                if not (2 <= len(ops) <= 6): raise ValueError('گزینه‌ها باید بین ۲ تا ۶ باشند')
                if not isinstance(cor, int) or not (0 <= cor < len(ops)):
                    raise ValueError('گزینه‌ی صحیح خارج از محدوده است')
                if dif not in ('easy', 'medium', 'hard'):
                    raise ValueError('سختی نامعتبر است (easy|medium|hard)')
                docs.append({
                    'lesson': (it.get('lesson') or '').strip()[:80],
                    'topic': (it.get('topic') or '').strip()[:80],
                    'difficulty': dif, 'chapter': '', 'tags': [],
                    'question': q[:1000], 'options': ops, 'correct_answer': cor,
                    'explanation': (it.get('explanation') or '').strip()[:2000],
                    'creator_id': creator,
                    'question_image': None, 'answer_image': None,
                    'intake': intake or '', 'source': 'web_import',
                    'approved': bool(auto_approve),
                    'created_at': datetime.now().isoformat(),
                    'attempt_count': 0, 'correct_count': 0,
                })
            except Exception as e:
                failed.append({'i': i, 'error': str(e)})
        inserted = 0
        if docs:
            r = await self.questions.insert_many(docs)
            inserted = len(getattr(r, 'inserted_ids', docs))
        return {'inserted': inserted, 'failed': failed}


    async def update_question(self, qid: str, updates: dict) -> bool:
        """🌊 موج Q-Editor — ویرایش whitelistی سؤال (افزودنی؛ مصرف: وب‌ادمین
        «ویرایش پیش از تأیید»). فقط فیلدهای محتوایی قابل تغییرند — هویت
        سازنده/وضعیت تأیید/intake از این مسیر دست‌نخورده می‌ماند."""
        allowed = {'question', 'options', 'correct_answer', 'explanation',
                   'difficulty', 'lesson', 'topic'}
        safe = {k: v for k, v in (updates or {}).items() if k in allowed}
        if not safe:
            return False
        try:
            r = await self.questions.update_one({'_id': ObjectId(qid)},
                                                {'$set': safe})
            return getattr(r, 'modified_count', 0) > 0 or True
        except Exception:
            return False


    async def save_answer(self, uid: int, qid: str, selected: int, is_correct: bool):
        await self.answers.insert_one({
            'user_id': uid, 'question_id': qid,
            'selected': selected, 'is_correct': is_correct,
            'answered_at': datetime.now().isoformat(),
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

    async def add_schedule(self, stype: str, lesson: str, teacher: str,
                           date: str, time: str, location: str,
                           notes: str = '', group: str = 'هر دو', is_weekly: bool = False,
                           flex_type: str = 'fixed', flex_note: str = ''):
        """
        FIX جدید: flex_type — 'fixed' (ثابت) یا 'flexible' (منعطف).
        برای کلاس منعطف، flex_note آخرین زمان اعلام‌شده را نگه می‌دارد.
        """
        r = await self.schedules.insert_one({
            'type': stype, 'lesson': lesson, 'teacher': teacher,
            'date': date, 'time': time, 'location': location,
            'notes': notes, 'group': group, 'is_weekly': is_weekly,
            'flex_type': flex_type, 'flex_note': flex_note,
            'created_at': datetime.now().isoformat(), 'notified_days': [],
        })
        return r.inserted_id


    async def update_schedule_time(self, sid: str, new_date: str, new_time: str, note: str = ''):
        """
        FIX جدید: تغییر زمان یک کلاس منعطف — برای اعلام به‌روز شدن زمان
        برگزاری به دانشجویان استفاده می‌شود.
        """
        try:
            await self.schedules.update_one(
                {'_id': ObjectId(sid)},
                {'$set': {'date': new_date, 'time': new_time, 'flex_note': note,
                          'last_time_change': datetime.now().isoformat()}}
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
        allowed_fields = {'date', 'time', 'location', 'teacher', 'lesson', 'notes', 'group'}
        if field not in allowed_fields:
            return False
        try:
            result = await self.schedules.update_one(
                {'_id': ObjectId(sid)},
                {'$set': {field: value, 'last_edited_at': datetime.now().isoformat()}}
            )
            return result.matched_count > 0
        except Exception:
            logger.exception('update_schedule_field failed')
            return False


    async def update_schedule_full(self, sid: str, lesson: str, teacher: str,
                                    date: str, time: str, location: str,
                                    notes: str = '', group: str = 'هر دو',
                                    flex_type: str = 'fixed', flex_note: str = '') -> bool:
        """
        FIX جدید (بخش اول — ویرایش برنامه): ویرایش کامل همه فیلدهای یک
        برنامه‌ی موجود با یک UPDATE واحد. رکورد جدید ساخته نمی‌شود و
        ID برنامه دست‌نخورده باقی می‌ماند.
        """
        try:
            result = await self.schedules.update_one(
                {'_id': ObjectId(sid)},
                {'$set': {
                    'lesson': lesson, 'teacher': teacher, 'date': date, 'time': time,
                    'location': location, 'notes': notes, 'group': group,
                    'flex_type': flex_type, 'flex_note': flex_note,
                    'last_edited_at': datetime.now().isoformat(),
                }}
            )
            return result.matched_count > 0
        except Exception:
            logger.exception('update_schedule_full failed')
            return False


    async def get_schedules(self, stype: str = None, upcoming: bool = True, group: str = None):
        from utils import now_tehran
        q = {}
        if stype:    q['type'] = stype
        if upcoming: q['date'] = {'$gte': now_tehran().strftime('%Y-%m-%d')}
        if group:
            q['$or'] = [
                {'group': group},
                {'group': 'هر دو'},
                {'group': ''},
                {'group': None},
                {'group': {'$exists': False}},
            ]
        return await self.schedules.find(q).sort('date', 1).to_list(200)


    async def delete_schedule(self, sid: str):
        try:
            await self.schedules.delete_one({'_id': ObjectId(sid)})
        except Exception: pass


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
        normalized_group = str(group or '').strip()
        if normalized_group:
            query['$or'] = [
                {'group': normalized_group},
                {'group': 'هر دو'},
                {'group': ''},
                {'group': None},
                {'group': {'$exists': False}},
            ]
        return await self.schedules.find(query).sort('date', 1).to_list(20)


    async def get_exams_for_reminder(self, remind_days: int):
        target = (datetime.now() + timedelta(days=remind_days)).strftime('%Y-%m-%d')
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
    #  FAQ
    # ══════════════════════════════════════════════════

    async def faq_get_all(self):
        return await self.faq.find({}).sort('order', 1).to_list(100)


    async def faq_add(self, question: str, answer: str, category: str = 'عمومی'):
        count = await self.faq.count_documents({})
        await self.faq.insert_one({
            'question': question, 'answer': answer, 'category': category,
            'order': count, 'created_at': datetime.now().isoformat(),
        })


    async def faq_delete(self, fid: str):
        try:
            await self.faq.delete_one({'_id': ObjectId(fid)})
        except Exception: pass


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
                {'fork_of': str(book_id), 'intake': intake})
        except Exception:
            return None


    async def bs_get_sessions_effective(self, lesson_id: str, intake=None):
        """نمای مؤثر جلسات یک درس. intake=None ⇒ همه (پیش‌نمایش ادمین،
        رفتار قدیمی)؛ لیست/رشته ⇒ دید آن scope: آیتم‌های در scope، با
        این تفاوت که base‌ای که برای آن ورودی fork دارد حذف و fork
        جایگزین می‌شود."""
        sessions = await self.bs_get_sessions(lesson_id)
        if intake is None:
            return sessions
        allowed = set(intake if isinstance(intake, (list, tuple, set)) else [intake])
        lesson = await self.bs_get_lesson(lesson_id) or {}
        li = lesson.get('intake') or ''

        def _si(s):
            return (s.get('intake') if 'intake' in s else li) or ''

        forked_bases = {str(s.get('fork_of')) for s in sessions
                        if s.get('fork_of') and _si(s) in allowed and _si(s) != ''}
        return [s for s in sessions
                if _si(s) in allowed and str(s['_id']) not in forked_bases]


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
                        if b.get('fork_of') and _bi(b) in allowed and _bi(b) != ''}
        return [b for b in books
                if _bi(b) in allowed and str(b['_id']) not in forked_bases]


    async def bs_fork_session(self, session_id: str, intake: str):
        """ساخت/بازیابی fork ورودی‌خاص از یک جلسه‌ی «سراسری»:
        کپی جلسه + کپی همه‌ی محتوایش (با notif_sent=True تا دوباره‌اعلان
        نشود) و downloads=0. ایدمپوتنت: fork موجود = همان برمی‌گردد.
        فقط base سراسری fork می‌شود؛ خروجی None یعنی نامعتبر."""
        base = await self.bs_get_session(session_id)
        if not base or not intake:
            return None
        if (await self.session_intake(session_id)) != '':
            return None
        existing = await self.bs_sessions.find_one(
            {'fork_of': session_id, 'intake': intake})
        if existing:
            return str(existing['_id'])
        r = await self.bs_sessions.insert_one({
            'lesson_id': base.get('lesson_id', ''),
            'number': base.get('number', 0),
            'topic': base.get('topic', ''),
            'teacher': base.get('teacher', ''),
            'intake': intake, 'fork_of': session_id,
            'created_at': datetime.now().isoformat(),
        })
        new_sid = str(r.inserted_id)
        for c in (await self.bs_get_content(session_id)):
            await self.bs_content.insert_one({
                'session_id': new_sid,
                'type': c.get('type', 'pdf'),
                'file_id': c.get('file_id', ''),
                'description': c.get('description', ''),
                'extra_info': c.get('extra_info', ''),
                'order': c.get('order', 0),
                'uploaded_at': datetime.now().isoformat(),
                'downloads': 0,
                'notif_sent': True,
                'fork_of': str(c['_id']),
            })
        return new_sid


    async def bs_unfork_session(self, fork_id: str):
        """بازگردانی به نسخه‌ی سراسری: حذف fork + محتوایش؛ خروجی = شناسه‌ی base."""
        fork = await self.bs_get_session(fork_id)
        if not fork or not fork.get('fork_of'):
            return False
        base_id = fork['fork_of']
        await self.bs_sessions.delete_one({'_id': fork['_id']})
        await self.bs_content.delete_many({'session_id': fork_id})
        return base_id


    async def ref_fork_book(self, book_id: str, intake: str):
        """ساخت/بازیابی fork ورودی‌خاص از یک کتاب «سراسری» (کپی کتاب+فایل‌ها)."""
        base = await self.ref_get_book(book_id)
        if not base or not intake:
            return None
        if (await self.ref_book_intake(book_id)) != '':
            return None
        existing = await self.ref_books.find_one(
            {'fork_of': book_id, 'intake': intake})
        if existing:
            return str(existing['_id'])
        count = await self.ref_books.count_documents(
            {'subject_id': base.get('subject_id', '')})
        r = await self.ref_books.insert_one({
            'subject_id': base.get('subject_id', ''),
            'name': base.get('name', ''),
            'order': count,
            'intake': intake, 'fork_of': book_id,
            'created_at': datetime.now().isoformat(),
        })
        new_bid = str(r.inserted_id)
        for f in (await self.ref_get_files(book_id)):
            await self.ref_files.insert_one({
                'book_id': new_bid,
                'lang': f.get('lang', 'fa'),
                'volume': f.get('volume', 1),
                'description': f.get('description', ''),
                'file_id': f.get('file_id', ''),
                'order': f.get('order', 0),
                'uploaded_at': datetime.now().isoformat(),
                'downloads': 0,
                'notif_sent': True,
                'fork_of': str(f['_id']),
            })
        return new_bid


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
                {'fork_of': str(session_id)}))
        except Exception:
            return False


    async def ref_book_has_forks(self, book_id: str) -> bool:
        """همان گارد برای کتاب‌های رفرنس."""
        try:
            return bool(await self.ref_books.find_one(
                {'fork_of': str(book_id)}))
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


    async def qbank_move_file_intake(self, file_id: str, intake: str):
        intake = intake or ''
        try:
            item = await self.qbank_files.find_one({'_id': ObjectId(file_id)})
            if not item:
                return ('err', 'not_found')
            old = item.get('intake') or ''
            await self.qbank_files.update_one(
                {'_id': ObjectId(file_id)}, {'$set': {'intake': intake}})
            return ('ok', old)
        except Exception:
            return ('err', 'not_found')



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


    async def create_content_report(self, target_type: str, target_id: str,
                                     reporter_id: int, reporter_name: str,
                                     reason: str, note: str = '',
                                     designer_id: int = None) -> int:
        """
        ثبت گزارش جدید — target_type: 'question' یا 'resource'.
        designer_id: آیدی طراح سوال (اگه target سوال باشد) برای اطلاع‌رسانی مستقیم.
        """
        count = await self.content_reports.count_documents({})
        report_id = count + 1
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
            'created_at':   datetime.now().isoformat(),
            'resolved_at':  None,
            'resolved_by':  None,
        })
        return report_id


    async def get_content_report(self, report_id: int):
        return await self.content_reports.find_one({'report_id': report_id})


    async def get_content_reports(self, status: str = None, limit: int = 50) -> list:
        q = {'status': status} if status else {}
        return await self.content_reports.find(q).sort('created_at', -1).to_list(limit)


    async def update_report_status(self, report_id: int, status: str, resolved_by: int = None):
        prev = None
        try:
            prev = await self.content_reports.find_one({'report_id': report_id})
        except Exception:
            pass
        update_data = {'status': status}
        if status in ('resolved', 'rejected'):
            update_data['resolved_at'] = datetime.now().isoformat()
            update_data['resolved_by'] = resolved_by
        await self.content_reports.update_one(
            {'report_id': report_id}, {'$set': update_data}
        )
        # 👑 P1 — اولین گذار به resolved ⇒ پاداش «گزارش مفید» به گزارش‌دهنده
        # 🧠 N1.2 — سینک‌فیکس: گزارش‌دهنده هیچ‌جا نمی‌فهمید گزارشش بررسی
        # شده؛ حالا تک‌منبع زنده (Inbox + DM + Deep Link به «گزارش‌های من»).
        try:
            if (status == 'resolved'
                    and (prev or {}).get('status') != 'resolved'
                    and (prev or {}).get('reporter_id')):
                rep_uid = int(prev['reporter_id'])
                await self.prestige_event(rep_uid,
                    'report_useful', {'report_id': report_id})
        except Exception:
            pass
        # 🧠 N1.2 — خبر در try جدا (ایزوله از موتور پرستیژ)
        try:
            if (status == 'resolved'
                    and (prev or {}).get('status') != 'resolved'
                    and (prev or {}).get('reporter_id')):
                rep_uid = int(prev['reporter_id'])
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


    async def get_reviewers(self) -> list:
        """همه کاربرانی که نقش reviewer (خرخون) دارند"""
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
        rx = {'$regex': query_text, '$options': 'i'}
        return await self.faq.find(
            {'$or': [{'question': rx}, {'answer': rx}]}
        ).limit(limit).to_list(limit)
