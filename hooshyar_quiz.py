# -*- coding: utf-8 -*-
"""
📚 QUIZ-PDF — «آزمون‌ساز هوشمند از روی PDF» برای هوشیار (فاز A).

جریان: آپلود PDF ← اعتبارسنجی ← استخراج متن هر صفحه (فارسی‌زیاد)
← ساختار مباحث (AI + fallback هیوریستیک) ← انتخاب محدوده/تنظیمات
← تولید سؤال ساختاریافته (JSON + schema) ← verification مخالف‌خوان
← ارسال Quiz Poll غیرناشناس ← poll_answer ← بازخورد فوری ← گزارش پایان.

محدودیت‌های تلگرام (تاییدشده از مستندات رسمی Bot API + PTB 21.3):
  • سؤال ۱-۳۰۰ کاراکتر، گزینه ۱-۱۰۰ کاراکتر، explanation ۰-۲۰۰ کاراکتر
    (حداکثر ۲ خط جدید) — فقط یک گزینه درست در حالت quiz.
  • poll_answer فقط برای poll غیرناشناس می‌آید و فقط poll_id/user/
    option_ids دارد ⇒ نگاشت telegram_poll_id → سؤال در DB (ایندکس یکتا).
  • getFile سقف دانلود ۲۰ مگابایت دارد (Bot API ابری).
"""
import asyncio
import hashlib
import io
import logging
import random
import re
import time
import unicodedata
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest, RetryAfter, Forbidden
from telegram.ext import ContextTypes

from database import db
from utils import ADMIN_ID, esc as _esc
from time_utils import utc_now_iso

logger = logging.getLogger(__name__)

# ── سقف‌ها (همگی از bot_settings قابل تغییر؛ پیش‌فرض محافظه‌کارانه) ──
DEFAULTS = {
    'quiz_pdf_enabled': True,             # کل قابلیت
    'quiz_max_pdf_mb': 20,                # سقف دانلود Bot API هم ۲۰ است
    'quiz_max_pages': 400,                # سقف تعداد صفحه
    'quiz_max_questions_per_session': 50, # سقف سؤال هر نشست
    'quiz_daily_question_limit': 150,     # سقف سؤال تولیدی روزانه هر کاربر
    'quiz_max_docs_per_user': 10,         # سقف اسناد ذخیره‌شده
    'quiz_doc_retention_days': 90,        # حذف خودکار اسناد قدیمی
    'quiz_batch_questions': 5,            # سؤال در هر فراخوانی AI
    'quiz_chunk_chars': 9000,             # حداکثر کاراکتر منبع در هر فراخوانی
}

# سقف‌های تلگرام (مستندات رسمی — نباید تغییر کنند)
TG_MAX_QUESTION = 300
TG_MAX_OPTION = 100
TG_MAX_EXPLANATION = 200

# سقف ارسال پیام در هر ثانیه به یک چت (throttle)
_SEND_GAP = 1.05
_last_send_at: dict = {}

# سمافور سراسری تماس با AI (جلوگیری از سوختن بودجه توسط یک کاربر)
_AI_SEMAPHORE = asyncio.Semaphore(3)

PersianLetters = re.compile(r'[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]')


async def _setting(key: str):
    return await db.get_setting(key, DEFAULTS[key])


# ══════════════════════════════════════════════════
#  ۱) اعتبارسنجی و پردازش PDF
# ══════════════════════════════════════════════════

def _normalize_persian(text: str) -> str:
    """نرمال‌سازی متن فارسی PDF:
    • NFKC: حروف‌شکل‌های عربی (presentation forms) → حروف پایه
    • ي→ی و ك→ک (عربی → فارسی)
    • حذف tatweel و کاراکترهای کنترلی؛ جمع‌کردن فاصله‌ها.
    ZWNJ (نیم‌فاصله) حفظ می‌شود."""
    if not text:
        return ''
    t = unicodedata.normalize('NFKC', text)
    t = t.replace('\u064A', '\u06CC').replace('\u0643', '\u06A9')  # ي→ی ك→ک
    t = t.replace('\u0640', '')                                     # tatweel
    t = ''.join(ch for ch in t if ch == '\u200d' or ord(ch) >= 32)  # کنترلی‌ها
    t = re.sub(r'[ \t\u00a0]+', ' ', t)
    t = re.sub(r'\n{3,}', '\n\n', t)
    return t.strip()


# واژه‌های پرتکرار فارسی برای تشخیص جهت متن (چندحرفی — «و» تک‌حرفی
# در هر دو جهت دیده می‌شود و امن نیست)
_FA_LOGICAL_MARKERS = ('است', ' که ', ' در ', ' از ', 'این', 'برای',
                       'می‌شود', 'دارد', 'می‌', 'های', 'شد', 'بود', 'هر ', 'با ')


def _logical_score(s: str) -> int:
    return sum(s.count(w) for w in _FA_LOGICAL_MARKERS)


def _fix_visual_rtl_line(line: str) -> str:
    """اگر خط در «ترتیب دیداری» (visual order) است → به منطقی برمی‌گرداند.

    برخی مولدهای PDF (InDesign و ابزارهای قدیمی) حروف فارسی را معکوس
    می‌نویسند؛ pypdf همان معکوس را بیرون می‌دهد. معیار: امتیاز واژه‌های
    پرتکارِ متعارف در متن اصلی در برابر وارونه. اعداد/لاتینِ داخل خط
    پس از وارونه‌سازی دوباره به‌ترتیب خودشان برمی‌گردند."""
    if not PersianLetters.search(line):
        return line
    rev = line[::-1]
    # بازگرداندن اعداد و حروف لاتین (در وارونه‌سازی قربانی می‌شوند)
    rev = re.sub(r'[A-Za-z0-9۰-۹٠-٩]+',
                 lambda m: m.group(0)[::-1], rev)
    return rev if _logical_score(rev) > _logical_score(line) else line


def _fix_visual_rtl(text: str) -> str:
    """اعمال تعمیر جهت، خط به خط (فقط خط‌های فارسی)."""
    if not text or not PersianLetters.search(text):
        return text
    return '\n'.join(_fix_visual_rtl_line(ln) for ln in text.split('\n'))


def _page_quality(text: str) -> float:
    """امتیاز کیفیت استخراج یک صفحه (۰..۱):
    نسبت حروف فارسی/لاتین به کل + سلامت کلمات (طول متوسط)."""
    if not text:
        return 0.0
    n = len(text)
    letters = len(re.findall(r'[\u0600-\u06FFA-Za-z]', text))
    bad = text.count('\ufffd') + text.count('�')
    words = [w for w in text.split() if len(w) >= 2]
    avg_w = (sum(len(w) for w in words) / len(words)) if words else 0
    ratio = letters / max(n, 1)
    score = min(1.0, ratio * 1.6) * 0.6 + min(1.0, avg_w / 4.0) * 0.4
    if bad:
        score = max(0.0, score - 0.3 * min(1.0, bad / 20))
    return round(score, 3)


class _PdfError(Exception):
    pass


async def process_document(bot, doc_id, owner_id: int, raw: bytes,
                           status_message=None) -> bool:
    """پردازش کامل سند با پیام پیشرفت زنده. True=آماده شد."""
    max_mb = int(await _setting('quiz_max_pdf_mb'))
    max_pages = int(await _setting('quiz_max_pages'))

    async def _progress(pct: int, text: str):
        if not status_message:
            return
        try:  # ویرایشِ حداکثر هر ۲ ثانیه — اسپم ادیت نکنیم
            now = time.monotonic()
            if pct < 99 and now - process_document._last_edit.get(doc_id, 0) < 2:
                return
            process_document._last_edit[doc_id] = now
            await status_message.edit_text(f"⏳ {text} … {pct}٪")
        except Exception:
            pass

    process_document._last_edit = getattr(process_document, '_last_edit', {})

    try:
        if raw[:5] != b'%PDF-':
            await db.quiz_fail_document(doc_id, 'not_pdf')
            await _progress(100, '❌ این فایل PDF نیست.')
            return False
        if len(raw) > max_mb * 1024 * 1024:
            await db.quiz_fail_document(doc_id, 'too_big')
            await _progress(100, f'❌ حجم فایل از سقف {max_mb} مگابایت بیشتر است.')
            return False

        await _progress(10, 'در حال باز کردن فایل')
        try:
            pages = await asyncio.to_thread(_extract_pdf_pages_sync, raw)
        except _PdfError as e:
            reason = str(e)
            await db.quiz_fail_document(doc_id, reason)
            msg = ('❌ این PDF رمزدار است — اول رمزش را بردار و دوباره بفرست.'
                   if reason == 'encrypted' else
                   '❌ فایل PDF قابل خواندن نیست (خراب است).')
            await _progress(100, msg)
            return False
        except Exception:
            logger.exception('pdf extract failed')
            await db.quiz_fail_document(doc_id, 'extract_error')
            await _progress(100, '❌ در خواندن PDF خطایی پیش آمد.')
            return False

        if len(pages) > max_pages:
            await db.quiz_fail_document(doc_id, 'too_many_pages')
            await _progress(100, f'❌ سقف صفحات مجاز {max_pages} است؛ این فایل {len(pages)} صفحه دارد.')
            return False
        if not pages:
            await db.quiz_fail_document(doc_id, 'no_pages')
            await _progress(100, '❌ صفحه‌ای در فایل پیدا نشد.')
            return False

        # کیفیت کل
        total_chars = sum(p['chars'] for p in pages)
        good_pages = [p for p in pages if p['chars'] >= 60]
        avg_q = (sum(_page_quality(p['text']) for p in pages) / len(pages)
                 if pages else 0)
        per_fa = len(good_pages) / len(pages)
        quality = round(avg_q * 0.6 + per_fa * 0.4, 3)

        if total_chars < 400 or quality < 0.22:
            # به احتمال زیاد اسکن‌شده است (تصویر، بدون متن قابل استخراج)
            await db.quiz_fail_document(
                doc_id, 'scanned_or_low_quality')
            await _progress(100, (
                '❌ از این PDF متن قابل استخراج نبود (احتمالاً اسکن/عکس است).\n'
                '📄 لطفاً نسخه‌ی «متنی» جزوه را بفرست؛ خواندن اسکن فعلاً '
                'پشتیبانی نمی‌شود.'))
            return False

        await _progress(35, 'متن استخراج شد — در حال تشخیص مباحث')

        # ساختار مباحث: AI با fallback هیوریستیک
        topics = await build_topic_structure(pages, owner_id)
        # انتساب هر صفحه به مبحث
        for p in pages:
            p['topic_id'] = _topic_of(topics, p['no'])
        await _progress(70, f'{len(topics)} مبحث تشخیص داده شد — ذخیره')

        note = ''
        if quality < 0.45:
            note = 'کیفیت استخراج متن متوسط بود؛ بعضی سؤال‌ها ممکن است دقیق نباشند.'
        ok = await db.quiz_finish_document(doc_id, pages, topics, quality, note)
        await _progress(100, '✅ سند آماده شد!')
        return bool(ok)
    except Exception:
        logger.exception('process_document failed')
        await db.quiz_fail_document(doc_id, 'internal')
        return False


def _extract_pdf_pages_sync(raw: bytes):
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(raw))
    if reader.is_encrypted:
        raise _PdfError('encrypted')
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            txt = page.extract_text() or ''
        except Exception:
            txt = ''
        txt = _fix_visual_rtl(_normalize_persian(txt))
        pages.append({'no': i, 'text': txt, 'chars': len(txt)})
    return pages


# ══════════════════════════════════════════════════
#  ۲) ساختار مباحث
# ══════════════════════════════════════════════════

def _topic_of(topics: list, page_no: int) -> int:
    """مبحثِ دارای بازه‌ی شامل این صفحه (اولین match)."""
    for t in topics:
        if t['page_start'] <= page_no <= t['page_end']:
            return t['id']
    return topics[0]['id'] if topics else 0


def _heuristic_topics(pages: list, max_topics: int = 30) -> list:
    """بدون AI: تقسیم به بلوک‌های ~۱۰ صفحه‌ای."""
    n = len(pages)
    size = max(5, (n + max_topics - 1) // max_topics)
    out = []
    for i in range(0, n, size):
        out.append({'id': len(out), 'title': f'صفحات {pages[i]["no"]}–{pages[min(i + size - 1, n - 1)]["no"]}',
                    'page_start': pages[i]['no'],
                    'page_end': pages[min(i + size - 1, n - 1)]['no']})
    return out


TOPICS_SCHEMA = {
    'type': 'OBJECT',
    'properties': {
        'topics': {
            'type': 'ARRAY',
            'items': {
                'type': 'OBJECT',
                'properties': {
                    'title': {'type': 'STRING'},
                    'page_start': {'type': 'INTEGER'},
                    'page_end': {'type': 'INTEGER'},
                },
                'required': ['title', 'page_start', 'page_end'],
            },
        },
    },
    'required': ['topics'],
}


async def build_topic_structure(pages: list, user_id: int) -> list:
    """فهرست مباحث با بازه صفحه — از روی «نقشه‌ی صفحات» (شروع هر صفحه).

    ورودی AI سبک است (سرِ هر صفحه)، پس حتی جزوه‌ی ۴۰۰ صفحه‌ای هم در یک
    فراخوانی ساختار می‌گیرد. در خطا/خروجی نامعتبر → هیوریستیک."""
    max_topics = 30
    try:
        page_map = []
        for p in pages:
            head = ' '.join(p['text'].split())[:170]
            if head:
                page_map.append(f"صفحه {p['no']}: {head}")
        prompt = (
            'نقشه‌ی صفحات یک جزوه‌ی درسی (طبقه‌بندی نشده) در پایین آمده است.\n'
            'وظیفه: فهرست «مباحث/فصل‌های» این جزوه را با بازه‌ی صفحه‌ی هرکدام استخراج کن.\n'
            'قواعد:\n'
            f'• بین ۳ تا {max_topics} مبحث؛ عنوان فارسی کوتاه و معنادار (مثل «فیزیولوژی سلول»).\n'
            '• بازه‌ها پیوسته و مرتب از صفحه‌ی ۱ تا آخر، بدون همپوشانی و بدون شکاف.\n'
            '• فقط از محتوای همین جزوه؛ مبحث از خودت نساز.\n\n'
            + '\n'.join(page_map[:400]))
        from ai_solver import generate_structured_json, get_ai_config, AIError
        cfg = await get_ai_config()
        t0 = time.monotonic()
        async with _AI_SEMAPHORE:
            data = await generate_structured_json(
                prompt, TOPICS_SCHEMA, purpose='ساختار مباحث',
                max_tokens=4096,
                system_prompt='تو دستیار تحلیل ساختار جزوه‌های درسی هستی. فقط JSON.')
        await db.quiz_log_generation(
            user_id, 'topics', cfg.get('provider', ''), cfg.get('model', ''),
            int((time.monotonic() - t0) * 1000), True,
            chars_in=len(prompt), chars_out=0,
            items_out=len((data or {}).get('topics') or []))
        topics = _sanitize_topics((data or {}).get('topics') or [], pages)
        if topics:
            return topics
    except Exception as e:
        logger.warning('topic structure AI failed: %s — heuristic', type(e).__name__)
        try:
            await db.quiz_log_generation(user_id, 'topics', '', '', 0, False,
                                         error_type=type(e).__name__)
        except Exception:
            pass
    return _heuristic_topics(pages, max_topics)


def _sanitize_topics(raw: list, pages: list, max_topics: int = 30) -> list:
    """اعتبارسنجی/تعمیر خروجی مباحث: مرتب، پیوسته، بدون همپوشانی."""
    n = len(pages)
    first, last = pages[0]['no'], pages[-1]['no']
    cleaned = []
    for t in raw or []:
        try:
            title = str(t.get('title', '')).strip()[:80]
            s, e = int(t.get('page_start', 0)), int(t.get('page_end', 0))
        except (TypeError, ValueError, AttributeError):
            continue
        if not title or s < first or e > last or e < s:
            continue
        # قطع همپوشانی با قبلی
        if cleaned and s <= cleaned[-1]['page_end']:
            s = cleaned[-1]['page_end'] + 1
            if e < s:
                continue
        cleaned.append({'id': len(cleaned), 'title': title,
                        'page_start': s, 'page_end': e})
        if len(cleaned) >= max_topics:
            break
    if not cleaned:
        return []
    # پوشش شکاف‌ها: بازه‌ی هر مبحث تا ابتدای مبحث بعدی گسترش می‌یابد
    for i in range(len(cleaned) - 1):
        nxt = cleaned[i + 1]['page_start']
        if cleaned[i]['page_end'] < nxt - 1:
            cleaned[i]['page_end'] = nxt - 1
    cleaned[-1]['page_end'] = max(cleaned[-1]['page_end'], last)
    return cleaned


# ══════════════════════════════════════════════════
#  ۳) تولید و اعتبارسنجی سؤال
# ══════════════════════════════════════════════════

QUESTION_SCHEMA = {
    'type': 'OBJECT',
    'properties': {
        'questions': {
            'type': 'ARRAY',
            'items': {
                'type': 'OBJECT',
                'properties': {
                    'stem': {'type': 'STRING'},          # صورت سؤال ≤300
                    'options': {                         # دقیقاً ۴ گزینه ≤100
                        'type': 'ARRAY',
                        'items': {'type': 'STRING'},
                    },
                    'correct_index': {'type': 'INTEGER'},  # 0..3
                    'explanation_short': {'type': 'STRING'},  # ≤200 برای poll
                    'explanation_long': {'type': 'STRING'},   # پیام جدا
                    'page_ref': {'type': 'INTEGER'},     # شماره صفحه مبنا
                    'difficulty': {'type': 'STRING'},    # easy|medium|hard
                    'cognitive_level': {'type': 'STRING'},
                    'concept_tags': {
                        'type': 'ARRAY', 'items': {'type': 'STRING'},
                    },
                    'source_evidence': {'type': 'STRING'},  # نقل از متن
                },
                'required': ['stem', 'options', 'correct_index',
                             'explanation_short', 'explanation_long',
                             'page_ref'],
            },
        },
    },
    'required': ['questions'],
}


def _validate_question(q: dict, valid_pages: set) -> tuple | None:
    """اعتبارسنجی سختِ یک سؤال. None = مردود. خروجی: dict سؤال.

    هیچ فیلدی کوتاه/بلند نمی‌شود — سؤالِ شکسته بهتر است رد شود (باگ‌گیر
    ۳۰۰/۱۰۰/۲۰۰ کاراکتر تلگرام اینجاست)."""
    if not isinstance(q, dict):
        return None
    stem = (q.get('stem') or '').strip()
    if not (10 <= len(stem) <= TG_MAX_QUESTION):
        return None
    opts = q.get('options')
    if not isinstance(opts, list) or len(opts) != 4:
        return None
    opts = [str(o).strip() for o in opts]
    if any(not (1 <= len(o) <= TG_MAX_OPTION) for o in opts):
        return None
    if len(set(opts)) != 4:                     # گزینه تکراری
        return None
    try:
        ci = int(q.get('correct_index'))
    except (TypeError, ValueError):
        return None
    if not 0 <= ci <= 3:
        return None
    es = (q.get('explanation_short') or '').strip()
    if not (5 <= len(es) <= TG_MAX_EXPLANATION) or es.count('\n') > 2:
        return None
    el = (q.get('explanation_long') or '').strip() or es
    try:
        pr = int(q.get('page_ref'))
    except (TypeError, ValueError):
        return None
    if pr not in valid_pages:
        return None
    return {
        'stem': stem, 'options': opts, 'correct_index': ci,
        'explanation_short': es, 'explanation_long': el[:1200],
        'difficulty': str(q.get('difficulty') or 'medium')[:12],
        'cognitive_level': str(q.get('cognitive_level') or '')[:24],
        'concept_tags': [str(t)[:40] for t in (q.get('concept_tags') or [])][:6],
        'source_evidence': str(q.get('source_evidence') or '')[:600],
        'topic_id': None, 'topic_title': '', 'page_refs': [pr],
    }


def _finalize_question(qd: dict, topic: dict):
    """تکمیل متادیتای مبحث + shuffle گزینه‌ها + content_hash."""
    qd['topic_id'] = topic['id']
    qd['topic_title'] = topic['title']
    opts = qd['options']
    correct_text = opts[qd['correct_index']]
    order = [0, 1, 2, 3]
    random.shuffle(order)                      # Fisher–Yates
    qd['options'] = [opts[i] for i in order]
    qd['correct_index'] = qd['options'].index(correct_text)
    h = hashlib.sha256()
    h.update(qd['stem'].encode('utf-8'))
    for o in sorted(qd['options']):
        h.update(o.encode('utf-8'))
    qd['content_hash'] = h.hexdigest()
    return qd


QUESTION_PROMPT = '''تو سازنده‌ی سؤال چهارگزینه‌ای برای جزوه‌ی زیر هستی.
قواعد آهنین:
• فقط از متن «منبع» زیر. چیزی که در منبع نیست نجوی — اگر متن برای {want} سؤال کافی نیست، کمتر بده (لیست کوتاه بهتر از سؤال بی‌مبناست).
• گزینه‌ی درست باید دقیقاً مطابق منبع باشد؛ گزینه‌های غلط «قابل باور ولی غلط» باشند (نه مسخره).
• صورت سؤال حداکثر ۳۰۰ کاراکتر، هر گزینه حداکثر ۱۰۰ کاراکتر.
• explanation_short حداکثر ۲۰۰ کاراکتر و حداکثر ۲ خط: چرا این گزینه درست است (با اشاره به صفحه).
• explanation_long: توضیح کامل‌تر برای دانشجو، با ذکر صفحه.
• page_ref: شماره صفحه‌ای که پاسخ در آن است (عدد از بازه‌ی مجاز پایین).
• سؤال تکراری یا معکوس سؤال قبلی نده.
• پاسخ فقط JSON مطابق schema.

بازه صفحه‌ی مجاز: {pfrom} تا {pto}
مبحث: {topic} (صفحات {tfrom}–{tto})
تعداد درخواستی: {want} سؤال

منبع:
{source}'''


async def generate_questions_for_topic(doc, topic: dict, want: int,
                                       user_id: int,
                                       difficulty: str = 'mixed') -> list:
    """تولید سؤال برای یک مبحث — چانک‌بندی + validation + verification.

    هر پاسخ AI → سؤال‌های validate شده → فراخوان verification جدا
    (مخالف‌خوان) → مردودها یک بار بازتولید. خروجی نهایی بدون تکرار
    content_hash در کل نشست."""
    pages = [p for p in doc['pages']
             if topic['page_start'] <= p['no'] <= topic['page_end']
             and p['chars'] >= 60]
    if not pages:
        return []
    valid_pages = {p['no'] for p in pages}
    chunk_chars = int(await _setting('quiz_chunk_chars'))
    batch = int(await _setting('quiz_batch_questions'))

    # چانک‌بندی متن مبحث
    chunks, cur, cur_len = [], [], 0
    for p in pages:
        cur.append(p)
        cur_len += p['chars']
        if cur_len >= chunk_chars:
            chunks.append(cur)
            cur, cur_len = [], 0
    if cur:
        chunks.append(cur)

    # توزیع want روی چانک‌ها به نسبت حجم
    total_chars = sum(sum(p['chars'] for p in c) for c in chunks) or 1
    plan = []           # (chunk, n)
    remaining = want
    for i, c in enumerate(chunks):
        n = (want * sum(p['chars'] for p in c)) // total_chars if i < len(chunks) - 1 else remaining
        n = min(n, remaining)
        if n > 0:
            plan.append((c, n))
            remaining -= n

    out: list = []
    seen_hashes: set = set()
    from ai_solver import generate_structured_json, get_ai_config
    cfg = await get_ai_config()
    if not cfg.get('enabled'):
        return []

    for c, n in plan:
        for attempt in (1, 2):          # تلاش + یک بازتولید برای مردودها
            need = n - sum(1 for q in out if q is not None)
            if need <= 0:
                break
            source = '\n\n'.join(
                f"── صفحه {p['no']} ──\n{p['text']}" for p in c)
            source = source[:chunk_chars + 3000]
            prompt = QUESTION_PROMPT.format(
                want=min(need + 2, batch + 2), pfrom=min(valid_pages),
                pto=max(valid_pages), topic=topic['title'],
                tfrom=topic['page_start'], tto=topic['page_end'],
                source=source)
            t0 = time.monotonic()
            try:
                async with _AI_SEMAPHORE:
                    data = await generate_structured_json(
                        prompt, QUESTION_SCHEMA, purpose='تولید سؤال',
                        max_tokens=8192,
                        system_prompt='تو مدرس باتجربه هستی؛ فقط JSON؛ فقط از منبع.')
            except Exception as e:
                logger.warning('question gen failed: %s', type(e).__name__)
                await db.quiz_log_generation(
                    user_id, 'questions', cfg.get('provider', ''),
                    cfg.get('model', ''), int((time.monotonic() - t0) * 1000),
                    False, chars_in=len(prompt), error_type=type(e).__name__)
                break
            await db.quiz_log_generation(
                user_id, 'questions', cfg.get('provider', ''), cfg.get('model', ''),
                int((time.monotonic() - t0) * 1000), True,
                chars_in=len(prompt), items_out=len((data or {}).get('questions') or []))
            raw = (data or {}).get('questions') or []
            candidates = []
            for q in raw:
                v = _validate_question(q, valid_pages)
                if v:
                    candidates.append(v)
            # verification مخالف‌خوان
            verified = await verify_questions(
                candidates, source, user_id,
                topic_title=topic['title']) if candidates else []
            added = 0
            for qd in verified:
                qd = _finalize_question(qd, topic)
                if qd['content_hash'] in seen_hashes:
                    continue
                seen_hashes.add(qd['content_hash'])
                out.append(qd)
                added += 1
                if sum(1 for x in out if x) >= n:
                    break
            if attempt == 1 and added < need:
                continue            # یک بازتولید
            break
    return [q for q in out if q]


VERIFY_SCHEMA = {
    'type': 'OBJECT',
    'properties': {
        'results': {
            'type': 'ARRAY',
            'items': {
                'type': 'OBJECT',
                'properties': {
                    'index': {'type': 'INTEGER'},
                    'verdict': {'type': 'STRING'},   # ok | wrong | fixable
                    'reason': {'type': 'STRING'},
                    'fixed_correct_index': {'type': 'INTEGER'},
                },
                'required': ['index', 'verdict'],
            },
        },
    },
    'required': ['results'],
}

VERIFY_PROMPT = '''تو «مخالف‌خوان» سخت‌گیر هستی. سؤال‌های چهارگزینه‌ای زیر را با متن منبع بسنج:
1) آیا گزینه‌ی درست واقعاً طبق منبع درست است؟ (بدون حدس)
2) آیا هیچ گزینه‌ی غلطی هم طبق منبع درست نباشد؟
3) آیا explanation با منبع سازگار است؟
4) آیا page_ref همان صفحه‌ی پاسخ است؟
verdict:
• ok — سؤال سالم است.
• wrong — ایراد اساسی دارد (پاسخ نادرست/مبهم/بی‌مبنا). مردود.
• fixable — فقط correct_index اشتباه علامت خورده و fixed_correct_index درست را می‌دهد.
با شماره‌ی index هر سؤال (۰-based) پاسخ بده. فقط JSON.

مبحث: {topic}

سؤال‌ها:
{qlist}

منبع:
{source}'''


async def verify_questions(candidates: list, source: str, user_id: int,
                          topic_title: str = '') -> list:
    """فراخوان دومِ AI: بازبینی مستقل سؤال‌ها در برابر منبع.

    برمی‌گرداند: سؤال‌های ok (+ fixableهای اصلاح‌شده). wrong حذف."""
    if not candidates:
        return []
    qlist = []
    for i, q in enumerate(candidates):
        opts = '\n'.join(f"  {chr(0x06F0 + j + 1)}. {o}"   # ۱۲۳۴ فارسی
                         for j, o in enumerate(q['options']))
        qlist.append(
            f"[{i}] {q['stem']}\n{opts}\n"
            f"گزینه‌ی درست ادعاشده: {q['correct_index'] + 1}\n"
            f"توضیح: {q['explanation_short']}\nصفحه: {q['page_refs'][0]}")
    prompt = VERIFY_PROMPT.format(
        topic=topic_title or '',
        qlist='\n\n'.join(qlist), source=source[:12000])
    from ai_solver import generate_structured_json, get_ai_config
    cfg = await get_ai_config()
    t0 = time.monotonic()
    try:
        async with _AI_SEMAPHORE:
            data = await generate_structured_json(
                prompt, VERIFY_SCHEMA, purpose='بازبینی سؤال',
                max_tokens=4096,
                system_prompt='تو ممیز بی‌رحم سؤال‌های امتحانی هستی؛ فقط JSON.')
    except Exception as e:
        # اگر verification در دسترس نیست، سؤال‌ها ارسال نمی‌شوند —
        # «سؤالِ مطمئن» مهم‌تر از «سؤالِ کافی» است.
        logger.warning('verify failed: %s — dropping %d candidates',
                       type(e).__name__, len(candidates))
        await db.quiz_log_generation(user_id, 'verify', '', '', 0, False,
                                     items_in=len(candidates),
                                     error_type=type(e).__name__)
        return []
    await db.quiz_log_generation(
        user_id, 'verify', cfg.get('provider', ''), cfg.get('model', ''),
        int((time.monotonic() - t0) * 1000), True,
        items_in=len(candidates), items_out=len((data or {}).get('results') or []))
    verdicts = {}
    for r in (data or {}).get('results') or []:
        try:
            verdicts[int(r['index'])] = (str(r.get('verdict', '')).lower(),
                                         r.get('fixed_correct_index'))
        except (KeyError, TypeError, ValueError):
            continue
    out = []
    for i, q in enumerate(candidates):
        v = verdicts.get(i)
        if v is None or v[0] != 'ok':
            if v and v[0] == 'fixable':
                try:
                    fx = int(v[1])
                    if 0 <= fx <= 3 and fx != q['correct_index'] \
                            and len(set(q['options'])) == 4:
                        q = dict(q)
                        q['correct_index'] = fx
                        out.append(q)
                        continue
                except (TypeError, ValueError):
                    pass
            continue        # wrong یا نامعتبر → حذف
        out.append(q)
    return out


# ══════════════════════════════════════════════════
#  ۴) گزارش پایان
# ══════════════════════════════════════════════════

def _fa(n) -> str:
    """عدد → ارقام فارسی."""
    return str(n).translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹'))


async def build_final_report(session: dict) -> str:
    """گزارش پایان نشست به تفکیک مبحث (HTML امن — esc شده)."""
    qs = await db.quiz_session_questions(session['_id'], only_answered=True)
    total = len(qs)
    if not total:
        return '📭 در این آزمون پاسخی ثبت نشد.'
    correct = sum(1 for q in qs if q.get('is_correct'))
    secs = 0
    try:
        t0 = datetime.fromisoformat(session.get('started_at') or session['created_at'])
        t1 = datetime.fromisoformat(session.get('finished_at') or utc_now_iso())
        secs = max(0, int((t1 - t0).total_seconds()))
    except Exception:
        pass

    by_topic: dict = {}
    for q in qs:
        t = (q.get('topic_title') or 'بدون مبحث')
        d = by_topic.setdefault(t, {'n': 0, 'c': 0})
        d['n'] += 1
        d['c'] += bool(q.get('is_correct'))

    # اعداد فارسی + درصدها
    pct = round(100 * correct / total)
    lines = [
        '📊 <b>گزارش پایان آزمون</b>',
        f"📘 سند: {_esc(session.get('doc_name') or '')}",
        f"✅ درست: <b>{_fa(correct)}</b> از {_fa(total)} "
        f"({_fa(pct)}٪)",
    ]
    if secs >= 60:
        lines.append(f"⏱ مدت: {_fa(secs // 60)} دقیقه")
    lines.append('')
    lines.append('<b>به تفکیک مبحث:</b>')
    for t, d in sorted(by_topic.items(), key=lambda kv: -kv[1]['n']):
        tp = round(100 * d['c'] / d['n'])
        # نشانگر گرافیکی
        filled = round(tp / 10)
        bar = '■' * filled + '□' * (10 - filled)
        lines.append(f"• {_esc(t)}: {_fa(d['c'])}/{_fa(d['n'])} "
                     f"({_fa(tp)}٪) {bar}")
    lines.append('')
    if pct >= 80:
        lines.append('🎉 عالی! تسلط خوبی روی این جزوه داری.')
    elif pct >= 50:
        lines.append('👍 بد نیست؛ روی مباحث ضعیف‌تر کمی وقت بگذار.')
    else:
        lines.append('💪 این جزوه را یک مرور دیگر لازم داری — دوباره آزمون بده!')
    return '\n'.join(lines)


# ══════════════════════════════════════════════════
#  ۵) رابط کاربری (callback flow)
# ══════════════════════════════════════════════════

def _kb(rows):
    return InlineKeyboardMarkup(rows)


# 🔌 رفرنس اپلیکیشن (bot/job_queue) — در post_init ربات ست می‌شود؛
# تسک‌های بک‌گراندِ تولید، بدون context به آن نیاز دارند.
_APP = {'app': None}


def set_application(app) -> None:
    _APP['app'] = app


async def quiz_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ورودی «آزمون‌ساز از PDF» — منوی اصلی."""
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    if not await _setting('quiz_pdf_enabled'):
        await q.edit_message_text('📚 آزمون‌ساز فعلاً توسط مدیریت غیرفعال است.')
        return

    active = await db.quiz_active_session(uid)
    if active:
        answered, total = active['answered'], active.get('total_planned', 0)
        rows = [[InlineKeyboardButton(
            f'▶️ ادامه ({_fa(answered)}/{_fa(total)})',
            callback_data=f'quiz:resume:{active["_id"]}')]]
        rows.append([InlineKeyboardButton(
            '⛔️ پایان و گزارش', callback_data=f'quiz:stop:{active["_id"]}')])
        await q.edit_message_text(
            '📚 <b>آزمون‌ساز از PDF</b>\n\n'
            'شما یک آزمون باز دارید:',
            parse_mode='HTML', reply_markup=_kb(rows))
        return

    docs = await db.quiz_list_documents(uid, limit=10)
    rows = []
    for d in docs:
        if d.get('status') == 'ready':
            label = f"📘 {d['name'][:28]} ({_fa(d.get('page_count', 0))} ص)"
            rows.append([InlineKeyboardButton(
                label, callback_data=f"quiz:doc:{d['_id']}")])
    rows.append([InlineKeyboardButton(
        '📤 ارسال جزوه جدید (PDF)', callback_data='quiz:upload')])
    text = ('📚 <b>آزمون‌ساز هوشمند</b>\n\n'
            'جزوه‌ی PDF خودت را بفرست؛ سؤال‌های چهارگزینه‌ایِ «کنکوری» از دلِ '
            'همان جزوه می‌سازم، همین‌جا توی تلگرام آزمون می‌گیری و آخرش '
            'گزارش نمره به تفکیک مبحث می‌گیری.\n\n'
            '🔻 جزوه‌ات را انتخاب کن یا یکی جدید بفرست:')
    if not docs:
        text += '\n\n<i>هنوز جزوه‌ای نداری — اولین PDF را بفرست!</i> 🎯'
    await q.edit_message_text(text, parse_mode='HTML', reply_markup=_kb(rows))


async def quiz_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """روتر همه‌ی quiz:* — stateless (همه‌ی انتخاب‌ها داخل callback_data)."""
    q = update.callback_query
    data = q.data or ''
    try:
        parts = data.split(':')
        action = parts[1] if len(parts) > 1 else 'main'
        uid = q.from_user.id

        if action == 'main':
            return await quiz_menu(update, context)

        if action == 'upload':
            await q.answer()
            limit_mb = int(await _setting('quiz_max_pdf_mb'))
            context.user_data['quiz_awaiting_pdf'] = True
            context.user_data.pop('mode', None)   # تداخل با ai_query
            await q.edit_message_text(
                f"📤 جزوه‌ات را همین‌جا در چت بفرست.\n\n"
                f"• فقط PDF (حداکثر {_fa(limit_mb)} مگابایت و "
                f"{_fa(int(await _setting('quiz_max_pages')))} صفحه)\n"
                f"• متنِ قابل‌کپی باید داشته باشد — عکس/اسکن را نمی‌توانم بخوانم\n"
                f"• متن جزوه فقط برای ساخت سؤال استفاده می‌شود و بعد از "
                f"{_fa(int(await _setting('quiz_doc_retention_days')))} روز "
                f"خودکار حذف می‌شود",
                reply_markup=_kb([[InlineKeyboardButton(
                    '↩️ بازگشت', callback_data='quiz:main')]]))
            return

        if action == 'doc' and len(parts) > 2:
            return await _show_doc(update, context, parts[2], uid)

        if action == 'start' and len(parts) > 2:
            return await _show_mode_screen(update, context, parts[2])

        if action == 'cnt' and len(parts) > 4:
            # quiz:cnt:<docid>:<mode>:<count> → صفحه‌ی انتخاب محدوده
            return await _show_range_screen(update, context,
                                            parts[2], parts[3], parts[4])

        if action == 'tp' and len(parts) > 5:
            # صفحه‌بندی مباحث: quiz:tp:<docid>:<mode>:<count>:<page>
            return await _show_range_screen(update, context,
                                            parts[2], parts[3], parts[4],
                                            page=int(parts[5]))

        if action == 'go' and len(parts) > 5:
            # quiz:go:<docid>:<mode>:<count>:<range>
            return await _begin_session(update, context,
                                        parts[2], parts[3], parts[4], parts[5])

        if action == 'del' and len(parts) > 2:
            return await _delete_doc_flow(update, context, parts[2], uid)

        if action == 'del2' and len(parts) > 2:
            return await quiz_delete_confirm(update, context)

        if action == 'resume' and len(parts) > 2:
            return await _resume_session(update, context, parts[2], uid)

        if action == 'stop' and len(parts) > 2:
            return await _stop_session(update, context, parts[2], uid,
                                       by_user=True)

        await q.answer()
        await q.edit_message_text('⚠️ دکمه نامعتبر است — /start و دوباره تلاش کن.',
                                  reply_markup=_kb([[InlineKeyboardButton(
                                      '📚 آزمون‌ساز', callback_data='quiz:main')]]))
    except Exception:
        logger.exception('quiz_callback failed')
        try:
            await q.answer('خطایی پیش آمد ⚠️', show_alert=False)
        except Exception:
            pass


def _doc_kb(doc_id):
    return _kb([
        [InlineKeyboardButton('🎯 شروع آزمون جدید',
                              callback_data=f'quiz:start:{doc_id}')],
        [InlineKeyboardButton('🗑 حذف جزوه', callback_data=f'quiz:del:{doc_id}')],
        [InlineKeyboardButton('↩️ بازگشت', callback_data='quiz:main')],
    ])


async def _show_doc(update, context, doc_id, uid):
    q = update.callback_query
    await q.answer()
    doc = await db.quiz_get_document(doc_id, owner_id=uid)
    if not doc or doc.get('status') != 'ready':
        await q.edit_message_text('⚠️ این جزوه در دسترس نیست (حذف یا ناموفی).',
                                  reply_markup=_kb([[InlineKeyboardButton(
                                      '↩️ بازگشت', callback_data='quiz:main')]]))
        return
    topics = doc.get('topics') or []
    lines = [f"📘 <b>{_esc(doc['name'])}</b>",
             f"📄 {_fa(doc.get('page_count', 0))} صفحه",
             f"🧩 {_fa(len(topics))} مبحث"]
    if doc.get('quality_note'):
        lines.append(f"⚠️ {_esc(doc['quality_note'])}")
    lines.append('\n<b>مباحث:</b>')
    for t in topics[:30]:
        lines.append(f"• {_esc(t['title'])} "
                     f"<i>(ص {_fa(t['page_start'])}–{_fa(t['page_end'])})</i>")
    await q.edit_message_text('\n'.join(lines), parse_mode='HTML',
                              reply_markup=_doc_kb(doc_id))


async def _show_mode_screen(update, context, doc_id):
    """گام ۱: حالت آزمون + تعداد سؤال (همه‌چیز در callback_data)."""
    q = update.callback_query
    await q.answer()
    doc = await db.quiz_get_document(doc_id, owner_id=q.from_user.id)
    if not doc:
        await q.answer('جزوه در دسترس نیست ⚠️', show_alert=True)
        return
    max_q = int(await _setting('quiz_max_questions_per_session'))
    counts = [c for c in (10, 20, 30) if c <= max_q] or [max_q]
    rows = []
    # سطر حالت تمرینی
    rows.append([InlineKeyboardButton(
        f'🧪 تمرینی — {_fa(c)} سؤال',
        callback_data=f'quiz:cnt:{doc_id}:practice:{c}')
        for c in counts])
    rows.append([InlineKeyboardButton(
        f'🏁 آزمونی — {_fa(c)} سؤال',
        callback_data=f'quiz:cnt:{doc_id}:exam:{c}')
        for c in counts])
    rows.append([InlineKeyboardButton('↩️ بازگشت',
                                      callback_data=f'quiz:doc:{doc_id}')])
    await q.edit_message_text(
        '🎯 <b>نوع آزمون را انتخاب کن</b>\n\n'
        '🧪 <b>تمرینی:</b> سؤال‌ها تک‌به‌تک؛ بعد از هر جواب فوراً '
        '«چرا درست/غلط» را می‌بینی.\n'
        '🏁 <b>آزمونی:</b> سؤال‌ها گروهی می‌آیند و در پایان، توضیح می‌گیری.',
        parse_mode='HTML', reply_markup=_kb(rows))


async def _show_range_screen(update, context, doc_id, mode, count, page=0):
    """گام ۲: محدوده — کل جزوه یا یک مبحث (صفحه‌بندی ۸تایی)."""
    q = update.callback_query
    await q.answer()
    doc = await db.quiz_get_document(doc_id, owner_id=q.from_user.id)
    if not doc:
        await q.answer('جزوه در دسترس نیست ⚠️', show_alert=True)
        return
    topics = doc.get('topics') or []
    per = 8
    total_pages = (len(topics) + per - 1) // per
    page = max(0, min(page, total_pages - 1)) if total_pages else 0
    rows = [[InlineKeyboardButton('📚 کل جزوه',
                                  callback_data=f'quiz:go:{doc_id}:{mode}:{count}:all')]]
    for t in topics[page * per:(page + 1) * per]:
        rows.append([InlineKeyboardButton(
            f"{t['title'][:30]}",
            callback_data=f'quiz:go:{doc_id}:{mode}:{count}:t{t["id"]}')])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton('⬅️ قبلی',
                                        callback_data=f'quiz:tp:{doc_id}:{mode}:{count}:{page - 1}'))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton('بعدی ➡️',
                                        callback_data=f'quiz:tp:{doc_id}:{mode}:{count}:{page + 1}'))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton('↩️ بازگشت',
                                      callback_data=f'quiz:start:{doc_id}')])
    await q.edit_message_text(
        '📐 <b>محدوده‌ی آزمون:</b>\n\nکل جزوه یا فقط یک مبحث؟',
        parse_mode='HTML', reply_markup=_kb(rows))


async def _delete_doc_flow(update, context, doc_id, uid):
    """تایید دومرحله‌ای حذف — حذفِ واقعی در quiz_delete_confirm (del2)."""
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        '🗑 این جزوه و همه‌ی آزمون‌هایش برای همیشه حذف شود؟',
        reply_markup=_kb([
            [InlineKeyboardButton('🗑 بله، حذف کن',
                                  callback_data=f'quiz:del2:{doc_id}')],
            [InlineKeyboardButton('❌ نه، پشیمون شدم',
                                  callback_data=f'quiz:doc:{doc_id}')]]))


async def quiz_delete_confirm(update, context):
    """quiz:del2 — حذف واقعی."""
    q = update.callback_query
    await q.answer()
    doc_id = (q.data or '').split(':')[2]
    n = await db.quiz_delete_document(doc_id, q.from_user.id)
    await q.edit_message_text(
        '🗑 جزوه حذف شد.' if n else '⚠️ حذف نشد (جزوه پیدا نشد).',
        reply_markup=_kb([[InlineKeyboardButton(
            '📚 آزمون‌ساز', callback_data='quiz:main')]]))


# ══════════════════════════════════════════════════
#  ۶) ساخت نشست و تولید سؤال‌ها
# ══════════════════════════════════════════════════

def _range_topics(doc: dict, range_spec: str) -> list:
    topics = doc.get('topics') or []
    if range_spec == 'all':
        return topics
    if range_spec.startswith('t'):
        try:
            tid = int(range_spec[1:])
        except ValueError:
            return topics
        return [t for t in topics if t['id'] == tid] or topics
    return topics


async def _begin_session(update, context, doc_id, mode, count, range_spec):
    q = update.callback_query
    uid = q.from_user.id
    doc = await db.quiz_get_document(doc_id, owner_id=uid)
    if not doc:
        await q.answer('جزوه در دسترس نیست ⚠️', show_alert=True)
        return
    if await db.quiz_active_session(uid):
        await q.answer('اول آزمون بازِ فعلی را تمام کن ⛔️', show_alert=True)
        return
    count = max(3, min(int(count), int(await _setting('quiz_max_questions_per_session'))))
    # سقف روزانه
    daily = int(await _setting('quiz_daily_question_limit'))
    used = await db.quiz_usage_today(uid)
    if used >= daily:
        await q.answer('سهمیه‌ی سؤال امروزت پر شده — فردا دوباره 🌙', show_alert=True)
        return
    count = min(count, daily - used)

    topics = _range_topics(doc, range_spec)
    settings = {
        'mode': mode if mode in ('practice', 'exam') else 'practice',
        'count': count, 'range': range_spec,
        'range_title': ('کل جزوه' if range_spec == 'all'
                        else topics[0]['title'] if topics else ''),
    }
    sid = await db.quiz_create_session(uid, doc, settings)
    await db.quiz_update_session(sid, {'build_attempts': 1})
    # پیام «در حال ساخت» — بعداً همین پیام ویرایش می‌شود
    await q.edit_message_text(
        '🛠 <b>در حال ساخت سؤال‌ها…</b>\n'
        'این کار چند دقیقه طول می‌کشد. می‌توانی این پیام را رها کنی و '
        'سر کارت باشی — وقتی آماده شد خبرت می‌کنم.',
        parse_mode='HTML')
    # تولید در بک‌گراند — همه‌ی state در DB است؛ ری‌استارت چیزی نمی‌برد
    asyncio.create_task(_build_and_start(
        q.message.chat_id, q.message.message_id, str(sid), uid))
    await q.answer('شروع شد 🚀')


async def _build_and_start(chat_id: int, message_id: int, sid: str, uid: int):
    """تولید سؤال‌های نشست (بک‌گراند) + فعال‌سازی و ارسال اولین سؤال.

    idempotent: اگر سؤالِ کافی از قبل هست (بعد از ری‌استارت) فقط ارسال
    را ادامه می‌دهد."""
    try:
        session = await db.quiz_get_session(sid)
        if not session:
            return
        if session['status'] == 'active':
            # ادامه‌ی نشست بعد از ری‌استارت
            if session['mode'] == 'exam':
                await _send_batch(session, chat_id)
            else:
                await _send_one(session, chat_id)
            return
        if session['status'] != 'building':
            return
        doc = await db.quiz_get_document(session['doc_id'])
        if not doc:
            await db.quiz_finish_session(sid, 'cancelled')
            return
        topics = _range_topics(doc, session['settings'].get('range', 'all'))
        planned = session['total_planned']
        existing = await db.quiz_session_questions(sid)
        have = len(existing)
        if have >= planned:
            return await _activate(session, chat_id, message_id)

        # توزیع سؤال بین مباحث به نسبت حجم متن
        vols = {t['id']: sum(p['chars'] for p in doc['pages']
                             if t['page_start'] <= p['no'] <= t['page_end'])
                for t in topics}
        total_v = sum(vols.values()) or 1
        # مباحثِ خالی → حذف از توزیع
        live = [t for t in topics if vols.get(t['id'], 0) >= 120] or topics[:1]
        total_v = sum(vols[t['id']] for t in live) or 1
        per_topic = {}
        rem = planned - have
        for i, t in enumerate(live):
            n = (rem * vols[t['id']]) // total_v if i < len(live) - 1 else rem
            n = min(n, rem)
            if n > 0:
                per_topic[t['id']] = n
                rem -= n

        made = 0
        for t in live:
            need = per_topic.get(t['id'], 0)
            if need <= 0:
                continue
            qs = await generate_questions_for_topic(doc, t, need, uid)
            if qs:
                made += await db.quiz_add_questions(sid, uid, session['doc_id'], qs)
        await db.quiz_inc_usage(uid, made)
        session = await db.quiz_get_session(sid)
        total_now = len(await db.quiz_session_questions(sid))
        if total_now == 0:
            await db.quiz_finish_session(sid, 'cancelled')
            await _bot_send_edit(
                chat_id, message_id,
                '😔 الان نتوانستم از این جزوه سؤال بسازم.\n'
                'ممکن است متن جزوه برای سؤال‌سازی کافی نباشد. '
                'دوباره تلاش کن یا جزوه‌ی بهتری بفرست.',
                keyboard=_kb([[InlineKeyboardButton(
                    '📚 آزمون‌ساز', callback_data='quiz:main')]]),
                bot=_get_bot())
            return
        # کمتر از پلان هم قبول است — پلان را به واقعی می‌چسبانیم
        if total_now < session['total_planned']:
            await db.quiz_update_session(sid, {'total_planned': total_now})
        await _activate(session, chat_id, message_id, total_now)
    except Exception:
        logger.exception('_build_and_start failed sid=%s', sid)
        await db.quiz_finish_session(sid, 'cancelled')
        await _bot_send_edit(
            chat_id, message_id, '⚠️ خطا در ساخت آزمون — دوباره تلاش کن.',
            keyboard=_kb([[InlineKeyboardButton(
                '📚 آزمون‌ساز', callback_data='quiz:main')]]),
            bot=_get_bot())


async def _bot_send_edit(chat_id, message_id, text, keyboard=None, bot=None):
    """ویرایش پیام وضعیت؛ در شکست → پیام جدید."""
    b = bot or _get_bot()
    if b is None:
        return
    try:
        await b.edit_message_text(text, chat_id=chat_id,
                                  message_id=message_id,
                                  reply_markup=keyboard)
    except Exception:
        try:
            await b.send_message(chat_id, text, reply_markup=keyboard)
        except Exception:
            pass


async def _activate(session, chat_id, message_id, total_now=None):
    """building → active + ارسال اولین سؤال/دسته."""
    await db.quiz_update_session(session['_id'],
                                 {'status': 'active',
                                  'started_at': utc_now_iso()})
    session = await db.quiz_get_session(session['_id'])
    await _bot_send_edit(
        chat_id, message_id,
        f"✅ آزمون آماده شد — {_fa(session['total_planned'])} سؤال!\nموفق باشی 🍀",
        bot=_get_bot())
    if session['mode'] == 'exam':
        await _send_batch(session, chat_id, batch=5)
    else:
        await _send_one(session, chat_id)


# ══════════════════════════════════════════════════
#  ۷) ارسال سؤال (Quiz Poll)
# ══════════════════════════════════════════════════

_OPEN_PERIOD = {'practice': 180, 'exam': 300}   # ثانیه


async def _send_question(bot, chat_id, session, question) -> bool:
    """ارسال یک سؤال به‌صورت Quiz Poll غیرناشناس + bind + تایم‌اوت."""
    try:
        m = await bot.send_poll(
            chat_id=chat_id,
            question=question['stem'],
            options=question['options'],
            type='quiz',
            is_anonymous=False,          # 🔑 بدون این poll_answer نمی‌آید
            correct_option_id=question['correct_index'],
            # 📌 explanation بدون parse_mode: متنِ AI است؛ HTML شکسته
            # می‌تواند کل ارسال را بکشد (سؤال = مهم‌ترین دارایی).
            explanation=question['explanation_short'],
            open_period=_OPEN_PERIOD.get(session['mode'], 180),
        )
    except RetryAfter as e:
        await asyncio.sleep(e.retry_after + 1)
        return await _send_question(bot, chat_id, session, question)
    except Forbidden:
        logger.info('quiz send forbidden uid~%s', session['user_id'])
        return False
    except BadRequest as e:
        # سؤالِ ردشده توسط تلگرام (مثلاً explanation نامعتبر) → skip
        logger.warning('poll rejected: %s', e)
        return False
    ok = await db.quiz_bind_poll(question['_id'],
                                 m.poll.id, chat_id, m.message_id)
    if not ok:
        try:
            await bot.stop_poll(chat_id, m.message_id)
        except Exception:
            pass
        return False
    await db.quiz_update_session(session['_id'], inc={'sent': 1},
                                 update={'current_order': question['order_index']})
    # تایم‌اوتِ سؤال — بعد از open_period+مهلت، skip و جلو می‌رویم
    try:
        jq = _get_job_queue()
        if jq:
            jq.run_once(quiz_question_timeout,
                        when=_OPEN_PERIOD.get(session['mode'], 180) + 25,
                        data={'sid': str(session['_id']),
                              'qid': str(question['_id'])},
                        name=f'quizq:{question["_id"]}')
    except Exception:
        logger.debug('timeout job arm failed', exc_info=True)
    return True


def _get_job_queue():
    a = _APP['app']
    return getattr(a, 'job_queue', None) if a else None


async def _send_one(session, chat_id):
    """حالت تمرینی: سؤال بعدی — فقط وقتی هیچ poll بازی نمانده.

    سؤالی که تلگرام رد کند → skip می‌شود (بدون حلقه‌ی بی‌نهایت) و
    همان‌جا سؤالِ بعدی ارسال می‌شود."""
    bot = _get_bot()
    if bot is None or not chat_id:
        return
    if await db.quiz_open_polls(session['_id']):
        return          # هنوز سؤال بازی هست
    while True:
        qn = await db.quiz_next_question(session['_id'])
        if not qn:
            return await _maybe_finish(session, chat_id)
        if await _send_question(bot, chat_id, session, qn):
            return
        # ارسال شکست خورد → skip و ادامه با بعدی
        await db.ai_quiz_questions.update_one(
            {'_id': qn['_id'], 'status': 'sent'},
            {'$set': {'status': 'skipped', 'is_correct': False,
                      'answered_at': utc_now_iso()}})
        await db.quiz_update_session(session['_id'], inc={'answered': 1})


async def _send_batch(session, chat_id, batch=5):
    """حالت آزمونی: ارسال دسته‌ای با فاصله‌ی ~۱.۱ ثانیه (سقف تلگرام)."""
    bot = _get_bot()
    if bot is None or not chat_id:
        return
    sent = 0
    while sent < batch:
        qn = await db.quiz_next_question(session['_id'])
        if not qn:
            break
        if await _send_question(bot, chat_id, session, qn):
            sent += 1
        else:
            # سؤال ردشده → skip و ادامه
            await db.ai_quiz_questions.update_one(
                {'_id': qn['_id'], 'status': 'sent'},
                {'$set': {'status': 'skipped', 'is_correct': False,
                          'answered_at': utc_now_iso()}})
            await db.quiz_update_session(session['_id'], inc={'answered': 1})
        if await _count_status(session['_id'], 'queued') == 0:
            break
        await asyncio.sleep(_SEND_GAP)
    if not await _has_open_or_queued(session['_id']):
        await _maybe_finish(session, chat_id)


async def _count_status(sid, status) -> int:
    return await db.ai_quiz_questions.count_documents(
        {'session_id': ObjectId(sid), 'status': status})


async def _has_open_or_queued(sid) -> bool:
    n1 = await _count_status(sid, 'queued')
    n2 = await _count_status(sid, 'sent')
    return bool(n1 or n2)


def _get_bot():
    a = _APP['app']
    return a.bot if a else None


# ══════════════════════════════════════════════════
#  ۸) پاسخ کاربر (poll_answer) + بازخورد
# ══════════════════════════════════════════════════

async def quiz_poll_answer_handler(update: Update,
                                   context: ContextTypes.DEFAULT_TYPE):
    """نقطه‌ی حیاتی: رأی کاربر → ثبت اتمیک → بازخورد → سؤال بعدی.

    idempotent: آپدیت تکراری/ردِ رأی نادیده گرفته می‌شود."""
    pa = update.poll_answer
    if not pa or not pa.option_ids:
        return                      # رأی پس‌گرفته‌شده یا ناقص
    qd = await db.quiz_question_by_poll(pa.poll_id)
    if not qd or qd.get('status') != 'sent':
        return                      # ناشناخته/دیرهنگام
    if qd.get('user_id') != pa.user.id:
        return                      # رأی دیگری (در چت خصوصی نباید بیاید)
    if qd.get('answered_option') is not None:
        return
    kind, q = await db.quiz_record_answer(
        qd['_id'], pa.option_ids[0],
        time_ms=None)
    if kind != 'first' or not q:
        return
    session = await db.quiz_get_session(qd['session_id'])
    if not session or session['status'] not in ('active',):
        return
    # is_correct را Mongo اتمیک محاسبه کرده — از سندِ تازه می‌خوانیم
    fresh = await db.ai_quiz_questions.find_one({'_id': qd['_id']})
    is_ok = bool(fresh and fresh.get('is_correct'))
    await db.quiz_update_session(
        session['_id'],
        inc={'answered': 1,
             'correct': 1 if is_ok else 0,
             'wrong': 0 if is_ok else 1})
    # 📌 سندِ session قدیمی است (قبل از $inc) — شمارنده‌ها را محلی
    # هم‌گام می‌کنیم تا خط امتیازِ بازخورد دقیق باشد.
    session['answered'] = int(session.get('answered') or 0) + 1
    session['correct'] = int(session.get('correct') or 0) + (1 if is_ok else 0)
    session['wrong'] = int(session.get('wrong') or 0) + (0 if is_ok else 1)
    await _send_feedback(context.bot, session, q, pa.option_ids[0], is_ok)
    # بستن poll (دیگر رأی نگیرد)
    try:
        await context.bot.stop_poll(qd['chat_id'], qd['message_id'])
    except Exception:
        pass
    # تمرینی: سؤال بعدی فقط وقتی همه‌ی قبلی‌ها جواب شده باشند
    if session['mode'] == 'practice':
        if not await _count_status(session['_id'], 'sent'):
            await _send_one(session, qd['chat_id'])
    await _maybe_finish(session, qd['chat_id'])


async def _send_feedback(bot, session, q, chosen, is_ok):
    """بازخورد فوری «چرا درست/غلط» با ارجاع صفحه."""
    correct_text = q['options'][q['correct_index']]
    page = (q.get('page_refs') or [0])[0]
    topic = q.get('topic_title') or ''
    long_exp = (q.get('explanation_long') or q.get('explanation_short') or '').strip()
    # در حالت آزمونی، توضیحِ بلند در پایان می‌آید؛ اینجا خلاصه
    exp = long_exp if session['mode'] == 'practice' else \
        (q.get('explanation_short') or long_exp)
    exp = _esc(exp)[:900]
    if is_ok:
        head = '✅ <b>درست!</b> آفرین 🎉'
    else:
        head = (f'❌ <b>نادرست.</b>\n✅ پاسخ درست: <b>{_esc(correct_text)}</b>')
    body = [head]
    if topic:
        body.append(f'🧩 {_esc(topic)}')
    if page:
        body.append(f'📖 صفحه {_fa(page)} جزوه')
    if exp:
        body.append('')
        body.append(exp)
    score = f"\n\n📊 تا اینجا: {_fa(session['correct'])}/{_fa(session['answered'])}"
    try:
        await bot.send_message(q['chat_id'], '\n'.join(body) + score,
                               parse_mode='HTML')
    except Exception:
        logger.debug('feedback send failed', exc_info=True)


async def quiz_question_timeout(context: ContextTypes.DEFAULT_TYPE):
    """job: سؤال بی‌پاسخ ماند → skip + پیشروی (همان مسیر پاسخ)."""
    data = (context.job.data or {}) if context.job else {}
    sid, qid = data.get('sid'), data.get('qid')
    if not sid or not qid:
        return
    q = await db.ai_quiz_questions.find_one({'_id': ObjectId(qid)})
    if not q or q.get('status') != 'sent':
        return
    # اتمیک: فقط اگر هنوز sent است → skipped
    r = await db.ai_quiz_questions.find_one_and_update(
        {'_id': q['_id'], 'status': 'sent'},
        {'$set': {'status': 'skipped', 'answered_option': None,
                  'is_correct': False, 'answered_at': utc_now_iso()}})
    if not r:
        return
    session = await db.quiz_get_session(sid)
    if not session or session['status'] != 'active':
        return
    await db.quiz_update_session(session['_id'], inc={'answered': 1})
    try:
        await context.bot.send_message(
            q['chat_id'],
            f"⌛️ زمان سؤال {_fa(q['order_index'] + 1)} تمام شد — بی‌پاسخ ثبت شد.")
    except Exception:
        pass
    if session['mode'] == 'practice' and not await _count_status(sid, 'sent'):
        await _send_one(session, q['chat_id'])
    await _maybe_finish(session, q['chat_id'])


async def _maybe_finish(session, chat_id):
    """اگر همه‌ی سؤال‌ها تعیین‌تکلیف شدند → پایان + گزارش."""
    sid = session['_id']
    open_n = await _count_status(sid, 'sent')
    queued_n = await _count_status(sid, 'queued')
    if open_n or queued_n:
        return
    cur = await db.quiz_get_session(sid)
    if not cur or cur['status'] != 'active':
        return
    # دو فراخوانِ همزمان نباید دوبار گزارش بفرستد — اتمیک:
    r = await db.ai_quiz_sessions.find_one_and_update(
        {'_id': sid, 'status': 'active'},
        {'$set': {'status': 'finished', 'finished_at': utc_now_iso()}})
    if not r:
        return
    report = await build_final_report(cur)
    bot = _get_bot()
    if bot is None:
        return
    try:
        await bot.send_message(chat_id, report, parse_mode='HTML',
                               reply_markup=_kb([
                                   [InlineKeyboardButton(
                                       '🔁 آزمون جدید از همین جزوه',
                                       callback_data=f"quiz:start:{cur['doc_id']}")],
                                   [InlineKeyboardButton(
                                       '📚 آزمون‌ساز', callback_data='quiz:main')]]))
    except Exception:
        logger.debug('report send failed', exc_info=True)


async def _resume_session(update, context, sid, uid):
    """ادامه‌ی نشست باز بعد از قطعی/ری‌استارت."""
    q = update.callback_query
    await q.answer()
    session = await db.quiz_get_session(sid)
    if not session or session['user_id'] != uid:
        await q.edit_message_text('⚠️ نشست پیدا نشد.')
        return
    chat_id = q.message.chat_id
    if session['status'] == 'building':
        # تولید نیمه‌کاره → ادامه‌ی تولید (deficit)
        attempts = int(session.get('build_attempts') or 0) + 1
        if attempts > 3:
            await db.quiz_finish_session(sid, 'cancelled')
            await q.edit_message_text(
                '😔 ساخت این آزمون چند بار ناموفی ماند. لطفاً دوباره شروع کن.',
                reply_markup=_kb([[InlineKeyboardButton(
                    '📚 آزمون‌ساز', callback_data='quiz:main')]]))
            return
        await db.quiz_update_session(sid, {'build_attempts': attempts})
        await q.edit_message_text('🛠 ادامه‌ی ساخت سؤال‌ها…')
        asyncio.create_task(_build_and_start(chat_id, q.message.message_id,
                                             sid, uid))
        return
    if session['status'] == 'active':
        open_q = await db.quiz_open_polls(sid)
        if not open_q:
            await _send_one(session, chat_id) if session['mode'] == 'practice' \
                else await _send_batch(session, chat_id)
        await q.edit_message_text('▶️ آزمون ادامه یافت — سؤال بعدی را جواب بده.')
        return
    await q.edit_message_text('این نشست بسته است.',
                              reply_markup=_kb([[InlineKeyboardButton(
                                  '📚 آزمون‌ساز', callback_data='quiz:main')]]))


async def _stop_session(update, context, sid, uid, by_user=False):
    """پایان زودهنگام: بستن pollهای باز + گزارش میانی."""
    q = update.callback_query
    await q.answer()
    session = await db.quiz_get_session(sid)
    if not session or session['user_id'] != uid:
        await q.edit_message_text('⚠️ نشست پیدا نشد.')
        return
    bot = q.bot
    # pollهای باز را ببند
    for open_q in await db.quiz_open_polls(sid):
        try:
            await bot.stop_poll(open_q['chat_id'], open_q['message_id'])
        except Exception:
            pass
        await db.ai_quiz_questions.update_one(
            {'_id': open_q['_id'], 'status': 'sent'},
            {'$set': {'status': 'skipped'}})
    r = await db.ai_quiz_sessions.find_one_and_update(
        {'_id': ObjectId(sid), 'status': {'$in': ['active', 'building', 'paused']}},
        {'$set': {'status': 'finished', 'finished_at': utc_now_iso()}})
    if not r:
        session = await db.quiz_get_session(sid)
    report = await build_final_report(session)
    await q.edit_message_text(report, parse_mode='HTML',
                              reply_markup=_kb([
                                  [InlineKeyboardButton(
                                      '🔁 دوباره',
                                      callback_data=f"quiz:start:{session['doc_id']}")],
                                  [InlineKeyboardButton(
                                      '📚 آزمون‌ساز', callback_data='quiz:main')]]))


# ══════════════════════════════════════════════════
#  ۹) هوک آپلود (از unified_file_handler)
# ══════════════════════════════════════════════════

async def quiz_upload_hook(update: Update,
                           context: ContextTypes.DEFAULT_TYPE) -> bool:
    """اگر کاربر در انتظارِ PDFِ آزمون‌ساز است، این فایل را می‌بلعد.

    True = مصرف شد (هندلرِ بعدی اجرا نشود)."""
    if not context.user_data.get('quiz_awaiting_pdf'):
        return False
    msg = update.message
    uid = msg.from_user.id
    context.user_data.pop('quiz_awaiting_pdf', None)
    doc = msg.document

    if not doc or (doc.mime_type or '') != 'application/pdf':
        await msg.reply_text('⚠️ فقط فایل PDF می‌پذیرم. دوباره از «آزمون‌ساز» شروع کن.')
        return True
    if msg.chat.type != 'private':
        return False     # فقط چت خصوصی

    # گیت‌ها
    if not await _setting('quiz_pdf_enabled'):
        await msg.reply_text('📚 آزمون‌ساز فعلاً غیرفعال است.')
        return True
    from subscription import feature_allowed, show_paywall
    if not await feature_allowed(uid, 'ai_chat'):
        await show_paywall(msg, uid, feature='ai_chat')
        return True
    from ai_solver import get_ai_config
    if not (await get_ai_config()).get('enabled'):
        await msg.reply_text('🤖 هوش مصنوعی فعلاً توسط مدیریت غیرفعال است.')
        return True
    max_docs = int(await _setting('quiz_max_docs_per_user'))
    docs = await db.quiz_list_documents(uid, limit=100)
    if len([d for d in docs if d.get('status') == 'ready']) >= max_docs:
        await msg.reply_text(
            f'⚠️ حداکثر {_fa(max_docs)} جزوه می‌توانی نگه داری. '
            f'اول یکی را از فهرست آزمون‌ساز حذف کن.',
            reply_markup=_kb([[InlineKeyboardButton(
                '📚 آزمون‌ساز', callback_data='quiz:main')]]))
        return True

    max_mb = int(await _setting('quiz_max_pdf_mb'))
    if doc.file_size and doc.file_size > max_mb * 1024 * 1024:
        await msg.reply_text(
            f'❌ حجم فایل ({_fa(round(doc.file_size / 1048576))} مگابایت) از '
            f'سقف {_fa(max_mb)} مگابایت بیشتر است.\n'
            f'💡 جزوه را چند بخش کنید یا نسخه‌ی سبک‌ترش را بفرست.',
            reply_markup=_kb([[InlineKeyboardButton(
                '📤 ارسال مجدد', callback_data='quiz:upload')]]))
        return True

    status = await msg.reply_text('⏳ در حال دریافت فایل … ۵٪')
    try:
        tg_file = await context.bot.get_file(doc.file_id)
        raw = await tg_file.download_as_bytearray()
    except Exception as e:
        logger.warning('getFile failed (%s) size=%s',
                       type(e).__name__, doc.file_size)
        await status.edit_text(
            '❌ نتوانستم فایل را دانلود کنم.\n'
            '💡 تلگرام برای دانلود فایل‌ها سقف ۲۰ مگابایت دارد؛ '
            'اگر فایل بزرگ‌تر است، آن را چند بخش کنید یا فشرده کنید.',
            reply_markup=_kb([[InlineKeyboardButton(
                '📤 ارسال مجدد', callback_data='quiz:upload')]]))
        return True

    name = (doc.file_name or 'جزوه').rsplit('.', 1)[0][:60]
    doc_id = await db.quiz_create_document(uid, name, len(raw),
                                           file_unique_id=doc.file_unique_id or '')
    ok = await process_document(context.bot, doc_id, uid, bytes(raw),
                                status_message=status)
    if not ok:
        doc = await db.quiz_get_document(doc_id, owner_id=uid)
        reason = (doc or {}).get('error', '')
        if reason in ('too_many_pages', 'too_big', 'not_pdf'):
            return True          # پیام دقیق خودش نشان داده شده
        return True
    doc = await db.quiz_get_document(doc_id, owner_id=uid)
    await status.delete()
    topics = doc.get('topics') or []
    lines = [f"✅ <b>{_esc(doc['name'])}</b> آماده شد!",
             f"📄 {_fa(doc.get('page_count', 0))} صفحه • "
             f"🧩 {_fa(len(topics))} مبحث"]
    if doc.get('quality_note'):
        lines.append(f"⚠️ {_esc(doc['quality_note'])}")
    lines.append('\n🎯 حالا آزمون را شروع کن:')
    await msg.reply_text('\n'.join(lines), parse_mode='HTML',
                         reply_markup=_kb([
                             [InlineKeyboardButton(
                                 '🎯 شروع آزمون',
                                 callback_data=f'quiz:start:{doc_id}')],
                             [InlineKeyboardButton(
                                 '📚 آزمون‌ساز', callback_data='quiz:main')]]))
    return True


# ══════════════════════════════════════════════════
#  ۱۰) job نگهداری
# ══════════════════════════════════════════════════

async def quiz_housekeeping_job(context: ContextTypes.DEFAULT_TYPE):
    """هر ۲ دقیقه: skip سؤال‌های سرسید گذشته + wake نشست‌های building.

    idempotent؛ همه‌چیز از DB خوانده می‌شود (همراه با ری‌استارت)."""
    try:
        now = time.time()
        # ۱) sentهایی که open_periodشان گذشته (مثلاً بعد از ری‌استارت که
        #    job تایم‌اوت از بین رفته) → skip
        stale = await db.ai_quiz_questions.find(
            {'status': 'sent', 'sent_at': {'$ne': None}}).to_list(50)
        for q in stale:
            try:
                sent_at = datetime.fromisoformat(q['sent_at'])
                age = now - sent_at.replace(tzinfo=timezone.utc).timestamp()
            except Exception:
                continue
            session = await db.quiz_get_session(q['session_id'])
            if not session:
                continue
            limit = _OPEN_PERIOD.get(session.get('mode'), 180) + 120
            if age > limit:
                r = await db.ai_quiz_questions.find_one_and_update(
                    {'_id': q['_id'], 'status': 'sent'},
                    {'$set': {'status': 'skipped', 'is_correct': False,
                              'answered_at': utc_now_iso()}})
                if r:
                    await db.quiz_update_session(session['_id'],
                                                 inc={'answered': 1})
                    if session['status'] == 'active':
                        if session['mode'] == 'practice' and \
                                not await _count_status(session['_id'], 'sent'):
                            await _send_one(session, q.get('chat_id') or 0)
                        await _maybe_finish(session,
                                            q.get('chat_id') or 0)
        # ۲) نشست‌های building سرگردان: خودکار resume نمی‌کنیم — پیام
        #    وضعیتِ زنده به chat_id نیاز دارد که بعد از ری‌استارت مطمئن
        #    نیست؛ کاربر با دکمه‌ی «ادامه» (که موجود است) برمی‌گرداند و
        #    _resume_session تولیدِ deficit را از سر می‌گیرد.
    except Exception:
        logger.debug('quiz housekeeping error', exc_info=True)


async def quiz_retention_job(context: ContextTypes.DEFAULT_TYPE):
    """روزانه: حذف اسناد قدیمی‌تر از quiz_doc_retention_days."""
    try:
        days = int(await _setting('quiz_doc_retention_days'))
        n = await db.quiz_cleanup_old_documents(days)
        if n:
            logger.info('quiz retention removed %d docs', n)
    except Exception:
        logger.debug('quiz retention error', exc_info=True)
