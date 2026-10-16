"""
پنل ادمین محتوا — نسخه نهایی با:
  ✅ ترتیب‌بندی درس‌ها (بالا/پایین)
  ✅ ترتیب‌بندی فایل‌های جلسه
  ✅ چند جلد برای رفرنس
  ✅ توضیحات اضافه (اختیاری) برای فایل
  ✅ لغو با /cancel در هر مرحله
  ✅ ویرایش و حذف همه موارد
"""
import asyncio, hashlib, os, logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import db

logger   = logging.getLogger(__name__)
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))

TERMS = ['ترم ۱', 'ترم ۲', 'ترم ۳', 'ترم ۴', 'ترم ۵', 'بانک سؤال']
CONTENT_TYPES = [
    ('video', '🎥 ویدیو کلاس'),
    ('ppt',   '📊 پاورپوینت'),
    ('pdf',   '📄 جزوه PDF'),
    ('note',  '📝 نکات'),
    ('test',  '🧪 تست'),
    ('voice', '🎙 ویس استاد'),
]

CA_WAITING_FILE = 50
CA_WAITING_TEXT = 51

# 🌊 موج C1 — callback مخصوص سطل «🌐 سراسری» در picker ورودی
GLOBAL_PICK = '__global__'
GLOBAL_INTAKE_LABEL = '🌐 سراسری'


def _clear(context):
    for k in ['ca_mode','ca_pending_file','ca_pending_file_info','ca_pending_display',
              'ca_pending_original','ca_content_type',
              'ca_edit_target','ca_edit_field','ca_ref_lang','ca_ref_volume',
              # ⭐ ماموریت ۶ — وضعیت CoW
              'ca_edit_scope','ca_pending_content','ca_pending_ref_upload',
              'ca_ref_upload_kind']:
        context.user_data.pop(k, None)


# ══════════════════════════════════════════════════════════
#  🌊 موج C1 — ابزارهای scope ورودی (Backend-Enforced)
# ══════════════════════════════════════════════════════════

async def _intake_label(intake: str) -> str:
    """کد ورودی → برچسب نمایشی؛ '' → 🌐 سراسری؛ کد ناموجود → خود کد."""
    if not intake:
        return GLOBAL_INTAKE_LABEL
    intakes = await db.get_all_intakes()
    return next((i['label'] for i in intakes if i['code'] == intake), intake)


async def _deny_scope(query, uid: int):
    """⛔ پیام استاندارد عدم دسترسی scope (§۲۷ spec) — بدون افشای جزئیات داخلی."""
    scope = await db.get_content_scope(uid)
    if scope and scope['kind'] == 'scoped':
        code = scope.get('intake') or ''
        if not code:
            # 🛡 C3.1 — نقش scoped با ورودی تنظیم‌نشده: نوشتن در هیچ سطلی
            # مجاز نیست (قبلاً «سراسری» را ویرایش می‌کرد)
            await query.answer(
                "⛔ دسترسی غیرمجاز\nبرای نقش شما هنوز ورودی‌ای تنظیم نشده؛ "
                "پس فقط مشاهده‌ی سراسری دارید.\nاز ادمین ارشد بخواهید ورودی‌تان را تعیین کند.",
                show_alert=True)
            return
        label = await _intake_label(code)
        await query.answer(
            f"⛔ دسترسی غیرمجاز\nشما فقط به محتوای ورودی «{label}» دسترسی دارید.",
            show_alert=True)
    else:
        await query.answer("⛔ دسترسی غیرمجاز", show_alert=True)


# نقشه‌ی مرکزی enforce: action → (اندیس شناسه در callback، نوع آیتم)
# resolver مربوطه intake واقعی آیتم را از DB می‌خواند — نه از callback.
ITEM_INTAKE_CHECKS = {
    'lesson_up': 'lesson', 'lesson_down': 'lesson',
    'edit_lesson_menu': 'lesson', 'edit_lesson_prompt': 'lesson',
    'del_lesson': 'lesson', 'confirm_del_lesson': 'lesson', 'lesson': 'lesson',
    'add_session_prompt': 'lesson',
    'edit_session_menu': 'session', 'edit_session_prompt': 'session',
    'del_session': 'session', 'confirm_del_session': 'session',
    'session': 'session', 'upload_content': 'session', 'sel_ctype': 'session',
    'content_up': 'content', 'content_down': 'content',
    'del_content': 'content', 'confirm_del_content': 'content',
    'ref_subject_up': 'ref_subject', 'ref_subject_down': 'ref_subject',
    'edit_ref_subject_prompt': 'ref_subject', 'del_ref_subject': 'ref_subject',
    'confirm_del_ref_subject': 'ref_subject', 'ref_subject': 'ref_subject',
    'add_ref_book_prompt': 'ref_subject',
    'ref_book_up': 'ref_book', 'ref_book_down': 'ref_book',
    'edit_ref_book_prompt': 'ref_book', 'del_ref_book': 'ref_book',
    'confirm_del_ref_book': 'ref_book', 'ref_book': 'ref_book',
    'upload_ref_volume_prompt': 'ref_book', 'upload_ref': 'ref_book',
    'del_ref_file': 'ref_file',
    # ⭐ ماموریت ۶
    'confirm_unfork_session': 'session', 'confirm_unfork_book': 'ref_book',
    'merge_new': 'session',
}


# 🌊 C1.5 — اکشن‌های «فقط‌مشاهده»: ادمین ورودی خاص حق دارد محتوای
# سراسری (intake='') را فقط‌خواندنی باز کند (§۲۲ spec: Global = هسته‌ی
# پایه، read-only برای scoped)؛ mutationها در همان map قبلی می‌مانند.
ITEM_VIEW_ACTIONS = {'lesson', 'session', 'ref_subject', 'ref_book'}


# 🌊 C3 — اکشن‌هایی که به‌جای ویرایشِ والد، «فرزند ورودی‌خاص» می‌سازند.
# برای این‌ها والدِ سراسری قابل‌بازکردن است (فرم باز می‌شود) چون خودِ والد
# تغییر نمی‌کند؛ تصمیم نهایی و نوشتن در db.scoped_child_intake گرفته می‌شود
# و در لحظه‌ی ثبت هم یک بار دیگر سنجیده می‌شود (دفاع لایه‌ای).
ITEM_CHILD_ACTIONS = {'add_session_prompt': 'lesson', 'add_ref_book_prompt': 'ref_subject'}


# ⭐ ماموریت ۶ (R1/R4) — اکشن‌های CoW: نوشتن روی آیتمِ سراسری (intake='')
# مجاز است چون در «لحظه‌ی ذخیره» به override ورودیِ سرور-تعیین‌شده هدایت
# می‌شود؛ هیچ ساخت داده‌ای در لحظه‌ی کلیک/بازکردن اتفاق نمی‌افتد.
ITEM_COW_ACTIONS = {
    'edit_session_menu', 'edit_session_prompt',
    'upload_content', 'sel_ctype',
    'content_up', 'content_down', 'del_content', 'confirm_del_content',
    'edit_ref_book_prompt',
    'upload_ref_volume_prompt', 'upload_ref', 'del_ref_file',
}


async def _cow_scope(context, uid):
    """(kind, intake) تصمیم‌گیر CoW — همیشه از سرور؛ ('', '') = CoW ممکن نیست.
    scoped → intake خودِ scope؛ ارشد → intake انتخاب‌شده (یا '' = سطل سراسری)."""
    try:
        scope = await db.get_content_scope(uid)
    except Exception:
        return '', ''
    if not scope:
        return '', ''
    if scope.get('kind') == 'scoped' and (scope.get('intake') or ''):
        return 'scoped', scope['intake']
    if scope.get('kind') == 'global':
        return 'global', ((context.user_data or {}).get('ca_intake') or '')
    return '', ''


async def _cow_session_target(context, uid, sid):
    """هدف نوشتن جلسه — Copy-on-Write در لحظه‌ی ذخیره (ماموریت ۶).
    خروجی: (sid, '')            → همان‌جا بنویس (دسترسی کامل)
            (fork_sid, note)    → روی override بنویس (ساخت در همین لحظه)
            (None, 'deny')      → دسترسی ندارد
            (None, 'choose')    → ارشد با ورودی انتخاب‌شده: صفحه‌ی انتخاب scope"""
    s_iv = await db.session_intake(sid)
    if s_iv:
        return (sid, '') if await db.can_access_intake(uid, s_iv) else (None, 'deny')
    kind, tgt = await _cow_scope(context, uid)
    if kind == 'scoped':
        fork_sid, created = await db.bs_ensure_override(sid, tgt)
        if not fork_sid:
            return None, 'deny'
        lbl = await _intake_label(tgt)
        return fork_sid, (f"⭐ برای ورودی «{lbl}» شخصی‌سازی شد؛ تغییرات فقط برای همین ورودی است."
                          if created else f"⭐ ویرایش نسخه‌ی اختصاصی ورودی «{lbl}».")
    if kind == 'global':
        if not tgt:
            return sid, ''                      # ارشد در سطل سراسری → درجا
        mode = (context.user_data or {}).get('ca_edit_scope') or ''
        if mode == 'global':
            return sid, ''
        if mode == 'intake':
            fork_sid, created = await db.bs_ensure_override(sid, tgt)
            if not fork_sid:
                return None, 'deny'
            lbl = await _intake_label(tgt)
            return fork_sid, (f"⭐ برای ورودی «{lbl}» شخصی‌سازی شد؛ تغییرات فقط برای همین ورودی است."
                              if created else f"⭐ ویرایش نسخه‌ی اختصاصی ورودی «{lbl}».")
        return None, 'choose'
    return None, 'deny'


async def _cow_book_target(context, uid, bid):
    """همان CoW برای کتاب رفرنس."""
    b_iv = await db.ref_book_intake(bid)
    if b_iv:
        return (bid, '') if await db.can_access_intake(uid, b_iv) else (None, 'deny')
    kind, tgt = await _cow_scope(context, uid)
    if kind == 'scoped':
        fork_bid, created = await db.ref_ensure_override(bid, tgt)
        if not fork_bid:
            return None, 'deny'
        lbl = await _intake_label(tgt)
        return fork_bid, (f"⭐ برای ورودی «{lbl}» شخصی‌سازی شد؛ تغییرات فقط برای همین ورودی است."
                          if created else f"⭐ ویرایش نسخه‌ی اختصاصی ورودی «{lbl}».")
    if kind == 'global':
        if not tgt:
            return bid, ''
        mode = (context.user_data or {}).get('ca_edit_scope') or ''
        if mode == 'global':
            return bid, ''
        if mode == 'intake':
            fork_bid, created = await db.ref_ensure_override(bid, tgt)
            if not fork_bid:
                return None, 'deny'
            lbl = await _intake_label(tgt)
            return fork_bid, (f"⭐ برای ورودی «{lbl}» شخصی‌سازی شد؛ تغییرات فقط برای همین ورودی است."
                              if created else f"⭐ ویرایش نسخه‌ی اختصاصی ورودی «{lbl}».")
        return None, 'choose'
    return None, 'deny'


async def _cow_content_target(context, uid, cid):
    """CoW در سطح فایل: cid → cid معادل روی هدف نوشتن جلسه.
    فایلِ فقط-در-سراسری (واگرایی R5) به‌صورت افزودنی به fork کپی می‌شود."""
    item = await db.bs_get_content_item(cid)
    if not item:
        return None, 'deny'
    sid = str(item.get('session_id', ''))
    tgt, note = await _cow_session_target(context, uid, sid)
    if tgt is None:
        return None, note
    if tgt == sid:
        return cid, note
    twin = await db.bs_content.find_one({'session_id': tgt, 'fork_of': cid})
    if twin:
        return str(twin['_id']), note
    return await db.bs_copy_content_item(cid, tgt), note


async def _cow_ref_file_target(context, uid, fid):
    """CoW در سطح فایل رفرنس: fid → معادل روی هدف نوشتن کتاب."""
    f = await db.ref_get_file(fid) if hasattr(db, 'ref_get_file') else None
    if not f:
        return None, 'deny'
    bid = str(f.get('book_id', ''))
    tgt, note = await _cow_book_target(context, uid, bid)
    if tgt is None:
        return None, note
    if tgt == bid:
        return fid, note
    twin = await db.ref_files.find_one({'book_id': tgt, 'fork_of': fid})
    if twin:
        return str(twin['_id']), note
    # کپی افزودنی تک‌فایل (همان فیلدهای ref_ensure_override)
    from time_utils import utc_now_iso as _uni
    r = await db.ref_files.insert_one({
        'book_id': tgt, 'lang': f.get('lang', 'fa'), 'volume': f.get('volume', 1),
        'description': f.get('description', ''), 'file_id': f.get('file_id', ''),
        'order': f.get('order', 0), 'uploaded_at': _uni(),
        'downloads': 0, 'notif_sent': True, 'fork_of': fid,
        'original_file_name': f.get('original_file_name', ''),
        'display_file_name': f.get('display_file_name', ''),
        'display_name': f.get('display_name', f.get('display_file_name', '')),
        'file_extension': f.get('file_extension', ''), 'mime_type': f.get('mime_type', ''),
        'file_size': f.get('file_size', 0), 'branding_enabled': f.get('branding_enabled', False),
    })
    return str(r.inserted_id), note


async def _scope_header(context, uid=None) -> str:
    """⭐ ماموریت ۶ — سربرگ محدوده‌ی یکدست روی همه‌ی صفحه‌های مدیریتی."""
    try:
        ctx = (context.user_data or {}).get('ca_intake') or ''
        if ctx:
            return f"📍 محدوده: {await _intake_label(ctx)} — تغییرات پیش‌فرض فقط همین ورودی\n\n"
        if uid is not None:
            kind, _ = await _cow_scope(context, uid)
            if kind == 'scoped':
                return "📍 محدوده: سراسری (فقط‌مشاهده — ورودی شما تنظیم نشده)\n\n"
        return "📍 محدوده: 🌐 سراسری (همه‌ی ورودی‌ها)\n\n"
    except Exception:
        return ''


async def _scope_choice_screen(query, context, item_id, kind, step):
    """صفحه‌ی انتخاب روشن برای ارشدی که ورودی‌ای انتخاب کرده و می‌خواهد
    آیتم «سراسری» را تغییر دهد (R4): 🌐 همه / ⭐ فقط همین ورودی."""
    ctx = (context.user_data or {}).get('ca_intake') or ''
    if not ctx:
        return False
    lbl = await _intake_label(ctx)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 ویرایش سراسری (همه‌ی ورودی‌ها)",
                              callback_data=f'ca:escope:{item_id}:g:{step}')],
        [InlineKeyboardButton(f"⭐ فقط برای ورودی {lbl}",
                              callback_data=f'ca:escope:{item_id}:i:{step}')],
        [InlineKeyboardButton("❌ لغو", callback_data=f'ca:{kind}:{item_id}')],
    ])
    await query.edit_message_text(
        "⚖️ <b>این مورد سراسری است (🌐)</b>\n\n"
        "تغییر را برای کدام محدوده اعمال کنید؟\n"
        "• 🌐 سراسری: روی <b>همه‌ی ورودی‌ها</b> اعمال می‌شود\n"
        f"• ⭐ فقط ورودی {lbl}: نسخه‌ی اختصاصی همین ورودی ساخته/ویرایش می‌شود؛ بقیه سراسری می‌مانند",
        parse_mode='HTML', reply_markup=kb)
    return True


async def _resolve_item_intake(kind: str, item_id: str) -> str:
    """intake واقعی آیتم از روی DB (زنجیره‌ی والد) — پیش‌فرض '' = سراسری."""
    try:
        if kind == 'lesson':
            return await db.lesson_intake(item_id)
        if kind == 'session':
            return await db.session_intake(item_id)
        if kind == 'content':
            return await db.content_intake(item_id)
        if kind == 'ref_subject':
            return await db.ref_subject_intake(item_id)
        if kind == 'ref_book':
            return await db.ref_book_intake(item_id)
        if kind == 'ref_file':
            return await db.ref_file_intake(item_id)
    except Exception as _e:
        logger.debug(f"_resolve_item_intake {kind}:{item_id} failed: {_e}")
    return ''


async def _enforce_item_scope(query, uid: int, action: str, parts) -> bool:
    """True اگر actor به آیتمِ callback دسترسی دارد؛ وگرنه ⛔ + False."""
    kind = ITEM_INTAKE_CHECKS.get(action)
    if not kind or len(parts) < 3:
        return True
    item_intake = await _resolve_item_intake(kind, parts[2])
    if await db.can_access_intake(uid, item_intake):
        return True
    # 🌊 C1.5 — مشاهده‌ی فقط‌خواندنیِ سراسری برای ادمین ورودی خاص
    if action in ITEM_VIEW_ACTIONS and item_intake == '':
        scope = await db.get_content_scope(uid)
        if scope and scope.get('kind') == 'scoped':
            return True
    # 🌊 C3 — ساخت «فرزند ورودی‌خاص» زیر والدِ سراسری (والد دست‌نخورده)
    if action in ITEM_CHILD_ACTIONS and item_intake == '':
        if await db.scoped_child_intake(uid, item_intake) is not None:
            return True
    # ⭐ ماموریت ۶ — CoW: نوشتن روی آیتم سراسری مجاز است چون در لحظه‌ی
    # ذخیره به override ورودیِ سرور-تعیین‌شده هدایت می‌شود؛ intake هدف
    # هرگز از callback/کلاینت نمی‌آید.
    if action in ITEM_COW_ACTIONS and item_intake == '':
        _scope = await db.get_content_scope(uid)
        if _scope and _scope.get('kind') == 'global':
            return True   # ارشد: همیشه می‌تواند سراسری را بنویسد (انتخاب scope بعداً)
        if _scope and _scope.get('kind') == 'scoped' and (_scope.get('intake') or ''):
            return True   # ورودی‌خاص: نوشتن به override خودش هدایت می‌شود
    await _deny_scope(query, uid)
    return False


def _back_btn(label, cb):
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=cb)]])


async def _exec_content_action(query, context, uid, action, cid):
    """⭐ ماموریت ۶ — اجرای عملیات فایل (⬆️/⬇️/🗑) با Copy-on-Write:
    هدف نوشتن از سرور تعیین می‌شود؛ در صورت نیاز override ساخته می‌شود."""
    tgt_cid, note = await _cow_content_target(context, uid, cid)
    if not tgt_cid:
        if note == 'choose':
            _item = await db.bs_get_content_item(cid) or {}
            _sid = str(_item.get('session_id', ''))
            context.user_data['ca_pending_content'] = (action, cid)
            await _scope_choice_screen(query, context, _sid, 'session', 'c')
        else:
            await _deny_scope(query, uid)
        return
    item = await db.bs_get_content_item(tgt_cid) or {}
    sid = str(item.get('session_id', ''))
    if sid:
        context.user_data['ca_session_id'] = sid
    if action == 'content_up':
        await db.reorder_content_up(tgt_cid, sid)
    elif action == 'content_down':
        await db.reorder_content_down(tgt_cid, sid)
    elif action == 'confirm_del_content':
        item_before = await db.bs_get_content_item(tgt_cid)
        await db.bs_delete_content(tgt_cid)
        if item_before:
            type_fa = dict(CONTENT_TYPES).get(item_before.get('type', ''), 'فایل')
            try:
                await _audit(context, uid, f"حذف {type_fa}",
                    severity='HIGH', target_id=tgt_cid, target_type='content',
                    target_label=item_before.get('description', '')[:60] or type_fa,
                    tags=['حذف_محتوا'])
            except Exception as _e:
                logger.warning(f"del_content audit failed: {_e}")
    if note:
        try:
            await query.answer(note[:190])
        except Exception:
            pass
    await _show_session_content(query, context, sid)


async def _exec_ref_file_action(query, context, uid, action, fid):
    """⭐ ماموریت ۶ — حذف فایل رفرنس با CoW."""
    tgt_fid, note = await _cow_ref_file_target(context, uid, fid)
    if not tgt_fid:
        if note == 'choose':
            _f = (await db.ref_get_file(fid) if hasattr(db, 'ref_get_file') else None) or {}
            _bid = str(_f.get('book_id', ''))
            context.user_data['ca_pending_ref_upload'] = (action, fid)
            await _scope_choice_screen(query, context, _bid, 'ref_book', 'bf')
        else:
            await _deny_scope(query, uid)
        return
    if action == 'del_ref_file':
        _reffile = await db.ref_get_file(tgt_fid) if hasattr(db, 'ref_get_file') else None
        _ref_label = f"جلد {_reffile.get('volume','')}" if _reffile else tgt_fid
        await db.ref_delete_file(tgt_fid)
        try:
            await _audit(context, uid, "حذف فایل رفرنس",
                severity='HIGH', target_id=tgt_fid, target_type='ref_file',
                target_label=_ref_label, tags=['حذف_رفرنس'])
        except Exception as _e:
            logger.warning(f"del_ref_file audit failed: {_e}")
        bid = context.user_data.get('ca_ref_book_id', '')
        _tgt_bid, _ = await _cow_book_target(context, uid, bid) if bid else (None, '')
        if _tgt_bid:
            context.user_data['ca_ref_book_id'] = _tgt_bid
            bid = _tgt_bid
        if note:
            try:
                await query.answer(note[:190])
            except Exception:
                pass
        await query.edit_message_text("✅ فایل حذف شد.",
            reply_markup=_back_btn("🔙 بازگشت", f'ca:ref_book:{bid}'))


# ══════════════════════════════════════════════════════════
#  Callback اصلی
# ══════════════════════════════════════════════════════════

async def _audit(context, uid, action, *, severity='INFO', details='',
                 target_id='', target_type='', target_label='',
                 before=None, after=None, tags=None):
    """🧹 موج Q2/W6 — helper مشترک audit پنل محتوا (حذف ۱۲ بلوک تکراری).
    🆕 Audit Refactor (§16,§34,§35): هرگز Silent نیست —
       • Delivery failure → warning + outbox retry (send_audit_log مرکزی)
       • Audit exception → logger.warning (قبلاً bare except:pass بود و شکست بی‌صدا می‌ماند)
       • اقدام اصلی هرگز به خاطر audit نمی‌شکند (fail-open) اما ناظر می‌بیند.
    """
    try:
        from utils import send_audit_log
        actor = await db.get_user(uid)
        actor_name = actor.get('name', 'ادمین محتوا') if actor else 'ادمین محتوا'
        await send_audit_log(
            context.bot, 'content', actor_name, uid, action,
            module='Content', severity=severity,
            actor_role=await db.get_actor_role_label(uid),
            target_id=target_id, target_type=target_type, target_label=target_label,
            before=before, after=after,
            details=details, tags=tags)
    except Exception as _e:
        # §16: هرگز silently swallow نشود — حداقل warning + تشخیص نوع شکست
        logger.warning(f"content _audit failed action={action!r} uid={uid}: {type(_e).__name__}: {_e}")


# ══════════════════════════════════════════════════════════
#  🌊 Q2-W9 — هندلرهای Fork/Unfork استخراج‌شده از content_admin_callback
#  (بدون تغییر رفتار؛ scope/audit و ترتیب پیام‌ها عیناً حفظ شده)
# ══════════════════════════════════════════════════════════
async def _h_fork_session(query, context, uid: int, _cscope, is_scoped: bool, parts: list):
    """شاخه‌ی fork_session — ساخت نسخه‌ی اختصاصی جلسه برای ورودی هدف."""
    base_id = parts[2]
    _target = (_cscope.get('intake') or '') if is_scoped \
        else (context.user_data.get('ca_intake') or '')
    if not _target:
        await query.answer(
            "ℹ️ سفارشی‌سازی روی سطل سراسری معنا ندارد؛ "
            "ابتدا یک ورودی را انتخاب کنید.", show_alert=True)
        return ConversationHandler.END
    new_sid = await db.bs_fork_session(base_id, _target)
    if not new_sid:
        await query.answer("❌ فقط جلسه‌ی سراسری قابل سفارشی‌سازی است.",
                           show_alert=True)
        return ConversationHandler.END
    try:
        _base = await db.bs_get_session(base_id) or {}
        await _audit(context, uid, "ساخت نسخه‌ی اختصاصی (Fork) جلسه",
            severity='INFO',
            details=(f"🍴 Fork Session: {_base.get('topic', '')}\n"
                     f"🏷 ورودی: {await _intake_label(_target)}"),
            tags=['فورک_محتوا'])
    except Exception as _e:
        logger.warning(f"fork_session audit failed: {_e}")
    await query.answer("⭐ نسخه‌ی اختصاصی ساخته شد — حالا قابل ویرایش است")
    _ls = await db.bs_get_session(base_id)
    await _show_sessions(query, context, (_ls or {}).get('lesson_id', ''))
    return ConversationHandler.END


async def _h_unfork_session(query, context, uid: int, _cscope, is_scoped: bool, parts: list):
    """شاخه‌ی unfork_session — تأییدِ بازگردانی جلسه‌ی فورک‌شده به سراسری."""
    fork_id = parts[2]
    _fi = await db.session_intake(fork_id)
    if not await db.can_access_intake(uid, _fi):
        await _deny_scope(query, uid)
        return ConversationHandler.END
    fork = await db.bs_get_session(fork_id) or {}
    # ⭐ م6: حذف override = از دست رفتن ویرایش‌های همین ورودی → تأیید صریح
    await query.edit_message_text(
        "↩️ <b>بازگشت به نسخه‌ی سراسری؟</b>\n\n"
        f"نسخه‌ی اختصاصی جلسه {fork.get('number','')} — «{fork.get('topic','')}» "
        f"برای ورودی «{await _intake_label(_fi)}» و همه‌ی تغییراتش حذف می‌شود؛ "
        "نسخه‌ی سراسری دست‌نخورده می‌ماند.",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("↩️ بله، بازگشت به سراسری",
                                  callback_data=f'ca:confirm_unfork_session:{fork_id}')],
            [InlineKeyboardButton("❌ لغو", callback_data=f'ca:session:{fork_id}')],
        ]))
    return ConversationHandler.END


async def _do_unfork_session(query, context, uid: int, fork_id: str):
    """اجرای بازگردانی (پس از تأیید)."""
    _fi = await db.session_intake(fork_id)
    if not await db.can_access_intake(uid, _fi):
        await _deny_scope(query, uid)
        return ConversationHandler.END
    base_id = await db.bs_unfork_session(fork_id)
    if not base_id:
        await query.answer("❌ این جلسه نسخه‌ی اختصاصی نیست.",
                           show_alert=True)
        return ConversationHandler.END
    try:
        await _audit(context, uid, "بازگردانی جلسه به نسخه‌ی سراسری (حذف Fork)",
            severity='INFO',
            details=f"↩️ Unfork Session\n🏷 ورودی: {await _intake_label(_fi)}",
            tags=['فورک_محتوا'])
    except Exception as _e:
        logger.warning(f"unfork_session audit failed: {_e}")
    await query.answer("↩️ به نسخه‌ی سراسری بازگشت")
    _ls = await db.bs_get_session(base_id)
    await _show_sessions(query, context, (_ls or {}).get('lesson_id', ''))
    return ConversationHandler.END


async def _h_fork_book(query, context, uid: int, _cscope, is_scoped: bool, parts: list):
    """شاخه‌ی fork_book — ساخت نسخه‌ی اختصاصی کتاب رفرنس برای ورودی هدف."""
    base_bid = parts[2]
    _target = (_cscope.get('intake') or '') if is_scoped \
        else (context.user_data.get('ca_intake') or '')
    if not _target:
        await query.answer(
            "ℹ️ سفارشی‌سازی روی سطل سراسری معنا ندارد؛ "
            "ابتدا یک ورودی را انتخاب کنید.", show_alert=True)
        return ConversationHandler.END
    new_bid = await db.ref_fork_book(base_bid, _target)
    if not new_bid:
        await query.answer("❌ فقط کتاب سراسری قابل سفارشی‌سازی است.",
                           show_alert=True)
        return ConversationHandler.END
    try:
        _bb = await db.ref_get_book(base_bid) or {}
        await _audit(context, uid, "ساخت نسخه‌ی اختصاصی (Fork) کتاب رفرنس",
            severity='INFO',
            details=(f"🍴 Fork Book: {_bb.get('name', '')}\n"
                     f"🏷 ورودی: {await _intake_label(_target)}"),
            tags=['فورک_محتوا'])
    except Exception as _e:
        logger.warning(f"fork_book audit failed: {_e}")
    await query.answer("⭐ نسخه‌ی اختصاصی کتاب ساخته شد")
    _bk = await db.ref_get_book(base_bid)
    await _show_ref_books(query, context, (_bk or {}).get('subject_id', ''))
    return ConversationHandler.END


async def _h_unfork_book(query, context, uid: int, _cscope, is_scoped: bool, parts: list):
    """شاخه‌ی unfork_book — تأییدِ بازگردانی کتاب فورک‌شده به سراسری."""
    fork_bid = parts[2]
    _fi = await db.ref_book_intake(fork_bid)
    if not await db.can_access_intake(uid, _fi):
        await _deny_scope(query, uid)
        return ConversationHandler.END
    fork = await db.ref_get_book(fork_bid) or {}
    await query.edit_message_text(
        "↩️ <b>بازگشت به نسخه‌ی سراسری؟</b>\n\n"
        f"نسخه‌ی اختصاصی کتاب «{fork.get('name','')}» برای ورودی "
        f"«{await _intake_label(_fi)}» و همه‌ی تغییراتش حذف می‌شود؛ "
        "نسخه‌ی سراسری دست‌نخورده می‌ماند.",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("↩️ بله، بازگشت به سراسری",
                                  callback_data=f'ca:confirm_unfork_book:{fork_bid}')],
            [InlineKeyboardButton("❌ لغو", callback_data=f'ca:ref_book:{fork_bid}')],
        ]))
    return ConversationHandler.END


async def _do_unfork_book(query, context, uid: int, fork_bid: str):
    """اجرای بازگردانی کتاب (پس از تأیید)."""
    _fi = await db.ref_book_intake(fork_bid)
    base_bid = await db.ref_unfork_book(fork_bid)
    if not base_bid:
        await query.answer("❌ این کتاب نسخه‌ی اختصاصی نیست.",
                           show_alert=True)
        return ConversationHandler.END
    try:
        await _audit(context, uid, "بازگردانی کتاب به نسخه‌ی سراسری (حذف Fork)",
            severity='INFO',
            details=f"↩️ Unfork Book\n🏷 ورودی: {await _intake_label(_fi)}",
            tags=['فورک_محتوا'])
    except Exception as _e:
        logger.warning(f"unfork_book audit failed: {_e}")
    await query.answer("↩️ به نسخه‌ی سراسری بازگشت")
    _bk = await db.ref_get_book(base_bid)
    await _show_ref_books(query, context, (_bk or {}).get('subject_id', ''))
    return ConversationHandler.END

# ─ آپلود جلد رفرنس ─


async def content_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer()
    uid    = update.effective_user.id
    data   = query.data
    parts  = data.split(':')
    action = parts[1] if len(parts) > 1 else 'main'

    if not await db.is_content_admin(uid):
        await query.answer("❌ دسترسی ندارید!", show_alert=True); return

    # ══════════════════════════════════════════════════════
    #  🌊 موج C1 — گیت scope ورودی (Backend-Enforced، §۸/§۱۱ spec)
    #  • ادمین scoped: context را روی scope خودش قفل می‌کنیم —
    #    هیچ‌کدام از داده‌های callback/user_data trusted نیستند.
    #  • ادمین ارشد (global): بدون context انتخاب‌شده → picker.
    #  • تمام اکشن‌های آیتم‌محور: intake واقعی آیتم از DB خوانده
    #    و با scope کاربر تطبیق داده می‌شود (ضد callback-manipulation).
    # ══════════════════════════════════════════════════════
    _cscope = await db.get_content_scope(uid)
    if not _cscope:
        await query.answer("❌ دسترسی ندارید!", show_alert=True); return
    is_scoped = (_cscope['kind'] == 'scoped')
    if is_scoped:
        context.user_data['ca_intake'] = _cscope.get('intake') or ''

    # ─ انتخاب/تغییر ورودی (فقط ادمین ارشد) ─
    if action == 'intake':
        if is_scoped:
            await _deny_scope(query, uid); return
        pick = parts[2] if len(parts) > 2 else ''
        code = '' if pick == GLOBAL_PICK else pick
        if code:
            intakes = await db.get_all_intakes()
            if not any(i['code'] == code for i in intakes):
                await query.answer("❌ ورودی نامعتبر است!", show_alert=True); return
        # تغییر ورودی فقط عوض‌کردن context نمایشی پنل است و هیچ داده‌ای
        # در DB تغییر نمی‌دهد؛ بنا به سیاست لاگ، برای این navigation ساده
        # نه در audit و نه در گروه لاگ محتوا پیام ارسال نمی‌شود.
        context.user_data['ca_intake'] = code
        await query.answer(f"📅 {await _intake_label(code)}")
        await _show_main(query, uid, context)
        return ConversationHandler.END

    elif action == 'change_intake':
        if is_scoped:
            await _deny_scope(query, uid); return
        await _show_intake_picker(query)
        return ConversationHandler.END

    # 🔒 C1.5/C3 — دکمه‌ی جداکننده‌ی «فقط‌خواندنی» (بدون عملکرد نوشتاری)
    elif action == 'ro_info':
        # ادمین ارشد داخل یک ورودی: سراسری باز، قابل ویرایش، و با ✂️ مخصوص همان ورودی است.
        if not is_scoped:
            await query.answer(
                "🌐 این‌ها محتوای سراسری‌اند. می‌توانید همان‌جا ویرایش کنید، "
                "یا با ✂️ یک نسخه‌ی اختصاصی برای ورودی انتخاب‌شده بسازید. "
                "نسخه‌ی سراسری برای بقیه دست‌نخورده می‌ماند.",
                show_alert=True)
            return ConversationHandler.END
        # 🌊 C3 — به نماینده یادآوری می‌کنیم که ساختن «جلسه‌ی مخصوص ورودی خودش»
        # آزاد است؛ وگرنه پیام ثابت «فقط‌خواندنی» فکر می‌دهد کل پنل قفل است.
        can_child = await db.scoped_child_intake(uid, '') not in (None, '')
        await query.answer(
            "🔒 محتوای سراسری — فقط‌خواندنی؛ مدیریت آن نزد 🎓 ادمین ارشد محتواست."
            + ("\n\n➕ اما می‌توانید «جلسه» یا «کتاب رفرنس» جدید را با برچسب "
               "«فقط ورودی خودم» داخل درس/موضوع سراسری بسازید."
               if can_child else ""),
            show_alert=True)
        return ConversationHandler.END

    ca_intake = context.user_data.get('ca_intake')

    # ادمین ارشد بدون context → اول picker (§۵ spec: اولین صفحه = انتخاب ورودی)
    if not is_scoped and ca_intake is None and action != 'main':
        await _show_intake_picker(query)
        return ConversationHandler.END

    # enforce آیتم‌محور — قبل از هر نمایش/تغییر (ضد ID manipulation)
    if not await _enforce_item_scope(query, uid, action, parts):
        return ConversationHandler.END

    KEEP_MODE = ('sel_ctype','upload_ref','add_lesson_prompt','add_session_prompt',
                 'add_ref_subject_prompt','add_ref_book_prompt','add_faq_prompt',
                 'edit_faq_prompt','edit_faq',
                 'upload_ref_volume_prompt','upload_content',
                 'edit_lesson_prompt','edit_session_prompt',
                 'edit_ref_subject_prompt','edit_ref_book_prompt',
                 'urlimport',
                 'confirm_filename','skip_filename','edit_filename','cancel_filename')  # 📄 rename flow
    if action not in KEEP_MODE:
        _clear(context)

    # ── 📄 File naming callbacks (must preserve pending file) ──
    if action in ('confirm_filename','skip_filename','edit_filename','cancel_filename'):
        # ensure pending exists
        pending_info = context.user_data.get('ca_pending_file_info')
        if not pending_info:
            await query.answer("❌ فایل منقضی شده، دوباره فایل بفرستید", show_alert=True)
            _clear(context)
            return ConversationHandler.END
        if action == 'cancel_filename':
            _clear(context)
            await query.edit_message_text("❌ عملیات لغو شد.")
            return ConversationHandler.END
        if action == 'edit_filename':
            # back to waiting_filename
            context.user_data['ca_mode'] = 'waiting_filename'
            await query.edit_message_text(
                "✏️ <b>نام جدید را بفرستید:</b>\n"
                f"نام فعلی: <code>{context.user_data.get('ca_pending_original','')}</code>\n"
                "پسوند حفظ می‌شود. ⌨️ /cancel",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⏭ استفاده از نام فعلی", callback_data="ca:skip_filename")],
                    [InlineKeyboardButton("❌ لغو", callback_data="ca:cancel_filename")]
                ]))
            return ConversationHandler.END
        if action == 'skip_filename':
            # use original as display
            orig = context.user_data.get('ca_pending_original', '') or pending_info.get('original_name','')
            context.user_data['ca_pending_display'] = orig
            # move to description step
            target = context.user_data.get('ca_pending_target', 'session')
            if target == 'ref':
                bid = context.user_data.get('ca_ref_book_id','')
                lang = context.user_data.get('ca_ref_lang','fa')
                vol = context.user_data.get('ca_ref_volume', 1)
                ll = "🇮🇷 فارسی" if lang == 'fa' else "🌐 لاتین"
                context.user_data['ca_mode'] = 'waiting_ref_description'
                await query.edit_message_text(
                    f"✅ نام نهایی: <code>{orig}</code>\n\n"
                    f"📝 توضیح اختیاری برای {ll} جلد {vol}:\n"
                    "اگر توضیحی ندارید <code>-</code> بزنید:\n⌨️ /cancel",
                    parse_mode='HTML',
                    reply_markup=_back_btn("❌ لغو", f'ca:ref_book:{bid}'))
            else:
                sid = context.user_data.get('ca_session_id','')
                context.user_data['ca_mode'] = 'waiting_description'
                await query.edit_message_text(
                    f"✅ نام نهایی: <code>{orig}</code>\n\n"
                    "📝 توضیح اختیاری برای این فایل:\n"
                    "(مثلاً: ویدیو قسمت اول)\n"
                    "اگر توضیحی ندارید <code>-</code> بزنید:\n⌨️ /cancel",
                    parse_mode='HTML',
                    reply_markup=_back_btn("❌ لغو", f'ca:session:{sid}'))
            return ConversationHandler.END
        if action == 'confirm_filename':
            # pending_display already set via text handler
            display = context.user_data.get('ca_pending_display', '') or context.user_data.get('ca_pending_original','')
            target = context.user_data.get('ca_pending_target', 'session')
            if target == 'ref':
                bid = context.user_data.get('ca_ref_book_id','')
                lang = context.user_data.get('ca_ref_lang','fa')
                vol = context.user_data.get('ca_ref_volume', 1)
                ll = "🇮🇷 فارسی" if lang == 'fa' else "🌐 لاتین"
                context.user_data['ca_mode'] = 'waiting_ref_description'
                await query.edit_message_text(
                    f"✅ نام نهایی: <code>{display}</code>\n\n"
                    f"📝 توضیح اختیاری برای {ll} جلد {vol}:\n"
                    "اگر توضیحی ندارید <code>-</code> بزنید:\n⌨️ /cancel",
                    parse_mode='HTML',
                    reply_markup=_back_btn("❌ لغو", f'ca:ref_book:{bid}'))
            else:
                sid = context.user_data.get('ca_session_id','')
                context.user_data['ca_mode'] = 'waiting_description'
                await query.edit_message_text(
                    f"✅ نام نهایی: <code>{display}</code>\n\n"
                    "📝 توضیح اختیاری برای این فایل:\n"
                    "اگر توضیحی ندارید <code>-</code> بزنید:\n⌨️ /cancel",
                    parse_mode='HTML',
                    reply_markup=_back_btn("❌ لغو", f'ca:session:{sid}'))
            return ConversationHandler.END

    from_admin = action.endswith('_admin')
    back_main  = 'admin:cat_content' if from_admin else 'ca:main'

    # ════ منوی اصلی ════
    if action == 'main':
        if not is_scoped and ca_intake is None:
            await _show_intake_picker(query)
            return ConversationHandler.END
        await _show_main(query, uid, context)

    # ══════════ علوم پایه ══════════

    elif action in ('terms','terms_admin'):
        context.user_data['ca_from_admin'] = from_admin
        await _show_terms(query, back=back_main, context=context)

    elif action == 'term':
        idx = int(parts[2])
        context.user_data.update({'ca_term': TERMS[idx], 'ca_term_idx': idx})
        fa  = context.user_data.get('ca_from_admin', False)
        await _show_lessons(query, context, TERMS[idx],
                            back='ca:terms_admin' if fa else 'ca:terms')

    # ─ افزودن درس ─
    elif action == 'add_lesson_prompt':
        idx  = int(parts[2]); term = TERMS[idx]
        # 🛡 C3.1 — بدون ورودیِ تنظیم‌شده، ساختن در سطل سراسری مجاز نیست
        if not await db.can_access_intake(uid, context.user_data.get('ca_intake') or ''):
            await query.answer(
                "⛔ برای نقش شما هنوز ورودی‌ای تنظیم نشده — از ادمین ارشد بخواهید.\n"
                "پیش از آن فقط مشاهده‌ی سراسری دارید.", show_alert=True)
            return
        context.user_data.update({'ca_term_idx': idx, 'ca_term': term, 'ca_mode': 'add_lesson'})
        await query.edit_message_text(
            f"➕ <b>درس جدید — {term}</b>\n\n"
            "فرمت: <code>نام درس, نام استاد</code>\n"
            "مثال: <code>فیزیولوژی, دکتر احمدی</code>\n"
            "<i>استاد اختیاری</i>\n\n⌨️ /cancel برای لغو",
            parse_mode='HTML', reply_markup=_back_btn("❌ لغو", f'ca:term:{idx}'))

    # ─ ترتیب درس‌ها ─
    elif action == 'lesson_up':
        lid = parts[2]; idx = context.user_data.get('ca_term_idx', 0)
        lesson = await db.bs_get_lesson(lid) or {}
        await db.reorder_up('bs_lessons', lid,
            {'term': lesson.get('term') or TERMS[idx], 'intake': lesson.get('intake') or ''})
        fa = context.user_data.get('ca_from_admin', False)
        await _show_lessons(query, context, TERMS[idx],
                            back='ca:terms_admin' if fa else 'ca:terms')

    elif action == 'lesson_down':
        lid = parts[2]; idx = context.user_data.get('ca_term_idx', 0)
        lesson = await db.bs_get_lesson(lid) or {}
        await db.reorder_down('bs_lessons', lid,
            {'term': lesson.get('term') or TERMS[idx], 'intake': lesson.get('intake') or ''})
        fa = context.user_data.get('ca_from_admin', False)
        await _show_lessons(query, context, TERMS[idx],
                            back='ca:terms_admin' if fa else 'ca:terms')

    # ─ ویرایش درس ─
    elif action == 'edit_lesson_menu':
        lid = parts[2]; lesson = await db.bs_get_lesson(lid)
        if not lesson: return
        kb = [
            [InlineKeyboardButton("✏️ ویرایش نام درس",   callback_data=f'ca:edit_lesson_prompt:{lid}:name')],
            [InlineKeyboardButton("✏️ ویرایش نام استاد", callback_data=f'ca:edit_lesson_prompt:{lid}:teacher')],
            [InlineKeyboardButton("🔙 بازگشت",            callback_data=f'ca:lesson:{lid}')],
        ]
        await query.edit_message_text(
            f"✏️ <b>ویرایش درس «{lesson['name']}»</b>",
            parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))

    elif action == 'edit_lesson_prompt':
        lid = parts[2]; field = parts[3]
        lesson = await db.bs_get_lesson(lid)
        if not lesson: return
        label = 'نام درس' if field == 'name' else 'نام استاد'
        context.user_data.update({'ca_mode':'edit_lesson','ca_edit_target':lid,'ca_edit_field':field})
        await query.edit_message_text(
            f"✏️ <b>ویرایش {label}</b>\n\nفعلی: <b>{lesson.get(field,'')}</b>\n\nجدید بنویسید:\n⌨️ /cancel",
            parse_mode='HTML', reply_markup=_back_btn("❌ لغو", f'ca:lesson:{lid}'))

    # ─ حذف درس ─
    elif action == 'del_lesson':
        lid = parts[2]; lesson = await db.bs_get_lesson(lid)
        if not lesson: return
        idx = context.user_data.get('ca_term_idx', 0)
        _hint = _global_delete_hint(lesson.get('intake') or '', context)
        await query.edit_message_text(
            f"⚠️ <b>حذف درس «{lesson['name']}»؟</b>\nتمام جلسات و محتوا حذف می‌شود!{_hint}",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🗑 بله", callback_data=f'ca:confirm_del_lesson:{lid}')],
                [InlineKeyboardButton("❌ لغو", callback_data=f'ca:term:{idx}')],
            ]))

    elif action == 'confirm_del_lesson':
        lid = parts[2]; lesson = await db.bs_get_lesson(lid)
        name = lesson['name'] if lesson else ''
        await db.bs_delete_lesson(lid)
        idx = context.user_data.get('ca_term_idx', 0)
        await _audit(context, uid, "حذف درس",
            severity='HIGH',
            target_id=lid,
            target_type='lesson',
            target_label=name,
            tags=['حذف_درس'])
        await query.edit_message_text(f"✅ درس «{name}» حذف شد.",
            reply_markup=_back_btn("🔙 بازگشت", f'ca:term:{idx}'))

    # ─ جلسات ─
    elif action == 'lesson':
        lid = parts[2]; context.user_data['ca_lesson_id'] = lid
        await _show_sessions(query, context, lid)

    elif action == 'add_session_prompt':
        lid = parts[2]
        context.user_data.update({'ca_lesson_id': lid, 'ca_mode': 'add_session'})
        lesson = await db.bs_get_lesson(lid)
        # 🌊 C3 — اگر والد سراسری است، فرزند در سطل scope خودِ actor نوشته می‌شود
        _child = await db.scoped_child_intake(uid, (lesson or {}).get('intake') or '')
        next_n = await db.bs_next_session_number(lid, _child or None)
        scope_line = ""
        if _child:
            scope_line = (f"📅 <b>فقط برای ورودی «{await _intake_label(_child)}»</b> — "
                          f"نسخه‌ی سراسری این درس تغییر نمی‌کند.\n\n")
        await query.edit_message_text(
            f"➕ <b>جلسه جدید — {lesson.get('name','') if lesson else ''}</b>\n\n"
            f"{scope_line}"
            f"فرمت: <code>شماره, موضوع, استاد</code>\n"
            f"مثال: <code>{next_n}, فیزیولوژی کلیه, دکتر احمدی</code>\n"
            f"<i>شماره پیشنهادی: {next_n} — استاد اختیاری</i>\n\n⌨️ /cancel",
            parse_mode='HTML', reply_markup=_back_btn("❌ لغو", f'ca:lesson:{lid}'))

    elif action == 'edit_session_menu':
        sid = parts[2]; session = await db.bs_get_session(sid)
        if not session: return
        context.user_data.pop('ca_edit_scope', None)   # ⭐ م6: انتخاب تازه در هر ورود
        hdr = ''
        if not await db.session_intake(sid):
            _kind, _tgt = await _cow_scope(context, uid)
            if _kind == 'scoped' and _tgt:
                hdr = (f"🌐 سراسری — تغییر در <b>نسخه‌ی اختصاصی ورودی "
                       f"{await _intake_label(_tgt)}</b> ذخیره می‌شود (⭐).\n\n")
            elif _kind == 'global' and _tgt:
                # ⭐ م6 (R4): ارشدِ در محدوده‌ی یک ورودی — انتخاب روشن قبل از ویرایش
                if await _scope_choice_screen(query, context, sid, 'session', 'e'):
                    return ConversationHandler.END
            else:
                hdr = "🌐 سراسری — تغییر برای <b>همه‌ی ورودی‌ها</b> اعمال می‌شود.\n\n"
        kb = [
            [InlineKeyboardButton("✏️ موضوع",      callback_data=f'ca:edit_session_prompt:{sid}:topic')],
            [InlineKeyboardButton("✏️ نام استاد",  callback_data=f'ca:edit_session_prompt:{sid}:teacher')],
            [InlineKeyboardButton("✏️ شماره جلسه", callback_data=f'ca:edit_session_prompt:{sid}:number')],
            [InlineKeyboardButton("🔙 بازگشت",     callback_data=f'ca:session:{sid}')],
        ]
        await query.edit_message_text(
            f"{hdr}✏️ <b>ویرایش جلسه {session.get('number','')} — {session.get('topic','')}</b>",
            parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))

    elif action == 'escope':
        # ⭐ ماموریت ۶ — نتیجه‌ی صفحه‌ی انتخاب (فقط ارشد؛ دفاع لایه‌ای زیر)
        item_id = parts[2]; choice = parts[3]
        step = parts[4] if len(parts) > 4 else 'e'
        _sc = await db.get_content_scope(uid)
        if not (_sc and _sc.get('kind') == 'global'):
            await _deny_scope(query, uid)
            return ConversationHandler.END
        context.user_data['ca_edit_scope'] = 'global' if choice == 'g' else 'intake'
        _lbl = await _intake_label(context.user_data.get('ca_intake', ''))
        if step == 'e':
            session = await db.bs_get_session(item_id)
            if not session: return
            hdr = ("🌐 <b>ویرایش سراسری</b> — تغییر برای همه‌ی ورودی‌ها اعمال می‌شود.\n\n"
                   if choice == 'g' else
                   f"⭐ <b>فقط ورودی {_lbl}</b> — در اولین ذخیره، نسخه‌ی اختصاصی ساخته می‌شود.\n\n")
            kb = [
                [InlineKeyboardButton("✏️ موضوع",      callback_data=f'ca:edit_session_prompt:{item_id}:topic')],
                [InlineKeyboardButton("✏️ نام استاد",  callback_data=f'ca:edit_session_prompt:{item_id}:teacher')],
                [InlineKeyboardButton("✏️ شماره جلسه", callback_data=f'ca:edit_session_prompt:{item_id}:number')],
                [InlineKeyboardButton("🔙 بازگشت",     callback_data=f'ca:session:{item_id}')],
            ]
            await query.edit_message_text(
                f"{hdr}✏️ <b>ویرایش جلسه {session.get('number','')} — {session.get('topic','')}</b>",
                parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))
        elif step == 'u':
            kb = [[InlineKeyboardButton(label, callback_data=f'ca:sel_ctype:{item_id}:{ct}')]
                  for ct, label in CONTENT_TYPES]
            kb.append([InlineKeyboardButton("❌ لغو", callback_data=f'ca:session:{item_id}')])
            hdr = ("🌐 <b>آپلود سراسری</b> — فایل برای همه‌ی ورودی‌ها قابل‌مشاهده می‌شود.\n\n"
                   if choice == 'g' else
                   f"⭐ <b>فقط ورودی {_lbl}</b> — در لحظه‌ی ثبت، نسخه‌ی اختصاصی ساخته می‌شود.\n\n")
            await query.edit_message_text(f"{hdr}📤 <b>نوع محتوا:</b>",
                parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))
        elif step == 'c':
            pend = context.user_data.pop('ca_pending_content', None)
            if pend and len(pend) == 2:
                await _exec_content_action(query, context, uid, pend[0], pend[1])
        elif step == 'be':
            book = await db.ref_get_book(item_id)
            if not book: return
            context.user_data.update({'ca_mode':'edit_ref_book','ca_edit_target':item_id})
            hdr = ("🌐 <b>ویرایش سراسری</b> — برای همه‌ی ورودی‌ها.\n\n" if choice == 'g' else
                   f"⭐ <b>فقط ورودی {_lbl}</b> — در اولین ذخیره، نسخه‌ی اختصاصی ساخته می‌شود.\n\n")
            await query.edit_message_text(
                f"{hdr}✏️ <b>ویرایش نام کتاب</b>\n\nفعلی: <b>{book['name']}</b>\n\nجدید:\n⌨️ /cancel",
                parse_mode='HTML', reply_markup=_back_btn("❌ لغو", f'ca:ref_book:{item_id}'))
        elif step == 'bu':
            lang = context.user_data.get('ca_ref_lang', 'fa')
            vol  = context.user_data.get('ca_ref_volume', 1)
            kind_u = context.user_data.get('ca_ref_upload_kind', 'volume')
            # ⭐ م6: مسیر ذخیره‌ی فایل را تضمین می‌کنیم (دفاع در برابر state گم‌شده)
            context.user_data.update({'ca_ref_book_id': item_id,
                                      'ca_mode': 'waiting_ref_file'})
            ll = "🇮🇷 فارسی" if lang == 'fa' else "🌐 لاتین"
            title = (f"📤 <b>آپلود {ll} — جلد {vol}</b>" if kind_u == 'volume'
                     else f"🔄 <b>جایگزین {ll} جلد {vol}</b>")
            hdr = ("🌐 <b>سراسری</b> — برای همه‌ی ورودی‌ها.\n\n" if choice == 'g' else
                   f"⭐ <b>فقط ورودی {_lbl}</b> — در لحظه‌ی ثبت، نسخه‌ی اختصاصی ساخته می‌شود.\n\n")
            await query.edit_message_text(
                f"{hdr}{title}\n\nفایل PDF را ارسال کنید:\n⌨️ /cancel",
                parse_mode='HTML', reply_markup=_back_btn("❌ لغو", f'ca:ref_book:{item_id}'))
        elif step == 'bf':
            pend = context.user_data.pop('ca_pending_ref_upload', None)
            if pend and len(pend) == 2:
                await _exec_ref_file_action(query, context, uid, pend[0], pend[1])
        return ConversationHandler.END

    elif action == 'edit_session_prompt':
        sid = parts[2]; field = parts[3]; session = await db.bs_get_session(sid)
        if not session: return
        labels = {'topic':'موضوع','teacher':'نام استاد','number':'شماره جلسه'}
        context.user_data.update({'ca_mode':'edit_session','ca_edit_target':sid,'ca_edit_field':field})
        await query.edit_message_text(
            f"✏️ <b>ویرایش {labels.get(field,'')}</b>\n\nفعلی: <b>{session.get(field,'')}</b>\n\nجدید بنویسید:\n⌨️ /cancel",
            parse_mode='HTML', reply_markup=_back_btn("❌ لغو", f'ca:session:{sid}'))

    elif action == 'del_session':
        sid = parts[2]; session = await db.bs_get_session(sid)
        if not session: return
        lid = context.user_data.get('ca_lesson_id','')
        _hint = _global_delete_hint(await db.session_intake(sid), context)
        await query.edit_message_text(
            f"⚠️ <b>حذف جلسه {session.get('number','')} — {session.get('topic','')}؟</b>{_hint}",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🗑 بله", callback_data=f'ca:confirm_del_session:{sid}')],
                [InlineKeyboardButton("❌ لغو", callback_data=f'ca:lesson:{lid}')],
            ]))

    elif action == 'confirm_del_session':
        sid = parts[2]
        # 🍴 Q1 — حذف baseای که fork دارد ⇒ orphan شدن نسخه‌های اختصاصی؛
        # مسدود می‌شود تا ابتدا نسخه‌ها ↩️ بازگردانده شوند (Scenario K)
        if await db.bs_session_has_forks(sid):
            await query.answer(
                "⚠️ این جلسه نسخه‌ی اختصاصی (fork) دارد؛\n"
                "ابتدا نسخه‌های اختصاصی را ↩️ حذف کنید.",
                show_alert=True)
            return ConversationHandler.END
        session = await db.bs_get_session(sid)
        session_label = f"{session.get('number','')} — {session.get('topic','')}" if session else sid
        await db.bs_delete_session(sid)
        lid = context.user_data.get('ca_lesson_id','')
        await _audit(context, uid, "حذف جلسه",
            severity='HIGH',
            target_id=sid,
            target_type='session',
            target_label=session_label,
            tags=['حذف_جلسه'])
        await query.edit_message_text("✅ جلسه حذف شد.",
            reply_markup=_back_btn("🔙 بازگشت", f'ca:lesson:{lid}'))

    # ─ محتوای جلسه ─
    elif action == 'session':
        sid = parts[2]; context.user_data['ca_session_id'] = sid
        await _show_session_content(query, context, sid)

    # ── 🍴 موج C2 — سفارشی‌سازی جلسه‌ی سراسری برای یک ورودی ──
    elif action == 'fork_session':
        # ⭐ م6: مسیر legacy — دکمه‌ای به اینجا اشاره نمی‌کند؛ callbackهای
        # قدیمی همچنان کار می‌کنند (به ensure_override اتمیک هدایت شده‌اند)
        return await _h_fork_session(query, context, uid, _cscope, is_scoped, parts)
    elif action == 'unfork_session':
        return await _h_unfork_session(query, context, uid, _cscope, is_scoped, parts)
    elif action == 'confirm_unfork_session':
        return await _do_unfork_session(query, context, uid, parts[2])
    elif action == 'upload_content':
        sid = parts[2]; context.user_data['ca_session_id'] = sid
        context.user_data.pop('ca_edit_scope', None)   # ⭐ م6: انتخاب تازه
        if not await db.session_intake(sid):
            _kind, _tgt = await _cow_scope(context, uid)
            if _kind == 'global' and _tgt:
                # ⭐ م6 (R4): ارشد در محدوده‌ی ورودی → انتخاب روشن قبل از آپلود
                if await _scope_choice_screen(query, context, sid, 'session', 'u'):
                    return ConversationHandler.END
        kb = [[InlineKeyboardButton(label, callback_data=f'ca:sel_ctype:{sid}:{ct}')]
              for ct, label in CONTENT_TYPES]
        kb.append([InlineKeyboardButton("❌ لغو", callback_data=f'ca:session:{sid}')])
        await query.edit_message_text("📤 <b>نوع محتوا:</b>",
            parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))

    elif action == 'sel_ctype':
        sid = parts[2]; ctype = parts[3]
        context.user_data.update({'ca_session_id':sid,'ca_content_type':ctype,'ca_mode':'waiting_file'})
        tl = dict(CONTENT_TYPES).get(ctype, ctype)
        await query.edit_message_text(
            f"📤 <b>آپلود {tl}</b>\n\nفایل را ارسال کنید:\n⌨️ /cancel",
            parse_mode='HTML', reply_markup=_back_btn("❌ لغو", f'ca:session:{sid}'))
        return CA_WAITING_FILE

    # ─ ترتیب فایل‌های جلسه ─
    elif action == 'content_up':
        # ⭐ م6 — CoW: تغییر ترتیب هم «ذخیره» است؛ هدف از سرور تعیین می‌شود
        await _exec_content_action(query, context, uid, 'content_up', parts[2])
        return ConversationHandler.END

    elif action == 'content_down':
        await _exec_content_action(query, context, uid, 'content_down', parts[2])
        return ConversationHandler.END

    elif action == 'merge_new':
        # ⭐ م6 (R5) — افزودن فایل‌های جدیدِ سراسری به fork (فقط افزودنی)
        fork_sid = parts[2]
        added = await db.bs_merge_base_new_content(fork_sid)
        await query.answer(f"📥 {added} فایل جدید از نسخه‌ی سراسری افزوده شد"
                           if added else "ℹ️ فایل جدیدی در نسخه‌ی سراسری نیست")
        await _show_session_content(query, context, fork_sid)
        return ConversationHandler.END

    # ─ حذف محتوا ─
    elif action == 'del_content':
        cid = parts[2]; item = await db.bs_get_content_item(cid)
        if not item: return
        sid = context.user_data.get('ca_session_id','')
        tl  = dict(CONTENT_TYPES).get(item.get('type',''),'فایل')
        await query.edit_message_text(
            f"⚠️ <b>حذف {tl}؟</b>\n{item.get('description','')[:40]}",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🗑 حذف", callback_data=f'ca:confirm_del_content:{cid}')],
                [InlineKeyboardButton("❌ لغو", callback_data=f'ca:session:{sid}')],
            ]))

    elif action == 'confirm_del_content':
        # ⭐ م6 — حذف هم «ذخیره» است: هدف از سرور (CoW در صورت نیاز)
        await _exec_content_action(query, context, uid, 'confirm_del_content', parts[2])
        return ConversationHandler.END

    # ══════════ رفرنس‌ها ══════════

    elif action in ('refs','refs_admin'):
        context.user_data['ca_ref_from_admin'] = from_admin
        await _show_ref_subjects(query, back=back_main, context=context)

    # ─ ترتیب درس‌های رفرنس ─
    elif action == 'ref_subject_up':
        sid = parts[2]
        subj = await db.ref_get_subject(sid) or {}
        await db.reorder_up('ref_subjects', sid,
            {'intake': subj.get('intake') or ''})
        fa = context.user_data.get('ca_ref_from_admin', False)
        back = 'ca:refs_admin' if fa else 'ca:refs'
        await _show_ref_subjects(query, back=back, context=context)

    elif action == 'ref_subject_down':
        sid = parts[2]
        subj = await db.ref_get_subject(sid) or {}
        await db.reorder_down('ref_subjects', sid,
            {'intake': subj.get('intake') or ''})
        fa = context.user_data.get('ca_ref_from_admin', False)
        back = 'ca:refs_admin' if fa else 'ca:refs'
        await _show_ref_subjects(query, back=back, context=context)

    elif action == 'add_ref_subject_prompt':
        # 🛡 C3.1 — بدون ورودیِ تنظیم‌شده، ساختن در سطل سراسری مجاز نیست
        if not await db.can_access_intake(uid, context.user_data.get('ca_intake') or ''):
            await query.answer(
                "⛔ برای نقش شما هنوز ورودی‌ای تنظیم نشده — از ادمین ارشد بخواهید.\n"
                "پیش از آن فقط مشاهده‌ی سراسری دارید.", show_alert=True)
            return
        context.user_data['ca_mode'] = 'add_ref_subject'
        fa = context.user_data.get('ca_ref_from_admin', False)
        back = 'ca:refs_admin' if fa else 'ca:refs'
        await query.edit_message_text(
            "➕ <b>درس جدید</b>\n\nنام درس را بنویسید:\n⌨️ /cancel",
            parse_mode='HTML', reply_markup=_back_btn("❌ لغو", back))

    elif action == 'edit_ref_subject_prompt':
        sid = parts[2]; subj = await db.ref_get_subject(sid)
        if not subj: return
        context.user_data.update({'ca_mode':'edit_ref_subject','ca_edit_target':sid})
        await query.edit_message_text(
            f"✏️ <b>ویرایش نام درس</b>\n\nفعلی: <b>{subj['name']}</b>\n\nجدید:\n⌨️ /cancel",
            parse_mode='HTML', reply_markup=_back_btn("❌ لغو", f'ca:ref_subject:{sid}'))

    elif action == 'del_ref_subject':
        sid = parts[2]; subj = await db.ref_get_subject(sid)
        if not subj: return
        fa = context.user_data.get('ca_ref_from_admin', False)
        back = 'ca:refs_admin' if fa else 'ca:refs'
        await query.edit_message_text(
            f"⚠️ <b>حذف درس «{subj['name']}»؟</b>\nتمام کتاب‌ها و فایل‌ها حذف می‌شوند!",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🗑 بله", callback_data=f'ca:confirm_del_ref_subject:{sid}')],
                [InlineKeyboardButton("❌ لغو", callback_data=back)],
            ]))

    elif action == 'confirm_del_ref_subject':
        sid = parts[2]
        _subj_for_audit = await db.ref_get_subject(sid) or {}
        _subj_name = _subj_for_audit.get('name','')
        await db.ref_delete_subject(sid)
        try:
            await _audit(context, uid, "حذف موضوع رفرنس",
                severity='HIGH',
                target_id=sid,
                target_type='ref_subject',
                target_label=_subj_name,
                tags=['حذف_رفرنس'])
        except Exception as _e:
            logger.warning(f"del_ref_subject audit failed: {_e}")
        fa = context.user_data.get('ca_ref_from_admin', False)
        back = 'ca:refs_admin' if fa else 'ca:refs'
        await query.edit_message_text("✅ درس حذف شد.", reply_markup=_back_btn("🔙 بازگشت", back))

    elif action == 'ref_subject':
        sid = parts[2]; context.user_data['ca_ref_subject_id'] = sid
        fa  = context.user_data.get('ca_ref_from_admin', False)
        back = 'ca:refs_admin' if fa else 'ca:refs'
        await _show_ref_books(query, context, sid, back=back)

    # ─ ترتیب کتاب‌های رفرنس ─
    elif action == 'ref_book_up':
        bid = parts[2]; sid = context.user_data.get('ca_ref_subject_id','')
        # 🌊 C3 — فقط با هم‌سطل‌ها swap می‌شود (پیش از این، ترتیب پایه‌ی
        # سراسری هم از جای خود کنده می‌شد — همان مسیر در API اصلاح شده بود)
        _bkf = db.ref_books_order_filter(await db.ref_get_book(bid) or {'subject_id': sid})
        await db.reorder_up('ref_books', bid, _bkf)
        fa = context.user_data.get('ca_ref_from_admin', False)
        back = 'ca:refs_admin' if fa else 'ca:refs'
        await _show_ref_books(query, context, sid, back=back)

    elif action == 'ref_book_down':
        bid = parts[2]; sid = context.user_data.get('ca_ref_subject_id','')
        _bkf = db.ref_books_order_filter(await db.ref_get_book(bid) or {'subject_id': sid})
        await db.reorder_down('ref_books', bid, _bkf)
        fa = context.user_data.get('ca_ref_from_admin', False)
        back = 'ca:refs_admin' if fa else 'ca:refs'
        await _show_ref_books(query, context, sid, back=back)

    elif action == 'add_ref_book_prompt':
        sid = parts[2]
        context.user_data.update({'ca_ref_subject_id': sid, 'ca_mode': 'add_ref_book'})
        # 🌊 C3 — اگر موضوع سراسری است، فرزند در سطل scope خودِ actor نوشته می‌شود
        _subj  = await db.ref_get_subject(sid)
        _child = await db.scoped_child_intake(uid, (_subj or {}).get('intake') or '')
        scope_line = ""
        if _child:
            scope_line = (f"📅 <b>فقط برای ورودی «{await _intake_label(_child)}»</b> — "
                          f"کتاب‌های سراسری این موضوع تغییر نمی‌کنند.\n\n")
        await query.edit_message_text(
            f"➕ <b>کتاب جدید</b>\n\n{scope_line}"
            "نام کتاب را بنویسید:\n⌨️ /cancel",
            parse_mode='HTML', reply_markup=_back_btn("❌ لغو", f'ca:ref_subject:{sid}'))

    elif action == 'edit_ref_book_prompt':
        bid = parts[2]; book = await db.ref_get_book(bid)
        if not book: return
        context.user_data.pop('ca_edit_scope', None)   # ⭐ م6
        hdr = ''
        if not await db.ref_book_intake(bid):
            _kind, _tgt = await _cow_scope(context, uid)
            if _kind == 'scoped' and _tgt:
                hdr = (f"🌐 سراسری — تغییر در <b>نسخه‌ی اختصاصی ورودی "
                       f"{await _intake_label(_tgt)}</b> ذخیره می‌شود (⭐).\n\n")
            elif _kind == 'global' and _tgt:
                if await _scope_choice_screen(query, context, bid, 'ref_book', 'be'):
                    return ConversationHandler.END
            else:
                hdr = "🌐 سراسری — تغییر برای <b>همه‌ی ورودی‌ها</b> اعمال می‌شود.\n\n"
        context.user_data.update({'ca_mode':'edit_ref_book','ca_edit_target':bid})
        await query.edit_message_text(
            f"{hdr}✏️ <b>ویرایش نام کتاب</b>\n\nفعلی: <b>{book['name']}</b>\n\nجدید:\n⌨️ /cancel",
            parse_mode='HTML', reply_markup=_back_btn("❌ لغو", f'ca:ref_book:{bid}'))

    elif action == 'del_ref_book':
        bid = parts[2]; book = await db.ref_get_book(bid)
        if not book: return
        sid = context.user_data.get('ca_ref_subject_id','')
        _hint = _global_delete_hint(await db.ref_book_intake(bid), context)
        await query.edit_message_text(
            f"⚠️ <b>حذف رفرنس «{book['name']}»؟</b>{_hint}",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🗑 حذف", callback_data=f'ca:confirm_del_ref_book:{bid}')],
                [InlineKeyboardButton("❌ لغو", callback_data=f'ca:ref_subject:{sid}')],
            ]))

    elif action == 'confirm_del_ref_book':
        bid = parts[2]
        # 🍴 Q1 — حذف کتابی که fork دارد ⇒ orphan؛ ابتدا forkها ↩️ شوند
        if await db.ref_book_has_forks(bid):
            await query.answer(
                "⚠️ این کتاب نسخه‌ی اختصاصی (fork) دارد؛\n"
                "ابتدا نسخه‌های اختصاصی را ↩️ حذف کنید.",
                show_alert=True)
            return ConversationHandler.END
        _book_for_audit = await db.ref_get_book(bid) or {}
        _book_name = _book_for_audit.get('name','')
        await db.ref_delete_book(bid)
        try:
            await _audit(context, uid, "حذف کتاب رفرنس",
                severity='HIGH',
                target_id=bid,
                target_type='reference_book',
                target_label=_book_name,
                tags=['حذف_رفرنس'])
        except Exception as _e:
            logger.warning(f"del_ref_book audit failed: {_e}")
        sid = context.user_data.get('ca_ref_subject_id','')
        await query.edit_message_text("✅ رفرنس حذف شد.",
            reply_markup=_back_btn("🔙 بازگشت", f'ca:ref_subject:{sid}'))

    elif action == 'ref_book':
        bid = parts[2]; context.user_data['ca_ref_book_id'] = bid
        await _show_ref_book_files(query, context, bid)

    # ── 🍴 موج C2 — سفارشی‌سازی کتاب سراسری برای یک ورودی ──
    elif action == 'fork_book':
        # ⭐ م6: مسیر legacy (مثل fork_session)
        return await _h_fork_book(query, context, uid, _cscope, is_scoped, parts)
    elif action == 'unfork_book':
        return await _h_unfork_book(query, context, uid, _cscope, is_scoped, parts)
    elif action == 'confirm_unfork_book':
        return await _do_unfork_book(query, context, uid, parts[2])
    elif action == 'upload_ref_volume_prompt':
        bid  = parts[2]; lang = parts[3]
        context.user_data.pop('ca_edit_scope', None)   # ⭐ م6
        files = await db.ref_get_files(bid)
        existing_vols = [f.get('volume', 1) for f in files if f.get('lang') == lang]
        next_vol = max(existing_vols, default=0) + 1
        # ⭐ م6: state باید *قبل* از صفحه‌ی انتخاب scope ساخته شود تا پس از
        # انتخاب، مسیر ذخیره‌ی فایل (message_router: waiting_ref_file) سالم باشد
        context.user_data.update({
            'ca_ref_book_id': bid,
            'ca_ref_lang':    lang,
            'ca_ref_volume':  next_vol,
            'ca_mode':        'waiting_ref_file',
            'ca_ref_upload_kind': 'volume',
        })
        if not await db.ref_book_intake(bid):
            _kind, _tgt = await _cow_scope(context, uid)
            if _kind == 'global' and _tgt:
                if await _scope_choice_screen(query, context, bid, 'ref_book', 'bu'):
                    return ConversationHandler.END
        ll = "🇮🇷 فارسی" if lang == 'fa' else "🌐 لاتین"
        await query.edit_message_text(
            f"📤 <b>آپلود {ll} — جلد {next_vol}</b>\n\n"
            f"فایل PDF را ارسال کنید:\n⌨️ /cancel",
            parse_mode='HTML', reply_markup=_back_btn("❌ لغو", f'ca:ref_book:{bid}'))
        # چون ممکنه خارج از ConversationHandler باشیم، state رو نمی‌تونیم return بدیم
        # message_router.py با چک ca_mode='waiting_ref_file' این رو handle می‌کنه

    elif action == 'upload_ref':
        # جایگزین کردن یک جلد موجود
        bid = parts[2]; lang = parts[3]; vol = int(parts[4])
        ll  = "🇮🇷 فارسی" if lang == 'fa' else "🌐 لاتین"
        context.user_data.pop('ca_edit_scope', None)   # ⭐ م6
        if not await db.ref_book_intake(bid):
            _kind, _tgt = await _cow_scope(context, uid)
            if _kind == 'global' and _tgt:
                context.user_data.update({
                    'ca_ref_book_id': bid, 'ca_ref_lang': lang,
                    'ca_ref_volume': vol, 'ca_ref_upload_kind': 'replace',
                    'ca_mode': 'waiting_ref_file',   # ⭐ م6: قبل از صفحه‌ی انتخاب scope
                })
                if await _scope_choice_screen(query, context, bid, 'ref_book', 'bu'):
                    return ConversationHandler.END
        context.user_data.update({
            'ca_ref_book_id': bid,
            'ca_ref_lang':    lang,
            'ca_ref_volume':  vol,
            'ca_mode':        'waiting_ref_file',
            'ca_ref_upload_kind': 'replace',   # ⭐ م6
        })
        await query.edit_message_text(
            f"🔄 <b>جایگزین {ll} جلد {vol}</b>\n\nفایل جدید ارسال کنید:\n⌨️ /cancel",
            parse_mode='HTML', reply_markup=_back_btn("❌ لغو", f'ca:ref_book:{bid}'))

    elif action == 'del_ref_file':
        # ⭐ م6 — حذف فایل هم «ذخیره» است: CoW از سرور
        await _exec_ref_file_action(query, context, uid, 'del_ref_file', parts[2])
        return ConversationHandler.END

    # ══════════ FAQ ══════════

    elif action == 'overview':
        await _show_overview(query, uid, context)

    elif action == 'create_q':
        # redirect به بانک سوال برای طراحی سوال
        kb = [[InlineKeyboardButton("✏️ شروع طراحی سوال", callback_data='questions:create_ca')],
              [InlineKeyboardButton("🔙 بازگشت", callback_data='ca:main')]]
        await query.edit_message_text(
            "✏️ <b>طراحی سوال (ادمین محتوا)</b>\n\n"
            "سوالات شما با برچسب <b>«طراحی شده توسط بات»</b> مشخص می‌شوند\n"
            "و بدون نیاز به تأیید، مستقیم در بانک سوال قرار می‌گیرند.",
            parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))

    elif action in ('faq', 'faq_admin'):
        context.user_data['ca_from_admin'] = from_admin
        await _show_faq(query, back=back_main)

    elif action == 'add_faq_prompt':
        context.user_data['ca_mode'] = 'add_faq'
        await query.edit_message_text(
            "➕ <b>سوال متداول جدید</b>\n\n"
            "فرمت: <code>سوال | جواب | دسته</code>\n⌨️ /cancel",
            parse_mode='HTML', reply_markup=_back_btn("❌ لغو", 'ca:faq'))

    elif action == 'edit_faq_menu':
        fid = parts[2] if len(parts) > 2 else ''
        faq = await db.faq_get(fid)
        if not faq:
            await query.answer("❌ سوال پیدا نشد", show_alert=True); return
        kb = [
            [InlineKeyboardButton("✏️ ویرایش سؤال", callback_data=f'ca:edit_faq_prompt:{fid}:question')],
            [InlineKeyboardButton("✏️ ویرایش پاسخ", callback_data=f'ca:edit_faq_prompt:{fid}:answer')],
            [InlineKeyboardButton("✏️ ویرایش دسته", callback_data=f'ca:edit_faq_prompt:{fid}:category')],
            [InlineKeyboardButton("🔙 بازگشت", callback_data='ca:faq')],
        ]
        await query.edit_message_text(
            f"✏️ <b>ویرایش FAQ</b>\n\n❓ <b>{faq.get('question','')[:120]}</b>\n\n"
            f"📝 {faq.get('answer','')[:300]}...\n\n🗂 دسته: {faq.get('category','عمومی')}",
            parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))

    elif action == 'edit_faq_prompt':
        fid = parts[2] if len(parts) > 2 else ''
        field = parts[3] if len(parts) > 3 else 'question'
        faq = await db.faq_get(fid)
        if not faq:
            await query.answer("❌ سوال پیدا نشد", show_alert=True); return
        labels = {'question':'سؤال','answer':'پاسخ','category':'دسته'}
        context.user_data.update({'ca_mode':'edit_faq','ca_edit_target':fid,'ca_edit_field':field})
        await query.edit_message_text(
            f"✏️ <b>ویرایش {labels.get(field,'سؤال')}</b>\n\nفعلی: <b>{faq.get(field,'')[:500]}</b>\n\nجدید بنویسید:\n⌨️ /cancel",
            parse_mode='HTML', reply_markup=_back_btn("❌ لغو", f'ca:edit_faq_menu:{fid}'))

    elif action == 'del_faq':
        _faq_del_id = parts[2]
        _faq_before = await db.faq_get(_faq_del_id) if hasattr(db, 'faq_get') else None
        await db.faq_delete(_faq_del_id)
        try:
            await _audit(context, uid, "حذف سوال متداول",
                severity='HIGH',
                target_id=_faq_del_id,
                target_type='faq',
                target_label=(_faq_before.get('question','')[:60] if _faq_before else _faq_del_id),
                tags=['حذف_FAQ'])
        except Exception as _e:
            logger.warning(f"del_faq audit failed: {_e}")
        await _show_faq(query)

    elif action == 'urlimport':
        # 📥 URL-Import — §46: ورودی متن → job → پیشرفت با edit
        context.user_data['ca_mode'] = 'ui_url'
        await query.edit_message_text(
            "📥 <b>درون‌ریزی محتوا از URL</b>\n\n"
            "لینک مستقیم فایل (http/https) رو بفرست.\n"
            "فایل روی سرور دانلود و مستقیم به تلگرام منتقل می‌شه —\n"
            "نیازی به دانلود/آپلود از دستگاه تو نیست.\n\n"
            "لغو: /cancel",
            parse_mode='HTML')

    # FIX باگ بسیار مهم — منشأ «ربات متن دریافت نمی‌کند»:
    # این تابع به‌عنوان entry_point با pattern='^ca:' ثبت شده است،
    # یعنی با هر کلیک در پنل محتوا، ConversationHandler کاربر را
    # وارد یک state می‌کند. قبلاً این تابع هیچ‌وقت
    # ConversationHandler.END برنمی‌گرداند، پس کاربر برای ۳۰ دقیقه
    # (conversation_timeout) در آن state می‌ماند — حتی برای اکشن‌های
    # ساده‌ی نمایشی که نیازی به ورودی متنی ندارند. در نتیجه پیام‌های
    # بعدی کاربر در بخش‌های کاملاً نامرتبط (مثل broadcast در پنل
    # ادمین) توسط ca_text_handler به‌اشتباه قورت می‌شدند.
    # حالا اگر action واقعاً منتظر یک ورودی متنی/فایلی نباشد
    # (یعنی در KEEP_MODE نیست)، رسماً از conversation خارج می‌شویم.
    if action not in KEEP_MODE:
        return ConversationHandler.END


# ══════════════════════════════════════════════════════════
#  توابع نمایش
# ══════════════════════════════════════════════════════════

async def _show_intake_picker(query_or_message, uid: int = None, edit: bool = True):
    """🌊 موج C1 — اولین صفحه‌ی ادمین ارشد محتوا (§۵ spec):
    «محتوای کدام ورودی را می‌خواهید مدیریت کنید؟»
    ورودی‌های فعال + سطل 🌐 سراسری (محتوای legacy/مشترک)."""
    intakes = await db.get_all_intakes()
    active  = [i for i in intakes if i.get('active', True)]
    kb = []
    for i in active:
        kb.append([InlineKeyboardButton(
            f"📅 {i['label']}", callback_data=f"ca:intake:{i['code']}")])
    kb.append([InlineKeyboardButton(
        GLOBAL_INTAKE_LABEL, callback_data=f"ca:intake:{GLOBAL_PICK}")])
    if edit:
        kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data='dashboard:refresh')])
    text = (
        "🎓 <b>پنل ادمین محتوا</b>\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "محتوای کدام ورودی را می‌خواهید مدیریت کنید؟\n\n"
        "<i>🌐 سراسری = محتوای مشترک و داده‌های قدیمی</i>"
    )
    if edit:
        await query_or_message.edit_message_text(
            text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))
    else:
        await query_or_message.reply_text(
            text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))


def _main_keyboard(is_scoped: bool):
    kb = [
        [InlineKeyboardButton("📊 آمار محتوا",          callback_data='ca:overview')],
        [
            InlineKeyboardButton("🔬 علوم پایه",         callback_data='ca:terms'),
            InlineKeyboardButton("📚 رفرنس‌ها",           callback_data='ca:refs'),
        ],
        [InlineKeyboardButton("✏️ طراحی سوال",           callback_data='ca:create_q')],
        [InlineKeyboardButton("🧪 مدیریت سوالات",        callback_data='questions:ca_q_list')],
        [InlineKeyboardButton("❓ سوالات متداول",          callback_data='ca:faq')],
        # 📥 URL-Import — همان پایپ‌لاین canonical سرویس
        [InlineKeyboardButton("📥 درون‌ریزی از URL",       callback_data='ca:urlimport')],
    ]
    if not is_scoped:
        kb.append([InlineKeyboardButton("🔄 تغییر ورودی", callback_data='ca:change_intake')])
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data='dashboard:refresh')])
    return kb


async def _show_main(query, uid: int = None, context=None):
    """🌊 C1 — منوی اصلی: خط وضعیت ورودی + دکمه‌ی تغییر ورودی برای
    ادمین ارشد؛ برای ادمین ورودی خاص فقط بنر قفل (بدون picker)."""
    cscope = await db.get_content_scope(uid) if uid else None
    is_scoped = bool(cscope and cscope['kind'] == 'scoped')
    if is_scoped:
        label = await _intake_label(cscope.get('intake') or '')
        header = (
            "🎓 <b>پنل محتوای ورودی</b>\n"
            "━━━━━━━━━━━━━━━━\n\n"
            f"📅 <b>ورودی تحت مدیریت:</b>\n<b>{label}</b>"
        )
    else:
        intake = (context.user_data.get('ca_intake')
                  if context is not None else None) or ''
        label = await _intake_label(intake)
        header = (
            "🎓 <b>پنل ادمین محتوا</b>\n"
            "━━━━━━━━━━━━━━━━\n\n"
            f"📅 <b>ورودی فعلی:</b> {label}"
        )
    await query.edit_message_text(
        header, parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(_main_keyboard(is_scoped))
    )


async def show_ca_main(message, uid: int, context=None):
    """فراخوانی از message_router — دکمه 🎓 پنل محتوا
    🌊 C1: scoped → قفل خودکار روی scope؛ global → picker در اولین ورود."""
    cscope = await db.get_content_scope(uid)
    is_scoped = bool(cscope and cscope['kind'] == 'scoped')
    if is_scoped:
        if context is not None:
            context.user_data['ca_intake'] = cscope.get('intake') or ''
        label = await _intake_label(cscope.get('intake') or '')
        header = (
            "🎓 <b>پنل محتوای ورودی</b>\n"
            "━━━━━━━━━━━━━━━━\n\n"
            f"📅 <b>ورودی تحت مدیریت:</b>\n<b>{label}</b>"
        )
    else:
        intake = (context.user_data.get('ca_intake')
                  if context is not None else None)
        if intake is None:
            await _show_intake_picker(message, uid, edit=False)
            return
        label = await _intake_label(intake or '')
        header = (
            "🎓 <b>پنل ادمین محتوا</b>\n"
            "━━━━━━━━━━━━━━━━\n\n"
            f"📅 <b>ورودی فعلی:</b> {label}"
        )
    kb = _main_keyboard(is_scoped)
    # نسخه‌ی پیام‌محور: دکمه‌ی بازگشت تحت‌الشعاع dashboard کار نمی‌کند، حذفش می‌کنیم
    kb = [row for row in kb
          if not any(b.callback_data == 'dashboard:refresh' for b in row)]
    await message.reply_text(
        header, parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(kb)
    )


async def _show_overview(query, uid: int = None, context=None):
    """نمای کلی آمار — 🌊 C1: محدود به intake جاریِ context (§۱۷ spec)."""
    intake = None
    if uid is not None:
        cscope = await db.get_content_scope(uid)
        if cscope and cscope['kind'] == 'scoped':
            intake = cscope.get('intake') or ''
        elif context is not None:
            intake = context.user_data.get('ca_intake', '')
    if intake is None:
        intake = ''
    s = await db.content_admin_stats(intake=intake)
    intake_label = await _intake_label(intake)

    # 🍴 موج C2 — «آمار مؤثر» = آنچه دانشجوی این ورودی واقعاً می‌بیند
    # (اختصاصی ورودی + سراسری) — راهنمای تصمیم fork/move برای مدیر محتوا.
    # فقط وقتی ctx یک ورودی مشخص است (روی سطل سراسری نمایش داده نمی‌شود).
    eff_line = ''
    if intake:
        e = await db.content_admin_stats(intake=intake, effective=True)
        eff_line = (
            "\n\n━━━━━━━━━━━━━━━━\n"
            "🔭 <b>مؤثر (آنچه دانشجوی این ورودی می‌بیند)</b>\n"
            f"📁 علوم پایه: <b>{e['bs_total']}</b> فایل    "
            f"📚 رفرنس: <b>{e['ref_files']}</b> فایل\n"
            f"✅ سؤال تأییدشده: <b>{e['q_total']}</b>    "
            f"⏳ در انتظار: <b>{e['q_pending']}</b>"
        )

    # ── نوار پیشرفت ──
    def bar(val, mx, width=8):
        if mx == 0: return '░' * width
        filled = min(width, round(val / mx * width))
        return '█' * filled + '░' * (width - filled)

    bs_bar  = bar(s['bs_total'],   max(s['bs_total'], 1))
    ref_bar = bar(s['ref_files'],  max(s['ref_files'], 1))
    q_bar   = bar(s['q_total'],    max(s['q_total'], 1))

    # ── نسبت پاسخ صحیح سوالات ──
    q_ratio = f"{round(s['q_by_bot'] / s['q_total'] * 100)}٪ بات" if s['q_total'] else '—'

    from utils import now_tehran_str
    now = now_tehran_str()

    text = (
        "📊 <b>داشبورد پنل محتوا</b>\n"
        "━━━━━━━━━━━━━━━━\n"
        f"<i>🕐 {now}</i>\n"
        f"<i>📅 ورودی: {intake_label}</i>\n\n"

        "📘 <b>علوم پایه</b>\n"
        f"📖 <b>{s['bs_lessons']}</b> درس   "
        f"📌 <b>{s['bs_sessions']}</b> جلسه   "
        f"📁 <b>{s['bs_total']}</b> فایل\n"
        f"<code>[{bs_bar}]</code>\n\n"
        f"  🎥 ویدیو: <b>{s['bs_video']}</b>      "
        f"📄 جزوه: <b>{s['bs_pdf']}</b>\n"
        f"  📊 پاورپوینت: <b>{s['bs_ppt']}</b>   "
        f"🎙 ویس: <b>{s['bs_voice']}</b>\n"
        f"  📝 نکات: <b>{s['bs_note']}</b>        "
        f"🧪 تست: <b>{s['bs_test']}</b>\n\n"

        "📚 <b>رفرنس‌ها</b>\n"
        f"📖 <b>{s['ref_subjects']}</b> درس   "
        f"📘 <b>{s['ref_books']}</b> کتاب   "
        f"📁 <b>{s['ref_files']}</b> فایل\n"
        f"<code>[{ref_bar}]</code>\n"
        f"  🇮🇷 فارسی: <b>{s['ref_fa']}</b>   "
        f"🌐 لاتین: <b>{s['ref_en']}</b>\n\n"

        "🧪 <b>بانک سوال</b>\n"
        f"✅ تأیید شده: <b>{s['q_total']}</b>   "
        f"⏳ انتظار: <b>{s['q_pending']}</b>\n"
        f"<code>[{q_bar}]</code>\n"
        f"  🤖 توسط بات: <b>{s['q_by_bot']}</b>   "
        f"👤 کاربران: <b>{s['q_by_users']}</b>\n"
        f"  📊 نسبت تولید توسط بات: <b>{q_ratio}</b>\n\n"

        "━━━━━━━━━━━━━━━━\n"
        "📈 <b>کلی</b>\n"
        f"⬇️ کل دانلودها: <b>{s['total_downloads']}</b>\n"
        f"👥 دانشجویان فعال: <b>{s['users_count']}</b>\n"
    ) + eff_line

    kb = [
        [InlineKeyboardButton("🔄 بروزرسانی", callback_data='ca:overview')],
        [InlineKeyboardButton("🔙 بازگشت",    callback_data='ca:main')],
    ]
    await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))

async def _show_terms(query, back='ca:main', context=None):
    kb = []
    for i in range(0, len(TERMS), 2):
        row = [InlineKeyboardButton(f"📘 {TERMS[i]}", callback_data=f'ca:term:{i}')]
        if i+1 < len(TERMS):
            row.append(InlineKeyboardButton(f"📘 {TERMS[i+1]}", callback_data=f'ca:term:{i+1}'))
        kb.append(row)
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data=back)])
    # ⭐ م6: سربرگ محدوده
    hdr = (await _scope_header(context, query.from_user.id)) if context else ''
    await query.edit_message_text(f"{hdr}📘 <b>انتخاب ترم — علوم پایه</b>",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))



def _ca_bucket(item, parent_intake=''):
    """intake مؤثر: فیلد صریح، وگرنه ارث از والد. رشته‌ی خالی یعنی سراسری."""
    if not item:
        return parent_intake or ''
    if 'intake' in item:
        return item.get('intake') or ''
    return parent_intake or ''


def _global_delete_hint(resolved_intake, context) -> str:
    """حذف سراسری از داخل یک ورودی، برای همه اعمال می‌شود — قبلش یادآوری ✂️."""
    ctx = (getattr(context, 'user_data', None) or {}).get('ca_intake') or ''
    if not ctx or resolved_intake:
        return ''
    return ("\n\n🌐 این مورد سراسری است. حذف، آن را برای همه برمی‌دارد. "
            "اگر فقط همین ورودی را می‌خواهید، حذف نکنید و ✂️ بزنید.")


async def _show_lessons(query, context, term, back='ca:terms'):
    # 🌊 C1 — لیست درس‌ها فقط در scope انتخاب‌شده/قفل‌شده
    # 🌊 C1.5 — ادمین ورودی خاص: درس‌های سراسری هم «فقط‌خواندنی» دیده
    # می‌شوند (گروه‌بندی: اول ورودی من، بعد 🌐 سراسری با 🔒)
    uid     = query.from_user.id
    _cscope = await db.get_content_scope(uid)
    is_scoped = bool(_cscope and _cscope.get('kind') == 'scoped')
    ctx     = context.user_data.get('ca_intake', '')
    # داخل یک ورودی (ارشد یا محدود) سراسری هم دیده می‌شود؛ سطل سراسری فقط سراسری است.
    lessons = await db.bs_get_lessons(
        term, intake=[ctx, ''] if ctx else ctx)
    idx     = context.user_data.get('ca_term_idx', 0)
    kb = []

    if ctx:
        own_items  = [l for l in lessons if (l.get('intake') or '') == ctx]
        glob_items = [l for l in lessons if (l.get('intake') or '') != ctx]
    elif is_scoped:
        # 🛡 C3.1 — scoped بدون ورودیِ تنظیم‌شده: هیچ سطلی «مال من» نیست،
        # پس همه‌چیز در گروه فقط‌خواندنی می‌نشیند (نه زیر دکمه‌های ✏️/🗑).
        own_items, glob_items = [], lessons
    else:
        own_items, glob_items = lessons, []

    for i, l in enumerate(own_items):
        lid = str(l['_id'])
        t   = f" | {l['teacher']}" if l.get('teacher') else ''
        # ردیف اصلی
        kb.append([
            InlineKeyboardButton(f"📖 {l['name']}{t}", callback_data=f'ca:lesson:{lid}'),
            InlineKeyboardButton("✏️", callback_data=f'ca:edit_lesson_menu:{lid}'),
            InlineKeyboardButton("🗑",  callback_data=f'ca:del_lesson:{lid}'),
        ])
        # ردیف ترتیب
        nav = []
        if i > 0:
            nav.append(InlineKeyboardButton("⬆️", callback_data=f'ca:lesson_up:{lid}'))
        if i < len(own_items) - 1:
            nav.append(InlineKeyboardButton("⬇️", callback_data=f'ca:lesson_down:{lid}'))
        if nav:
            kb.append(nav)

    if glob_items and is_scoped:
        kb.append([InlineKeyboardButton(
            "── 🌐 منابع سراسری (🔒 فقط‌خواندنی) ──",
            callback_data='ca:ro_info')])
        for l in glob_items:
            lid = str(l['_id'])
            t   = f" | {l['teacher']}" if l.get('teacher') else ''
            kb.append([InlineKeyboardButton(
                f"🌐 {l['name']}{t}", callback_data=f'ca:lesson:{lid}')])
    elif glob_items:
        kb.append([InlineKeyboardButton(
            "── 🌐 سراسری (ویرایش یا ✂️ روی جلسه) ──",
            callback_data='ca:ro_info')])
        for i, l in enumerate(glob_items):
            lid = str(l['_id'])
            t   = f" | {l['teacher']}" if l.get('teacher') else ''
            kb.append([
                InlineKeyboardButton(f"🌐 {l['name']}{t}", callback_data=f'ca:lesson:{lid}'),
                InlineKeyboardButton("✏️", callback_data=f'ca:edit_lesson_menu:{lid}'),
                InlineKeyboardButton("🗑", callback_data=f'ca:del_lesson:{lid}'),
            ])
            nav = []
            if i > 0:
                nav.append(InlineKeyboardButton("⬆️", callback_data=f'ca:lesson_up:{lid}'))
            if i < len(glob_items) - 1:
                nav.append(InlineKeyboardButton("⬇️", callback_data=f'ca:lesson_down:{lid}'))
            if nav:
                kb.append(nav)

    if not (is_scoped and not ctx):
        kb.append([InlineKeyboardButton("➕ درس جدید", callback_data=f'ca:add_lesson_prompt:{idx}')])
    kb.append([InlineKeyboardButton("🔙 بازگشت",   callback_data=back)])
    if glob_items and is_scoped:
        ro_line = "\n🔒 🌐=سراسری — فقط‌خواندنی (مدیریت: 🎓 ادمین ارشد)"
    elif glob_items:
        ro_line = ("\n🌐 سراسری هم اینجاست — با اولین تغییر روی جلسه‌ی سراسری، "
                   "انتخاب می‌دهید: 🌐 همه یا ⭐ فقط همین ورودی.")
    else:
        ro_line = ''
    if is_scoped and not ctx:
        ro_line += ("\n⚠️ برای نقش شما هنوز ورودی‌ای تنظیم نشده؛ فعلاً فقط "
                    "مشاهده‌ی سراسری دارید. از ادمین ارشد بخواهید ورودی‌تان را تعیین کند.")
    await query.edit_message_text(
        f"{await _scope_header(context, query.from_user.id)}"
        f"📘 <b>{term}</b> — {len(lessons)} درس\n"
        f"<i>✏️=ویرایش  🗑=حذف  ⬆️⬇️=ترتیب</i>{ro_line}",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))


async def _show_sessions(query, context, lid):
    lesson   = await db.bs_get_lesson(lid)
    sessions = await db.bs_get_sessions(lid)
    idx      = context.user_data.get('ca_term_idx', 0)
    uid      = query.from_user.id
    # 🌊 C1.5 — درس سراسری برای ادمین ورودی خاص: فقط‌خواندنی
    _li      = (lesson or {}).get('intake') or ''
    writable = await db.can_access_intake(uid, _li)
    _cscope    = await db.get_content_scope(uid)
    is_scoped  = bool(_cscope and _cscope.get('kind') == 'scoped')
    ctx        = context.user_data.get('ca_intake', '')
    # 🌊 C3 — نماینده روی درس 🌐: «جلسه‌ی فقط‌ورودی‌خودم» ساختنی است (والد قفل)
    can_child  = (not writable and
                  await db.scoped_child_intake(uid, _li) not in (None, ''))
    # ⭐ م6 (R2) — سطل سراسریِ ارشد: forkها زیر base جمع می‌شوند؛ یک ردیف
    # برای هر جلسه‌ی منطقی + نشان «⭐n» (تعداد ورودی‌های دارای override).
    _ovr = await db.bs_override_counts(lid)
    if writable and not is_scoped and not ctx:
        _bases = {str(s['_id']) for s in sessions}
        sessions = [s for s in sessions
                    if not (s.get('fork_of') and str(s.get('fork_of')) in _bases)]
    elif ctx or (not writable and is_scoped):
        # داخل ورودی انتخاب‌شده: سراسری + همان ورودی (نمای مؤثر/سایه)
        sessions = await db.bs_get_sessions_effective(lid, [ctx, ''])
    kb = []
    for s in sessions:
        sid = str(s['_id'])
        is_fork  = bool(s.get('fork_of'))
        # 🌊 C3 — فرزند ورودی‌خاص (جلسه‌ای که فقط برای ورودی من ساخته شده)
        own_child = bool(is_scoped and ctx and not is_fork
                         and (s.get('intake') or '') == ctx)
        own_fork  = is_scoped and is_fork and (s.get('intake') or '') == ctx
        if writable:
            resolved = _ca_bucket(s, _li)
            # ⭐ م6 (R7): نشان در ابتدای دکمه؛ برچسب ورودی کنار نشان
            if is_fork:
                mk = f"⭐({await _intake_label(s.get('intake') or '')})"
            elif resolved:
                mk = f"📅({await _intake_label(resolved)})"
            else:
                mk = "🌐"
                if _ovr.get(sid):
                    mk = f"🌐 ⭐{_ovr[sid]}"
            row = [
                InlineKeyboardButton(
                    f"{mk} {s['number']} — {s.get('topic','')[:20]}",
                    callback_data=f'ca:session:{sid}'),
                InlineKeyboardButton("✏️", callback_data=f'ca:edit_session_menu:{sid}'),
                InlineKeyboardButton("🗑",  callback_data=f'ca:del_session:{sid}'),
            ]
            # ⭐ م6 (R1): ✂️ حذف شد — شخصی‌سازی در لحظه‌ی ذخیره (CoW) انجام می‌شود.
            if is_fork and ctx and (s.get('intake') or '') == ctx:
                row.append(InlineKeyboardButton("↩️", callback_data=f'ca:unfork_session:{sid}'))
            kb.append(row)
        elif own_fork:
            kb.append([
                InlineKeyboardButton(
                    f"⭐ {s['number']} — {s.get('topic','')[:20]} (نسخه‌ی من)",
                    callback_data=f'ca:session:{sid}'),
                InlineKeyboardButton("↩️", callback_data=f'ca:unfork_session:{sid}'),
            ])
        elif own_child:
            kb.append([
                InlineKeyboardButton(
                    f"📅 {s['number']} — {s.get('topic','')[:20]} (ورودی من)",
                    callback_data=f'ca:session:{sid}'),
                InlineKeyboardButton("✏️", callback_data=f'ca:edit_session_menu:{sid}'),
                InlineKeyboardButton("🗑",  callback_data=f'ca:del_session:{sid}'),
            ])
        else:
            # ⭐ م6: برای ادمین ورودی، بازکردن 🌐 فقط نمایش است؛ با اولین
            # ویرایش/آپلود، نسخه‌ی اختصاصی خودش ساخته می‌شود (CoW).
            kb.append([InlineKeyboardButton(
                f"🌐 {s['number']} — {s.get('topic','')[:20]}",
                callback_data=f'ca:session:{sid}')])
    if writable:
        kb.append([InlineKeyboardButton("➕ جلسه جدید", callback_data=f'ca:add_session_prompt:{lid}')])
    elif can_child:
        # 🌊 C3 — جلسه برای سطل خودش؛ نه دست‌زدن به درس/جلسات سراسری
        kb.append([InlineKeyboardButton(
            "➕ جلسه جدید (فقط ورودی خودم)",
            callback_data=f'ca:add_session_prompt:{lid}')])
    kb.append([InlineKeyboardButton("🔙 بازگشت",    callback_data=f'ca:term:{idx}')])
    lname = lesson.get('name','') if lesson else ''
    # ⭐ م6: سربرگ محدوده + legend یکدست
    hdr = await _scope_header(context, uid)
    if writable:
        ro_line = ("<i>🌐=سراسری (همه)  ⭐=نسخه‌ی اختصاصی ورودی  📅=بومی ورودی  "
                   "↩️=بازگشت به سراسری</i>")
    elif is_scoped:
        ro_line = ("🌐 سراسری — با اولین ویرایش/آپلود، نسخه‌ی اختصاصی ورودی شما ساخته می‌شود\n"
                   "<i>⭐=نسخه‌ی من  ↩️=بازگشت به سراسری  📅=بومی ورودی خودم</i>")
        if can_child:
            ro_line += "\n<i>📅=جلسه‌ی اختصاصی ورودی خودم (قابل ویرایش خودتان)</i>"
    else:
        ro_line = "🔒 🌐 سراسری — فقط‌خواندنی"
    await query.edit_message_text(
        f"{hdr}📖 <b>{lname}</b> — {len(sessions)} جلسه\n{ro_line}",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))


async def _show_session_content(query, context, sid):
    session  = await db.bs_get_session(sid)
    contents = await db.bs_get_content(sid)
    lid      = context.user_data.get('ca_lesson_id','')
    ICONS    = dict(CONTENT_TYPES)
    uid      = query.from_user.id
    session_iv = await db.session_intake(sid)
    writable = await db.can_access_intake(uid, session_iv)
    # ⭐ م6 — CoW: ادمین ورودی هم می‌تواند 🌐 را ویرایش/آپلود کند؛
    # تغییرات در لحظه‌ی ذخیره به override خودش هدایت می‌شود.
    _ck, _ct = await _cow_scope(context, uid)
    cow = writable or bool(_ck == 'scoped' and _ct and not session_iv)
    kb = []
    for i, c in enumerate(contents):
        cid  = str(c['_id'])
        ctype = c.get('type','pdf')
        desc  = c.get('description','')[:18] or f'فایل {i+1}'
        if cow:
            # ردیف فایل
            kb.append([
                InlineKeyboardButton(f"{ICONS.get(ctype,'📎')} {desc}", callback_data=f'ca:session:{sid}'),
                InlineKeyboardButton("🗑", callback_data=f'ca:del_content:{cid}'),
            ])
            # ردیف ترتیب
            nav = []
            if i > 0:
                nav.append(InlineKeyboardButton("⬆️", callback_data=f'ca:content_up:{cid}'))
            if i < len(contents) - 1:
                nav.append(InlineKeyboardButton("⬇️", callback_data=f'ca:content_down:{cid}'))
            if nav:
                kb.append(nav)
        else:
            kb.append([InlineKeyboardButton(
                f"{ICONS.get(ctype,'📎')} {desc}",
                callback_data=f'ca:session:{sid}')])

    if cow:
        if not contents:
            kb.append([InlineKeyboardButton("📤 آپلود اولین فایل", callback_data=f'ca:upload_content:{sid}')])
        else:
            kb.append([InlineKeyboardButton("📤 ➕ افزودن فایل جدید", callback_data=f'ca:upload_content:{sid}')])
        kb.append([InlineKeyboardButton("✏️ ویرایش اطلاعات جلسه", callback_data=f'ca:edit_session_menu:{sid}')])
    # ⭐ م6 (R5) — واگرایی: فایل‌های جدیدِ سراسری که این fork ندارد
    _new_from_base = 0
    if (session or {}).get('fork_of'):
        _new_from_base = await db.bs_base_new_content_count(sid)
        if _new_from_base:
            kb.append([InlineKeyboardButton(
                f"📥 افزودن {_new_from_base} فایل جدید از نسخه‌ی سراسری",
                callback_data=f'ca:merge_new:{sid}')])
    # ⭐ م6 — ↩️ با برچسب روشن برای fork خودِ محدوده‌ی جاری
    _own_scope_iv = (_ct if _ck == 'scoped' else context.user_data.get('ca_intake', ''))
    if (session or {}).get('fork_of') and _own_scope_iv == (session.get('intake') or ''):
        kb.append([InlineKeyboardButton(
            "↩️ بازگشت به نسخه‌ی سراسری (حذف شخصی‌سازی)",
            callback_data=f'ca:unfork_session:{sid}')])
    kb.append([InlineKeyboardButton("🔙 بازگشت",              callback_data=f'ca:lesson:{lid}')])

    by_type = {}
    for c in contents:
        by_type.setdefault(c.get('type','pdf'), []).append(c)
    summary = '  '.join(f"{ICONS.get(t,'📎')}×{len(v)}" for t,v in by_type.items()) if by_type else '❌ بدون فایل'

    # ⭐ م6: سربرگ محدوده + نشان هویت رکورد
    if session:
        _mk = "⭐" if session.get('fork_of') else ("📅" if session_iv else "🌐")
        _mk_note = ""
        if session.get('fork_of'):
            _mk_note = f" (نسخه‌ی اختصاصی ورودی {await _intake_label(session.get('intake') or '')})"
        elif session_iv:
            _mk_note = f" (بومی ورودی {await _intake_label(session_iv)})"
        footer = "<i>⬆️⬇️=ترتیب  🗑=حذف</i>" if cow else "🔒 🌐 سراسری — فقط‌خواندنی"
        if not writable and cow:
            footer = ("🌐 سراسری — با اولین تغییر، نسخه‌ی اختصاصی ورودی شما ساخته می‌شود (⭐)\n" + footer)
        if _new_from_base:
            footer += f"\n📥 نسخه‌ی سراسری {_new_from_base} فایل جدید دارد که این نسخه ندارد."
        hdr = await _scope_header(context, uid)
        header = (f"{hdr}{_mk} <b>جلسه {session.get('number','')}</b>{_mk_note}\n"
                  f"📚 {session.get('topic','')}\n"
                  f"👨‍🏫 {session.get('teacher','') or 'ثبت نشده'}\n"
                  f"━━━━━━━━━━━━━━━━\n"
                  f"📁 {len(contents)} فایل: {summary}\n"
                  f"{footer}")
    else:
        header = "📌 جلسه"
    await query.edit_message_text(header, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))


async def _show_ref_subjects(query, back='ca:main', context=None):
    # 🌊 C1 — موضوعات رفرنس فقط در scope انتخاب‌شده/قفل‌شده
    # 🌊 C1.5 — ادمین ورودی خاص: موضوعات سراسری هم «فقط‌خواندنی» دیده
    # می‌شوند (گروه‌بندی: اول ورودی من، بعد 🌐 سراسری با 🔒)
    intake = (context.user_data.get('ca_intake', '')
              if context is not None else '')
    is_scoped = False
    if context is not None:
        _cscope = await db.get_content_scope(query.from_user.id)
        is_scoped = bool(_cscope and _cscope.get('kind') == 'scoped')
    subjects = await db.ref_get_subjects(
        intake=[intake, ''] if intake else intake)
    if intake:
        own_items  = [s for s in subjects if (s.get('intake') or '') == intake]
        glob_items = [s for s in subjects if (s.get('intake') or '') != intake]
    elif is_scoped:
        # 🛡 C3.1 — بدون ورودیِ تنظیم‌شده چیزی «مال من» نیست؛ همه فقط‌خواندنی
        own_items, glob_items = [], subjects
    else:
        own_items, glob_items = subjects, []
    kb = []
    for i, s in enumerate(own_items):
        sid = str(s['_id'])
        kb.append([
            InlineKeyboardButton(f"📖 {s['name']}", callback_data=f'ca:ref_subject:{sid}'),
            InlineKeyboardButton("✏️", callback_data=f'ca:edit_ref_subject_prompt:{sid}'),
            InlineKeyboardButton("🗑",  callback_data=f'ca:del_ref_subject:{sid}'),
        ])
        nav = []
        if i > 0:
            nav.append(InlineKeyboardButton("⬆️", callback_data=f'ca:ref_subject_up:{sid}'))
        if i < len(own_items) - 1:
            nav.append(InlineKeyboardButton("⬇️", callback_data=f'ca:ref_subject_down:{sid}'))
        if nav:
            kb.append(nav)
    if glob_items and is_scoped:
        kb.append([InlineKeyboardButton(
            "── 🌐 منابع سراسری (🔒 فقط‌خواندنی) ──",
            callback_data='ca:ro_info')])
        for s in glob_items:
            kb.append([InlineKeyboardButton(
                f"🌐 {s['name']}",
                callback_data=f'ca:ref_subject:{str(s["_id"])}')])
    elif glob_items:
        kb.append([InlineKeyboardButton(
            "── 🌐 سراسری (ویرایش یا ✂️ روی کتاب) ──",
            callback_data='ca:ro_info')])
        for i, s in enumerate(glob_items):
            sid = str(s['_id'])
            kb.append([
                InlineKeyboardButton(f"🌐 {s['name']}", callback_data=f'ca:ref_subject:{sid}'),
                InlineKeyboardButton("✏️", callback_data=f'ca:edit_ref_subject_prompt:{sid}'),
                InlineKeyboardButton("🗑", callback_data=f'ca:del_ref_subject:{sid}'),
            ])
            nav = []
            if i > 0:
                nav.append(InlineKeyboardButton("⬆️", callback_data=f'ca:ref_subject_up:{sid}'))
            if i < len(glob_items) - 1:
                nav.append(InlineKeyboardButton("⬇️", callback_data=f'ca:ref_subject_down:{sid}'))
            if nav:
                kb.append(nav)
    if not (is_scoped and not intake):
        kb.append([InlineKeyboardButton("➕ درس جدید", callback_data='ca:add_ref_subject_prompt')])
    kb.append([InlineKeyboardButton("🔙 بازگشت",   callback_data=back)])
    if glob_items and is_scoped:
        ro_line = "\n🔒 🌐=سراسری — فقط‌خواندنی (مدیریت: 🎓 ادمین ارشد)"
    elif glob_items:
        ro_line = ("\n🌐 سراسری هم اینجاست. ✏️ نسخه‌ی مشترک را عوض می‌کند؛ "
                   "برای مخصوص‌کردن همین ورودی، کتاب را باز کنید و ✂️ بزنید.")
    else:
        ro_line = ''
    if is_scoped and not intake:
        ro_line += ("\n⚠️ برای نقش شما هنوز ورودی‌ای تنظیم نشده؛ فعلاً فقط "
                    "مشاهده‌ی سراسری دارید. از ادمین ارشد بخواهید ورودی‌تان را تعیین کند.")
    await query.edit_message_text(
        f"{await _scope_header(context, query.from_user.id)}"
        f"📚 <b>رفرنس‌ها</b> — {len(subjects)} درس\n<i>✏️=ویرایش  🗑=حذف  ⬆️⬇️=ترتیب</i>{ro_line}",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))


async def _show_ref_books(query, context, sid, back='ca:refs'):
    subj  = await db.ref_get_subject(sid)
    books = await db.ref_get_books(sid)
    uid   = query.from_user.id
    # 🌊 C1.5 — موضوع سراسری برای ادمین ورودی خاص: فقط‌خواندنی
    writable = await db.can_access_intake(
        uid, (subj or {}).get('intake') or '')
    _cscope   = await db.get_content_scope(uid)
    is_scoped = bool(_cscope and _cscope.get('kind') == 'scoped')
    ctx       = context.user_data.get('ca_intake', '')
    # 🌊 C3 — نماینده روی موضوع 🌐: «کتاب فقط‌ورودی‌خودم» ساختنی است (والد قفل)
    can_child  = (not writable and
                  await db.scoped_child_intake(uid, (subj or {}).get('intake') or '')
                  not in (None, ''))
    # ⭐ م6 (R2) — سطل سراسریِ ارشد: forkها زیر base جمع می‌شوند (⭐n)
    _ovr = await db.ref_override_counts(sid)
    if writable and not is_scoped and not ctx:
        _bases = {str(b['_id']) for b in books}
        books = [b for b in books
                 if not (b.get('fork_of') and str(b.get('fork_of')) in _bases)]
    elif ctx or (not writable and is_scoped):
        books = await db.ref_get_books_effective(sid, [ctx, ''])
    kb = []
    for i, b in enumerate(books):
        bid = str(b['_id'])
        is_fork  = bool(b.get('fork_of'))
        own_fork = is_scoped and is_fork and (b.get('intake') or '') == ctx
        # 🌊 C3 — فرزندِ ورودی‌خاص (کتابی که فقط برای ورودی من ساخته شده)
        own_child = bool(is_scoped and ctx and not is_fork
                         and (b.get('intake') or '') == ctx)
        if writable:
            resolved = _ca_bucket(b, (subj or {}).get('intake') or '')
            # ⭐ م6 (R7): نشان در ابتدای دکمه
            if is_fork:
                mk = f"⭐({await _intake_label(b.get('intake') or '')})"
            elif resolved:
                mk = f"📅({await _intake_label(resolved)})"
            else:
                mk = "🌐"
                if _ovr.get(bid):
                    mk = f"🌐 ⭐{_ovr[bid]}"
            row = [
                InlineKeyboardButton(f"{mk} {b['name']}", callback_data=f'ca:ref_book:{bid}'),
                InlineKeyboardButton("✏️", callback_data=f'ca:edit_ref_book_prompt:{bid}'),
                InlineKeyboardButton("🗑",  callback_data=f'ca:del_ref_book:{bid}'),
            ]
            # ⭐ م6 (R1): ✂️ حذف شد — شخصی‌سازی در لحظه‌ی ذخیره (CoW)
            if is_fork and ctx and (b.get('intake') or '') == ctx:
                row.append(InlineKeyboardButton("↩️", callback_data=f'ca:unfork_book:{bid}'))
            kb.append(row)
            nav = []
            if i > 0:
                nav.append(InlineKeyboardButton("⬆️", callback_data=f'ca:ref_book_up:{bid}'))
            if i < len(books) - 1:
                nav.append(InlineKeyboardButton("⬇️", callback_data=f'ca:ref_book_down:{bid}'))
            if nav:
                kb.append(nav)
        elif own_fork:
            kb.append([
                InlineKeyboardButton(
                    f"⭐ {b['name']} (نسخه‌ی من)",
                    callback_data=f'ca:ref_book:{bid}'),
                InlineKeyboardButton("↩️", callback_data=f'ca:unfork_book:{bid}'),
            ])
        elif own_child:
            kb.append([
                InlineKeyboardButton(
                    f"📅 {b['name']} (ورودی من)", callback_data=f'ca:ref_book:{bid}'),
                InlineKeyboardButton("✏️", callback_data=f'ca:edit_ref_book_prompt:{bid}'),
                InlineKeyboardButton("🗑",  callback_data=f'ca:del_ref_book:{bid}'),
            ])
        else:
            # ⭐ م6: بازکردن 🌐 برای ورودی‌خاص فقط نمایش است؛ CoW در ذخیره
            kb.append([InlineKeyboardButton(
                f"🌐 {b['name']}", callback_data=f'ca:ref_book:{bid}')])
    if writable:
        kb.append([InlineKeyboardButton("➕ کتاب جدید", callback_data=f'ca:add_ref_book_prompt:{sid}')])
    elif can_child:
        # 🌊 C3 — کتاب برای سطل خودش؛ هسته‌ی سراسری دست‌نخورده
        kb.append([InlineKeyboardButton(
            "➕ کتاب جدید (فقط ورودی خودم)",
            callback_data=f'ca:add_ref_book_prompt:{sid}')])
    kb.append([InlineKeyboardButton("🔙 بازگشت",    callback_data=back)])
    name = subj.get('name','') if subj else ''
    # ⭐ م6: سربرگ محدوده + legend یکدست (بدون ✂️)
    hdr = await _scope_header(context, uid)
    if writable:
        ro_line = ("<i>🌐=سراسری (همه)  ⭐=نسخه‌ی اختصاصی ورودی  📅=بومی ورودی  "
                   "↩️=بازگشت به سراسری</i>")
    elif is_scoped:
        ro_line = ("🌐 سراسری — با اولین ویرایش/آپلود، نسخه‌ی اختصاصی ورودی شما ساخته می‌شود\n"
                   "<i>⭐=نسخه‌ی من  ↩️=بازگشت به سراسری  📅=بومی ورودی خودم</i>")
    else:
        ro_line = "🔒 🌐 سراسری — فقط‌خواندنی"
    await query.edit_message_text(
        f"{hdr}📖 <b>{name}</b> — {len(books)} رفرنس\n{ro_line}",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))


async def _show_ref_book_files(query, context, bid):
    book    = await db.ref_get_book(bid)
    files   = await db.ref_get_files(bid)
    sid     = context.user_data.get('ca_ref_subject_id','')
    uid     = query.from_user.id
    book_iv = await db.ref_book_intake(bid)
    writable = await db.can_access_intake(uid, book_iv)
    # ⭐ م6 — CoW: ادمین ورودی می‌تواند 🌐 را ویرایش/آپلود کند؛ ذخیره→override
    _ck, _ct = await _cow_scope(context, uid)
    cow = writable or bool(_ck == 'scoped' and _ct and not book_iv)
    kb      = []

    # گروه‌بندی بر اساس زبان
    fa_files = sorted([f for f in files if f.get('lang') == 'fa'], key=lambda x: x.get('volume',1))
    en_files = sorted([f for f in files if f.get('lang') == 'en'], key=lambda x: x.get('volume',1))

    for lang, items, label_prefix in [('fa', fa_files, '🇮🇷 فارسی'), ('en', en_files, '🌐 لاتین')]:
        for f in items:
            fid = str(f['_id']); vol = f.get('volume',1); dl = f.get('downloads',0)
            desc = f.get('description','')
            row_label = f"✅ {label_prefix} جلد {vol}" + (f" — {desc[:15]}" if desc else '') + f"  ⬇️{dl}"
            if cow:
                kb.append([
                    InlineKeyboardButton(row_label, callback_data=f'ca:ref_book:{bid}'),
                    InlineKeyboardButton("🔄", callback_data=f'ca:upload_ref:{bid}:{lang}:{vol}'),
                    InlineKeyboardButton("🗑", callback_data=f'ca:del_ref_file:{fid}'),
                ])
            else:
                kb.append([InlineKeyboardButton(
                    row_label, callback_data=f'ca:ref_book:{bid}')])
        # دکمه افزودن جلد جدید
        if cow:
            kb.append([InlineKeyboardButton(
                f"📤 ➕ جلد جدید {label_prefix}",
                callback_data=f'ca:upload_ref_volume_prompt:{bid}:{lang}'
            )])

    if cow:
        kb.append([InlineKeyboardButton("✏️ ویرایش نام کتاب", callback_data=f'ca:edit_ref_book_prompt:{bid}')])
    # ⭐ م6 — ↩️ با برچسب روشن برای fork خودِ محدوده‌ی جاری
    _own_scope_iv = (_ct if _ck == 'scoped' else context.user_data.get('ca_intake', ''))
    if (book or {}).get('fork_of') and _own_scope_iv == ((book or {}).get('intake') or ''):
        kb.append([InlineKeyboardButton(
            "↩️ بازگشت به نسخه‌ی سراسری (حذف شخصی‌سازی)",
            callback_data=f'ca:unfork_book:{bid}')])
    kb.append([InlineKeyboardButton("🔙 بازگشت",           callback_data=f'ca:ref_subject:{sid}')])
    name = book.get('name','') if book else ''
    footer = "🔄=جایگزین  🗑=حذف  ➕=جلد جدید" if cow else "🔒 🌐 سراسری — فقط‌خواندنی"
    if not writable and cow:
        footer = ("🌐 سراسری — با اولین تغییر، نسخه‌ی اختصاصی ورودی شما ساخته می‌شود (⭐)\n" + footer)
    # ⭐ م6: سربرگ محدوده + نشان هویت رکورد
    _mk = "⭐" if (book or {}).get('fork_of') else ("📅" if book_iv else "🌐")
    hdr = await _scope_header(context, uid)
    await query.edit_message_text(
        f"{hdr}{_mk} <b>{name}</b>\n"
        f"📁 {len(files)} فایل\n\n"
        f"{footer}",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))


async def _show_faq(query, back='ca:main'):
    faqs = await db.faq_get_all()
    kb   = []
    for f in faqs[:15]:
        fid = str(f['_id'])
        kb.append([
            InlineKeyboardButton(f"❓ {f.get('question','')[:28]}", callback_data='ca:faq'),
            InlineKeyboardButton("✏️", callback_data=f'ca:edit_faq_menu:{fid}'),
            InlineKeyboardButton("🗑", callback_data=f'ca:del_faq:{fid}'),
        ])
    kb.append([InlineKeyboardButton("➕ سوال جدید", callback_data='ca:add_faq_prompt')])
    kb.append([InlineKeyboardButton("🔙 بازگشت",   callback_data=back)])
    await query.edit_message_text(
        f"❓ <b>سوالات متداول</b> — {len(faqs)} سوال\n<i>✏️=ویرایش  🗑=حذف</i>",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))


# ══════════════════════════════════════════════════════════
#  هندلر فایل
# ══════════════════════════════════════════════════════════

async def _ca_msg_scope(update, context):
    """🌊 C1 — گیت scope برای هندلرهای متن/فایل: scoped روی scope خودش
    قفل می‌شود؛ خروجی: (cscope, ctx_intake) یا (None, None) بی‌دسترسی."""
    uid = update.effective_user.id
    cscope = await db.get_content_scope(uid)
    if not cscope:
        return None, None
    if cscope['kind'] == 'scoped':
        context.user_data['ca_intake'] = cscope.get('intake') or ''
    return cscope, context.user_data.get('ca_intake') or ''


async def ca_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid     = update.effective_user.id
    if not await db.is_content_admin(uid): return
    _cscope, _ctx_intake = await _ca_msg_scope(update, context)
    if not _cscope: return
    ca_mode = context.user_data.get('ca_mode','')
    if ca_mode not in ('waiting_file','waiting_ref_file'): return

    # ── Extract file info (support all types incl. Photo) ──
    msg = update.message
    file_obj = None
    original_name = None
    mime_type = "application/octet-stream"
    file_size = 0
    media_type = "document"
    is_photo = False

    # Photo (no filename)
    if msg.photo:
        photo = msg.photo[-1] if isinstance(msg.photo, (list, tuple)) else msg.photo
        file_obj = photo
        original_name = f"photo_{photo.file_id[:8]}.jpg"
        mime_type = "image/jpeg"
        file_size = getattr(photo, 'file_size', 0) or 0
        media_type = "photo"
        is_photo = True
    elif msg.document:
        file_obj = msg.document
        original_name = getattr(file_obj, 'file_name', None) or "file"
        mime_type = getattr(file_obj, 'mime_type', None) or "application/octet-stream"
        file_size = getattr(file_obj, 'file_size', 0) or 0
        media_type = "document"
    elif msg.video:
        file_obj = msg.video
        original_name = getattr(file_obj, 'file_name', None) or f"video_{file_obj.file_id[:8]}.mp4"
        mime_type = getattr(file_obj, 'mime_type', None) or "video/mp4"
        file_size = getattr(file_obj, 'file_size', 0) or 0
        media_type = "video"
    elif msg.audio:
        file_obj = msg.audio
        original_name = getattr(file_obj, 'file_name', None) or f"audio_{file_obj.file_id[:8]}.mp3"
        mime_type = getattr(file_obj, 'mime_type', None) or "audio/mpeg"
        file_size = getattr(file_obj, 'file_size', 0) or 0
        media_type = "audio"
    elif msg.voice:
        file_obj = msg.voice
        original_name = f"voice_{file_obj.file_id[:8]}.ogg"
        mime_type = getattr(file_obj, 'mime_type', None) or "audio/ogg"
        file_size = getattr(file_obj, 'file_size', 0) or 0
        media_type = "voice"
    else:
        await update.message.reply_text("❌ فایل معتبر ارسال کنید (Document/Video/Audio/Photo/Voice).\n⌨️ /cancel")
        return CA_WAITING_FILE

    fid = file_obj.file_id
    # Also capture forward info (spec § forward support) — no extra logic needed, file_obj same
    info = {
        'file_id': fid,
        'original_name': original_name,
        'mime_type': mime_type,
        'file_size': file_size,
        'media_type': media_type,
        'is_photo': is_photo,
    }

    if ca_mode == 'waiting_ref_file':
        bid  = context.user_data.get('ca_ref_book_id','')
        lang = context.user_data.get('ca_ref_lang','fa')
        vol  = context.user_data.get('ca_ref_volume', 1)
        # Store pending and ask for filename
        context.user_data.update({
            'ca_pending_file': fid,
            'ca_pending_file_info': info,
            'ca_pending_original': original_name,
            'ca_mode': 'waiting_filename',
            'ca_pending_target': 'ref',
        })
        # Show filename prompt with current name and skip option
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("⏭ استفاده از نام فعلی", callback_data="ca:skip_filename")],
            [InlineKeyboardButton("❌ لغو", callback_data=f"ca:ref_book:{bid}")],
        ])
        await update.message.reply_text(
            f"✅ فایل دریافت شد: <code>{original_name}</code>\n\n"
            f"✏️ <b>نام نهایی فایل را بفرستید</b>\n"
            f"(پسوند <code>{original_name.split('.')[-1] if '.' in original_name else ''}</code> حفظ می‌شود، کاراکترهای <code>/\\:*?\"<>|</code> حذف می‌شوند)\n"
            f"یا روی «استفاده از نام فعلی» بزنید:\n⌨️ /cancel برای لغو",
            parse_mode='HTML', reply_markup=kb)
        return CA_WAITING_TEXT

    # فایل محتوای جلسه — go to filename step
    sid = context.user_data.get('ca_session_id','')
    context.user_data.update({
        'ca_pending_file': fid,
        'ca_pending_file_info': info,
        'ca_pending_original': original_name,
        'ca_mode': 'waiting_filename',
        'ca_pending_target': 'session',
    })
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⏭ استفاده از نام فعلی", callback_data="ca:skip_filename")],
        [InlineKeyboardButton("❌ لغو", callback_data=f"ca:session:{sid}")],
    ])
    await update.message.reply_text(
        f"✅ فایل دریافت شد: <code>{original_name}</code>\n\n"
        f"✏️ <b>نام نهایی فایل را بفرستید</b>\n"
        f"(مثلاً: <code>جزوه فیزیو - جلسه ۳</code> — پسوند خودکار اضافه می‌شود)\n"
        f"یا روی «استفاده از نام فعلی» بزنید:\n⌨️ /cancel برای لغو",
        parse_mode='HTML', reply_markup=kb)
    return CA_WAITING_TEXT


# ══════════════════════════════════════════════════════════
#  هندلر متن
# ══════════════════════════════════════════════════════════

_UI_FA = {
    'created': '🕘 در صف…', 'validating': '🔍 بررسی لینک…',
    'downloading': '⬇️ دریافت فایل از سرور مبدأ…',
    'validating_file': '🔬 بررسی فایل…',
    'uploading': '☁️ انتقال به تلگرام…',
    'registering': ' ثبت محتوا…',
    'completed': '✅ کامل شد — محتوا آماده‌ی دانشجوهاست.',
    'failed': '❌ ناموفق.', 'cancelled': ' لغو شد.',
    'duplicate': '⚠️ این فایل قبلاً درون‌ریزی شده.',
}


async def _ui_run_bot(message, uid: int, url: str, lesson: str, topic: str):
    """📥 URL-Import در بات — همان سرویس canonical (§106)، نه منطق موازی.
    پیشرفت با edit همان پیام (§47) — نه spam صدها پیام."""
    import url_import_service as uis
    user = await db.get_user(uid) or {}
    admin = {"id": uid, "name": user.get("name", "")}
    scope = await db.get_content_scope(uid) or {}
    try:
        doc = await uis.create_import_job(admin, {
            "url": url, "kind": "qbank", "lesson": lesson, "topic": topic,
            "intake": scope.get("intake") or "",
        }, idem_key=f"bot:{uid}:{hashlib.sha256(url.encode()).hexdigest()[:16]}")
    except uis.UrlImportError as e:
        await message.edit_text(f"❌ {e.message}")
        return
    job_id = str(doc["_id"])
    await uis.start_import_job(job_id)
    for _ in range(40):  # تا ~۲ دقیقه؛ بعدش ادمین از وب/مینی‌اپ پیگیری می‌کند
        await asyncio.sleep(3)
        doc = await uis.get_import_job(job_id)
        if not doc:
            break
        st = doc.get("status")
        pct = (doc.get("progress") or {}).get("percent")
        txt = f"📥 {doc.get('url_safe', '')}\n{_UI_FA.get(st, st)}"
        if isinstance(pct, int) and pct:
            txt += f" — {pct}٪"
        if doc.get("error"):
            txt += f"\n{doc['error'].get('code')}: {doc['error'].get('message')}"
        try:
            await message.edit_text(txt)
        except Exception as _e:
            logger.debug(f"_ui_run_bot edit failed: {_e}")
        if st in uis.TERMINAL:
            break


async def ca_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid     = update.effective_user.id
    if not await db.is_content_admin(uid): return ConversationHandler.END
    _cscope, _ctx_intake = await _ca_msg_scope(update, context)
    if not _cscope: return ConversationHandler.END
    ca_mode = context.user_data.get('ca_mode','')
    text    = update.message.text.strip()

    if text.lower() in ('/cancel','لغو','❌ لغو','cancel'):
        _clear(context)
        await update.message.reply_text("✅ عملیات لغو شد.")
        return ConversationHandler.END

    # FIX باگ مهم: 'ربات متن دریافت نمی‌کند' — این تابع به‌عنوان
    # entry_point ربات را در ConversationHandler نگه می‌داشت (با
    # callback pattern='^ca:') حتی بعد از خروج از پنل محتوا. اگر
    # ca_mode خالی/نامعتبر باشد (یعنی کاربر دیگر واقعاً در حال
    # تکمیل یک فرم محتوا نیست — مثلاً وارد broadcast شده)، باید
    # فوراً کنترل را به مسیر عادی (route_message) برگردانیم،
    # نه این‌که متن را بی‌صدا نادیده بگیریم.
    VALID_CA_MODES = {
        'add_lesson', 'add_session', 'edit_lesson', 'edit_session',
        'waiting_filename', 'confirming_filename',
        'waiting_description', 'waiting_ref_description',
        'add_faq', 'edit_faq', 'add_ref_subject', 'add_ref_book',
        'edit_ref_subject', 'edit_ref_book',
        'ui_url', 'ui_lesson', 'ui_topic',  # 📥 URL-Import
    }
    if ca_mode not in VALID_CA_MODES:
        from message_router import route_message
        return await route_message(update, context)

    # ── 📥 URL-Import — سه گام متنی: URL → درس → مبحث (§46) ──
    if ca_mode == 'ui_url':
        if not text.startswith(('http://', 'https://')):
            await update.message.reply_text(
                "⚠️ لینک باید با http:// یا https:// شروع بشه.")
            return ConversationHandler.END
        context.user_data['ui_url'] = text[:2048]
        context.user_data['ca_mode'] = 'ui_lesson'
        await update.message.reply_text("📚 نام درس رو بفرست:")
        return ConversationHandler.END

    if ca_mode == 'ui_lesson':
        context.user_data['ui_lesson'] = text[:100]
        context.user_data['ca_mode'] = 'ui_topic'
        await update.message.reply_text("🧭 نام مبحث رو بفرست:")
        return ConversationHandler.END

    if ca_mode == 'ui_topic':
        url = context.user_data.pop('ui_url', '')
        lesson = context.user_data.pop('ui_lesson', '')
        _clear(context)
        msg = await update.message.reply_text("⏳ ساخت job درون‌ریزی…")
        await _ui_run_bot(msg, uid, url, lesson, text[:100])
        return ConversationHandler.END

    # ── 📄 File naming: waiting for custom filename ──
    if ca_mode == 'waiting_filename':
        # handle skip via text as well
        if text in ('⏭ استفاده از نام فعلی', '⏭', 'skip', '-'):
            orig = context.user_data.get('ca_pending_original', '') or context.user_data.get('ca_pending_file_info', {}).get('original_name','file')
            context.user_data['ca_pending_display'] = orig
            target = context.user_data.get('ca_pending_target', 'session')
            if target == 'ref':
                context.user_data['ca_mode'] = 'waiting_ref_description'
                bid = context.user_data.get('ca_ref_book_id','')
                lang = context.user_data.get('ca_ref_lang','fa')
                vol = context.user_data.get('ca_ref_volume', 1)
                ll = "🇮🇷 فارسی" if lang == 'fa' else "🌐 لاتین"
                await update.message.reply_text(
                    f"✅ نام نهایی: <code>{orig}</code>\n\n"
                    f"📝 توضیح اختیاری برای {ll} جلد {vol}:\n"
                    "اگر توضیحی ندارید <code>-</code> بزنید:\n⌨️ /cancel",
                    parse_mode='HTML', reply_markup=_back_btn("❌ لغو", f'ca:ref_book:{bid}'))
            else:
                context.user_data['ca_mode'] = 'waiting_description'
                sid = context.user_data.get('ca_session_id','')
                await update.message.reply_text(
                    f"✅ نام نهایی: <code>{orig}</code>\n\n"
                    "📝 توضیح اختیاری برای این فایل:\n"
                    "اگر توضیحی ندارید <code>-</code> بزنید:\n⌨️ /cancel",
                    parse_mode='HTML', reply_markup=_back_btn("❌ لغو", f'ca:session:{sid}'))
            return CA_WAITING_TEXT
        # normal filename input
        try:
            from utils_file_naming import prepare_rename, get_extension
        except ImportError:
            try:
                from humsyarx.utils_file_naming import prepare_rename, get_extension  # fallback
            except ImportError:
                # minimal fallback sanitize
                def prepare_rename(a,b,*args,**kwargs): return {'display_name': a.strip() or b}
                def get_extension(x): return x.split('.')[-1] if '.' in x else ''
        orig = context.user_data.get('ca_pending_original', '') or context.user_data.get('ca_pending_file_info', {}).get('original_name','file.pdf')
        target = context.user_data.get('ca_pending_target', 'session')
        # collect existing for dedup
        existing = set()
        try:
            if target == 'ref':
                bid = context.user_data.get('ca_ref_book_id','')
                async for d in db.ref_files.find({'book_id': bid}, {'display_name': 1, 'display_file_name': 1}):
                    n = d.get('display_file_name') or d.get('display_name') or ''
                    if n: existing.add(n)
            else:
                sid = context.user_data.get('ca_session_id','')
                async for d in db.bs_content.find({'session_id': sid}, {'display_name': 1, 'display_file_name': 1}):
                    n = d.get('display_file_name') or d.get('display_name') or ''
                    if n: existing.add(n)
        except Exception:
            pass
        prep = prepare_rename(text, orig, existing_names=existing, fallback='فایل')
        display = prep['display_name']
        context.user_data['ca_pending_display'] = display
        context.user_data['ca_mode'] = 'confirming_filename'
        # show confirmation with buttons
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ تایید", callback_data="ca:confirm_filename"),
             InlineKeyboardButton("✏️ ویرایش", callback_data="ca:edit_filename")],
            [InlineKeyboardButton("⏭ استفاده از نام فعلی", callback_data="ca:skip_filename")],
            [InlineKeyboardButton("❌ لغو", callback_data="ca:cancel_filename")]
        ])
        note_dup = " (تکراری — به (1) تغییر یافت)" if prep.get('deduplicated') else ""
        note_trunc = " (کوتاه شد)" if prep.get('truncated') else ""
        await update.message.reply_text(
            f"📄 نام نهایی: <code>{display}</code>{note_dup}{note_trunc}\n"
            f"اصلی: <code>{orig}</code>\n\n"
            "آیا تایید می‌کنید؟",
            parse_mode='HTML', reply_markup=kb)
        return CA_WAITING_TEXT

    if ca_mode == 'confirming_filename':
        # If user sends text while confirming, treat as new filename
        context.user_data['ca_mode'] = 'waiting_filename'
        # re-invoke same logic (avoid recursion, just handle as new input)
        # Store text as new candidate and show again? reuse above block logic
        # To avoid duplication, just set pending and call same prepare
        try:
            from utils_file_naming import prepare_rename, get_extension
        except ImportError:
            try:
                from humsyarx.utils_file_naming import prepare_rename, get_extension
            except ImportError:
                def prepare_rename(a,b,*args,**kwargs): return {'display_name': a.strip() or b}
                def get_extension(x): return x.split('.')[-1] if '.' in x else ''
        orig = context.user_data.get('ca_pending_original', '') or context.user_data.get('ca_pending_file_info', {}).get('original_name','file.pdf')
        target = context.user_data.get('ca_pending_target', 'session')
        existing = set()
        try:
            if target == 'ref':
                bid = context.user_data.get('ca_ref_book_id','')
                async for d in db.ref_files.find({'book_id': bid}, {'display_name': 1, 'display_file_name': 1}):
                    n = d.get('display_file_name') or d.get('display_name') or ''
                    if n: existing.add(n)
            else:
                sid = context.user_data.get('ca_session_id','')
                async for d in db.bs_content.find({'session_id': sid}, {'display_name': 1, 'display_file_name': 1}):
                    n = d.get('display_file_name') or d.get('display_name') or ''
                    if n: existing.add(n)
        except Exception:
            pass
        prep = prepare_rename(text, orig, existing_names=existing, fallback='فایل')
        display = prep['display_name']
        context.user_data['ca_pending_display'] = display
        context.user_data['ca_mode'] = 'confirming_filename'
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ تایید", callback_data="ca:confirm_filename"),
             InlineKeyboardButton("✏️ ویرایش", callback_data="ca:edit_filename")],
            [InlineKeyboardButton("⏭ استفاده از نام فعلی", callback_data="ca:skip_filename")],
            [InlineKeyboardButton("❌ لغو", callback_data="ca:cancel_filename")]
        ])
        await update.message.reply_text(
            f"📄 نام نهایی: <code>{display}</code>\n"
            f"اصلی: <code>{orig}</code>\n\nآیا تایید می‌کنید؟",
            parse_mode='HTML', reply_markup=kb)
        return CA_WAITING_TEXT

    if ca_mode == 'add_lesson':
        ps = [p.strip() for p in text.split(',')]
        name = ps[0]; teacher = ps[1] if len(ps) > 1 else ''
        term = context.user_data.get('ca_term',''); idx = context.user_data.get('ca_term_idx',0)
        # 🛡 C3.1 — سطل مقصد ساخت باید واقعاً نوشتنی باشد (scoped بدونِ scope
        # سراسری را نوشتنی نیست؛ قبلاً دقیقاً همان‌جا می‌نوشت)
        if not await db.can_access_intake(uid, _ctx_intake):
            _clear(context)
            await update.message.reply_text(
                "⛔ ساخت درس مجاز نیست — برای نقش شما هنوز ورودی‌ای تنظیم نشده.\n"
                "از ادمین ارشد بخواهید ورودی شما را تعیین کند.",
                reply_markup=_back_btn("🔙 برگشت", f'ca:term:{idx}'))
            return ConversationHandler.END
        # 🌊 C1 — درس جدید دقیقاً در scope جاری context ساخته می‌شود
        result = await db.bs_add_lesson(term, name, teacher, intake=_ctx_intake)
        _clear(context)
        msg = f"✅ درس «{name}» اضافه شد!" if result else "⚠️ این درس قبلاً وجود دارد."
        if result:
            await _audit(context, uid, "ایجاد درس جدید",
                severity='INFO',
                target_type='lesson',
                target_label=name,
                details=f"ترم: {term}\n🏷 ورودی: {await _intake_label(_ctx_intake)}",
                tags=['ایجاد_درس'])
        await update.message.reply_text(msg, reply_markup=_back_btn("🔙 برگشت", f'ca:term:{idx}'))

    elif ca_mode == 'edit_lesson':
        lid = context.user_data.get('ca_edit_target',''); field = context.user_data.get('ca_edit_field','')
        if not await db.can_access_intake(uid, await db.lesson_intake(lid)):
            _clear(context)
            await update.message.reply_text("⛔ دسترسی غیرمجاز — این درس در scope شما نیست.")
            return ConversationHandler.END
        # FIX جدید: مقدار قبلی را برای لاگ before/after نگه می‌داریم
        old_lesson = await db.bs_get_lesson(lid)
        old_value  = old_lesson.get(field, '') if old_lesson else ''
        ok = await db.bs_update_lesson(lid, {field: text})
        _clear(context)
        if ok:
            await _audit(context, uid, "ویرایش درس",
                severity='WARNING',
                target_id=lid,
                target_type='lesson',
                target_label=old_lesson.get('name', '') if old_lesson else '',
                before={field: old_value},
                after={field: text},
                tags=['ویرایش_درس'])
        await update.message.reply_text("✅ ذخیره شد." if ok else "❌ خطا.",
            reply_markup=_back_btn("🔙 برگشت", f'ca:lesson:{lid}'))

    elif ca_mode == 'add_session':
        ps  = [p.strip() for p in text.split(',')]
        lid = context.user_data.get('ca_lesson_id','')
        _lesson = await db.bs_get_lesson(lid)
        # 🌊 C3 — «فرزند ورودی‌خاص»: scoped روی درس 🌐 مجاز است جلسه‌ی فقط-ورودیِ
        # خودش را بسازد؛ هر حالت دیگر (ورودی دیگر / بدون scope) همچنان ⛔.
        _child = await db.scoped_child_intake(uid, (_lesson or {}).get('intake') or '')
        if _child is None:
            _clear(context)
            await update.message.reply_text("⛔ دسترسی غیرمجاز — این درس در scope شما نیست.")
            return ConversationHandler.END
        if len(ps) < 2:
            await update.message.reply_text(
                "❌ فرمت اشتباه!\nمثال: <code>3, فیزیولوژی کلیه, دکتر احمدی</code>\n⌨️ /cancel",
                parse_mode='HTML', reply_markup=_back_btn("❌ لغو", f'ca:lesson:{lid}'))
            return CA_WAITING_TEXT
        try:    number = int(ps[0])
        except (ValueError, IndexError):
            # 🛡 §۲۰ — خطای تبدیل عدد، نه «هر چیزی» (bare except لغو/shutdown را می‌بلعد)
            number = await db.bs_next_session_number(lid, _child or None)
        topic = ps[1]; teacher = ps[2] if len(ps) > 2 else ''
        await db.bs_add_session(lid, number, topic, teacher, intake=_child or None)
        _clear(context)
        _warn = ""
        if _child and await db.bs_session_number_taken(lid, number):
            _warn = ("\n⚠️ نسخه‌ی سراسری با همین شماره وجود دارد؛ در لیست دانشجو "
                     "هر دو دیده می‌شوند (برای جایگزینی از ✂️ استفاده کنید).")
        await _audit(context, uid, "ایجاد جلسه جدید",
            severity='INFO',
            target_type='session',
            target_label=f"جلسه {number} — {topic}",
            details=f"📅 فقط ورودی {await _intake_label(_child)}" if _child else "",
            tags=['ایجاد_جلسه'] + ([f"ورودی_{_child}"] if _child else []))
        await update.message.reply_text(
            f"✅ جلسه {number} — «{topic}» اضافه شد!"
            + (f"\n📅 فقط برای ورودی «{await _intake_label(_child)}».{_warn}" if _child else ""),
            reply_markup=_back_btn("🔙 برگشت", f'ca:lesson:{lid}'))

    elif ca_mode == 'edit_session':
        sid = context.user_data.get('ca_edit_target',''); field = context.user_data.get('ca_edit_field','')
        # ⭐ م6 — CoW در لحظه‌ی ذخیره: هدف از سرور؛ override در صورت نیاز
        _tgt, _note = await _cow_session_target(context, uid, sid)
        if _tgt is None:
            _clear(context)
            await update.message.reply_text(
                "⛔ دسترسی غیرمجاز — این جلسه در scope شما نیست."
                if _note == 'deny' else
                "⚖️ ابتدا محدوده‌ی تغییر را انتخاب کنید (🌐 سراسری / ⭐ فقط ورودی).")
            return ConversationHandler.END
        sid = _tgt
        val = int(text) if field == 'number' and text.isdigit() else text
        old_session = await db.bs_get_session(sid)
        old_value   = old_session.get(field, '') if old_session else ''
        ok  = await db.bs_update_session(sid, {field: val})
        _clear(context)
        if ok:
            session_label_for_log = f"جلسه {old_session.get('number','')} — {old_session.get('topic','')}" if old_session else sid
            await _audit(context, uid, "ویرایش جلسه",
                severity='WARNING',
                target_id=sid,
                target_type='session',
                target_label=session_label_for_log,
                before={field: old_value},
                after={field: val},
                tags=['ویرایش_جلسه'])
        await update.message.reply_text(
            ("✅ جلسه ویرایش شد." if ok else "❌ خطا.") + (f"\n{_note}" if _note else ""),
            reply_markup=_back_btn("🔙 برگشت", f'ca:session:{sid}'))

    elif ca_mode == 'waiting_description':
        desc = '' if text == '-' else text
        fid  = context.user_data.get('ca_pending_file','')
        sid  = context.user_data.get('ca_session_id','')
        ct   = context.user_data.get('ca_content_type','pdf')
        # ⭐ م6 — CoW در لحظه‌ی ثبت: هدف از سرور؛ override در صورت نیاز
        _tgt, _note = await _cow_session_target(context, uid, sid)
        if _tgt is None:
            _clear(context)
            await update.message.reply_text(
                "⛔ دسترسی غیرمجاز — این جلسه در scope شما نیست."
                if _note == 'deny' else
                "⚖️ ابتدا محدوده‌ی تغییر را انتخاب کنید (🌐 سراسری / ⭐ فقط ورودی).")
            return ConversationHandler.END
        sid = _tgt
        context.user_data['ca_session_id'] = sid
        # ── 📄 Resolve final filename with re-upload if needed ──
        pending_info = context.user_data.get('ca_pending_file_info', {}) or {}
        orig_name = context.user_data.get('ca_pending_original') or pending_info.get('original_name','') or 'file.pdf'
        disp_name = context.user_data.get('ca_pending_display') or orig_name
        mime = pending_info.get('mime_type', 'application/octet-stream')
        fsize = pending_info.get('file_size', 0)
        is_photo = pending_info.get('is_photo', False)
        # Determine if re-upload needed (rename or photo->document)
        need_reupload = False
        try:
            from utils_file_naming import get_extension as _get_ext
        except ImportError:
            try:
                from humsyarx.utils_file_naming import get_extension as _get_ext
            except ImportError:
                def _get_ext(x): return x.split('.')[-1] if '.' in x else ''
        # Compare normalized? If display differs from original, need
        if disp_name.strip() != orig_name.strip():
            need_reupload = True
        if is_photo:
            need_reupload = True
        final_fid = fid
        if need_reupload and fid:
            try:
                # Dedicated Rename Pipeline — فقط همین سرویس از Local Bot API استفاده می‌کند
                try:
                    from telegram_file_rename_service import rename_telegram_file
                except ImportError:
                    from humsyarx.telegram_file_rename_service import rename_telegram_file
                new_id, new_name = await rename_telegram_file(uid, fid, disp_name, mime)
                if new_id:
                    final_fid = new_id
                    # Verify filename از Telegram برگشتی
                    if new_name and new_name != disp_name:
                        logger.warning(f"RENAME_VERIFY_MISMATCH expected={disp_name} got={new_name}")
                    logger.info(f"DEDICATED_RENAME_OK old={fid[:10]} new={new_id[:10]} name={new_name or disp_name} via={'local' if (__import__('os').getenv('TELEGRAM_LOCAL_API_URL') or '').strip() else 'cloud'}")
                else:
                    logger.warning(f"DEDICATED_RENAME_FAIL keep original file_id for {disp_name} — display_name همچنان در لیست/کپشن دیده می‌شود")
            except Exception as e:
                logger.warning(f"dedicated rename error: {e}")
                final_fid = fid
        # Prepare extension from display
        ext = _get_ext(disp_name)
        # Insert with naming fields
        cid_new = await db.bs_add_content(sid, ct, final_fid, description=desc,
                                          original_name=orig_name, display_name=disp_name,
                                          file_extension=ext, mime_type=mime, file_size=fsize)
        tl = dict(CONTENT_TYPES).get(ct, ct)
        try:
            _sess_for_audit = await db.bs_get_session(sid) or {}
            await _audit(context, uid, f"افزودن {tl}",
                severity='INFO',
                target_id=str(cid_new or ''),
                target_type='content',
                target_label=desc[:60] if desc else tl,
                details=f"جلسه: {_sess_for_audit.get('topic','')[:50]}\nنوع: {tl}" + (f"\n📝 {desc[:120]}" if desc else ""),
                tags=['افزودن_محتوا', ct])
        except Exception as _e:
            logger.warning(f"add_content audit failed: {_e}")
        _clear(context)
        # اطلاع به ادمین: نام نمایشی حتی اگر reupload ناموفق بود در لیست دانشجو دیده می‌شود
        msg_extra = f"\n📄 نام فایل: <code>{disp_name}</code>"
        # سایلنت: حتی اگر نام تلگرامی به دلیل محدودیت موقت عوض نشد، نمایش لیست و کپشن همین نام است
        if final_fid != fid:
            msg_extra += " — ✅"
        await update.message.reply_text(
            f"✅ {tl} اضافه شد!{msg_extra}" + (f"\n{_note}" if _note else ""),
            parse_mode='HTML', reply_markup=_back_btn("🔙 برگشت", f'ca:session:{sid}'))

    elif ca_mode == 'waiting_ref_description':
        desc  = '' if text == '-' else text
        fid   = context.user_data.get('ca_pending_file','')
        bid   = context.user_data.get('ca_ref_book_id','')
        lang  = context.user_data.get('ca_ref_lang','fa')
        vol   = context.user_data.get('ca_ref_volume', 1)
        # ⭐ م6 — CoW در لحظه‌ی ثبت
        _tgt, _note = await _cow_book_target(context, uid, bid)
        if _tgt is None:
            _clear(context)
            await update.message.reply_text(
                "⛔ دسترسی غیرمجاز — این رفرنس در scope شما نیست."
                if _note == 'deny' else
                "⚖️ ابتدا محدوده‌ی تغییر را انتخاب کنید (🌐 سراسری / ⭐ فقط ورودی).")
            return ConversationHandler.END
        bid = _tgt
        context.user_data['ca_ref_book_id'] = bid
        pending_info = context.user_data.get('ca_pending_file_info', {}) or {}
        orig_name = context.user_data.get('ca_pending_original') or pending_info.get('original_name','') or 'file.pdf'
        disp_name = context.user_data.get('ca_pending_display') or orig_name
        mime = pending_info.get('mime_type', 'application/octet-stream')
        fsize = pending_info.get('file_size', 0)
        is_photo = pending_info.get('is_photo', False)
        need_reupload = (disp_name.strip() != orig_name.strip()) or is_photo
        final_fid = fid
        if need_reupload and fid:
            try:
                try:
                    from telegram_file_rename_service import rename_telegram_file
                except ImportError:
                    from humsyarx.telegram_file_rename_service import rename_telegram_file
                new_id, new_name = await rename_telegram_file(uid, fid, disp_name, mime)
                if new_id:
                    final_fid = new_id
                    if new_name and new_name != disp_name:
                        logger.warning(f"REF_RENAME_VERIFY_MISMATCH expected={disp_name} got={new_name}")
                    logger.info(f"DEDICATED_REF_RENAME_OK old={fid[:10]} new={new_id[:10]} name={new_name or disp_name} via={'local' if (__import__('os').getenv('TELEGRAM_LOCAL_API_URL') or '').strip() else 'cloud'}")
                else:
                    logger.warning(f"DEDICATED_REF_RENAME_FAIL keep original for {disp_name}")
            except Exception as e:
                logger.warning(f"dedicated ref rename error: {e}")
        try:
            from utils_file_naming import get_extension as _get_ext2
        except ImportError:
            try:
                from humsyarx.utils_file_naming import get_extension as _get_ext2
            except ImportError:
                def _get_ext2(x): return x.split('.')[-1] if '.' in x else ''
        ext = _get_ext2(disp_name)
        fid_new = await db.ref_add_file(bid, lang, final_fid, volume=vol, description=desc,
                                        original_name=orig_name, display_name=disp_name,
                                        file_extension=ext, mime_type=mime, file_size=fsize)
        ll = "🇮🇷 فارسی" if lang == 'fa' else "🌐 لاتین"
        try:
            _book_for_audit = await db.ref_get_book(bid) or {}
            await _audit(context, uid, f"آپلود رفرنس {ll} جلد {vol}",
                severity='INFO',
                target_id=str(fid_new or ''),
                target_type='ref_file',
                target_label=f"{_book_for_audit.get('name','')} — {ll} جلد {vol}",
                details=(f"کتاب: {_book_for_audit.get('name','')}" + (f"\n📝 {desc[:120]}" if desc else "")),
                tags=['آپلود_رفرنس', lang])
        except Exception as _e:
            logger.warning(f"ref_add_file audit failed: {_e}")
        _clear(context)
        msg_extra_ref = f"\n📄 نام فایل: <code>{disp_name}</code>"
        if final_fid != fid:
            msg_extra_ref += " — ✅"
        await update.message.reply_text(
            f"✅ {ll} جلد {vol} آپلود شد!" + (f"\n📝 {desc}" if desc else '') + msg_extra_ref
            + (f"\n{_note}" if _note else ""),
            parse_mode='HTML',
            reply_markup=_back_btn("🔙 برگشت", f'ca:ref_book:{bid}'))

    elif ca_mode == 'add_ref_subject':
        # 🛡 C3.1 — سطل مقصد باید نوشتنی باشد (scoped بدونِ scope ⇒ نه سراسری)
        if not await db.can_access_intake(uid, _ctx_intake):
            _clear(context)
            fa = context.user_data.get('ca_ref_from_admin', False)
            await update.message.reply_text(
                "⛔ ساخت موضوع مجاز نیست — برای نقش شما هنوز ورودی‌ای تنظیم نشده.\n"
                "از ادمین ارشد بخواهید ورودی شما را تعیین کند.",
                reply_markup=_back_btn("🔙 برگشت", 'ca:refs_admin' if fa else 'ca:refs'))
            return ConversationHandler.END
        # 🌊 C1 — موضوع جدید در scope جاری context
        result = await db.ref_add_subject(text, intake=_ctx_intake)
        fa = context.user_data.get('ca_ref_from_admin', False)
        back = 'ca:refs_admin' if fa else 'ca:refs'
        if result:
            try:
                await _audit(context, uid, "ایجاد موضوع رفرنس",
                    severity='INFO',
                    target_id=str(result or ''),
                    target_type='ref_subject',
                    target_label=text,
                    details=f"🏷 ورودی: {await _intake_label(_ctx_intake)}",
                    tags=['ایجاد_رفرنس'])
            except Exception as _e:
                logger.warning(f"ref_add_subject audit failed: {_e}")
        _clear(context)
        await update.message.reply_text(
            f"✅ درس «{text}» اضافه شد!" if result else "⚠️ قبلاً وجود دارد.",
            reply_markup=_back_btn("🔙 برگشت", back))

    elif ca_mode == 'edit_ref_subject':
        sid = context.user_data.get('ca_edit_target','')
        if not await db.can_access_intake(uid, await db.ref_subject_intake(sid)):
            _clear(context)
            await update.message.reply_text("⛔ دسترسی غیرمجاز — این موضوع در scope شما نیست.")
            return ConversationHandler.END
        _old_subj = await db.ref_get_subject(sid) or {}
        _old_name = _old_subj.get('name','')
        ok  = await db.ref_update_subject(sid, {'name': text})
        if ok:
            try:
                await _audit(context, uid, "ویرایش موضوع رفرنس",
                    severity='WARNING',
                    target_id=sid,
                    target_type='ref_subject',
                    target_label=_old_name,
                    before={'name': _old_name},
                    after={'name': text},
                    tags=['ویرایش_رفرنس'])
            except Exception as _e:
                logger.warning(f"edit_ref_subject audit failed: {_e}")
        _clear(context)
        await update.message.reply_text(f"✅ نام به «{text}» تغییر یافت." if ok else "❌ خطا.",
            reply_markup=_back_btn("🔙 برگشت", f'ca:ref_subject:{sid}'))

    elif ca_mode == 'add_ref_book':
        sid = context.user_data.get('ca_ref_subject_id','')
        _subj_bk = await db.ref_subject_intake(sid)
        # 🌊 C3 — «فرزند ورودی‌خاص»: scoped زیر موضوع 🌐 مجاز است کتابِ فقط-ورودیِ
        # خودش را بسازد؛ هر حالت دیگر (ورودی دیگر / بدون scope) همچنان ⛔.
        _child = await db.scoped_child_intake(uid, _subj_bk)
        if _child is None:
            _clear(context)
            await update.message.reply_text("⛔ دسترسی غیرمجاز — این موضوع در scope شما نیست.")
            return ConversationHandler.END
        _bk = await db.ref_add_book(sid, text, intake=_child or None)
        _clear(context)
        await _audit(context, uid, "ایجاد کتاب رفرنس",
            severity='INFO',
            target_id=str(_bk or ''),
            target_type='reference_book',
            target_label=text,
            details=f"📅 فقط ورودی {await _intake_label(_child)}" if _child else "",
            tags=['ایجاد_رفرنس'] + ([f"ورودی_{_child}"] if _child else []))
        await update.message.reply_text(
            f"✅ رفرنس «{text}» اضافه شد!"
            + (f"\n📅 فقط برای ورودی «{await _intake_label(_child)}»." if _child else ""),
            reply_markup=_back_btn("🔙 برگشت", f'ca:ref_subject:{sid}'))

    elif ca_mode == 'edit_ref_book':
        bid = context.user_data.get('ca_edit_target','')
        # ⭐ م6 — CoW در لحظه‌ی ذخیره
        _tgt, _note = await _cow_book_target(context, uid, bid)
        if _tgt is None:
            _clear(context)
            await update.message.reply_text(
                "⛔ دسترسی غیرمجاز — این رفرنس در scope شما نیست."
                if _note == 'deny' else
                "⚖️ ابتدا محدوده‌ی تغییر را انتخاب کنید (🌐 سراسری / ⭐ فقط ورودی).")
            return ConversationHandler.END
        bid = _tgt
        context.user_data['ca_edit_target'] = bid
        _old_book = await db.ref_get_book(bid) or {}
        _old_bname = _old_book.get('name','')
        ok  = await db.ref_update_book(bid, {'name': text})
        if ok:
            try:
                await _audit(context, uid, "ویرایش کتاب رفرنس",
                    severity='WARNING',
                    target_id=bid,
                    target_type='reference_book',
                    target_label=_old_bname,
                    before={'name': _old_bname},
                    after={'name': text},
                    tags=['ویرایش_رفرنس'])
            except Exception as _e:
                logger.warning(f"edit_ref_book audit failed: {_e}")
        _clear(context)
        await update.message.reply_text(
            (f"✅ نام کتاب به «{text}» تغییر یافت." if ok else "❌ خطا.")
            + (f"\n{_note}" if _note else ""),
            reply_markup=_back_btn("🔙 برگشت", f'ca:ref_book:{bid}'))

    elif ca_mode == 'add_faq':
        ps = [p.strip() for p in text.split('|')]
        if len(ps) < 2:
            await update.message.reply_text(
                "❌ فرمت اشتباه!\nمثال: <code>سوال | جواب | دسته</code>\n⌨️ /cancel",
                parse_mode='HTML'); return CA_WAITING_TEXT
        question = ps[0]; answer = ps[1]; category = ps[2] if len(ps) > 2 else 'عمومی'
        faq_id = await db.faq_add(question, answer, category)
        try:
            await _audit(context, uid, "ایجاد سوال متداول",
                severity='INFO',
                target_id=str(faq_id or ''),
                target_type='faq',
                target_label=question[:60],
                details=f"دسته: {category}",
                tags=['ایجاد_FAQ'])
        except Exception as _e:
            logger.warning(f"add_faq audit failed: {_e}")
        _clear(context)
        await update.message.reply_text(f"✅ سوال اضافه شد!",
            reply_markup=_back_btn("🔙 برگشت", 'ca:faq'))

    elif ca_mode == 'edit_faq':
        fid = context.user_data.get('ca_edit_target',''); field = context.user_data.get('ca_edit_field','')
        if not fid or field not in ('question','answer','category'):
            _clear(context)
            await update.message.reply_text("❌ خطا — دوباره از منو اقدام کنید.")
            return ConversationHandler.END
        old = await db.faq_get(fid)
        if not old:
            _clear(context)
            await update.message.reply_text("❌ سوال پیدا نشد.")
            return ConversationHandler.END
        val = text.strip()
        if not val:
            await update.message.reply_text("❌ مقدار خالی مجاز نیست — دوباره بفرست یا /cancel")
            return CA_WAITING_TEXT
        ok = await db.faq_update(fid, {field: val})
        _clear(context)
        if ok:
            try:
                await _audit(context, uid, "ویرایش سوال متداول",
                    severity='WARNING',
                    target_id=fid,
                    target_type='faq',
                    target_label=old.get('question','')[:60],
                    before={field: old.get(field,'')},
                    after={field: val},
                    tags=['ویرایش_FAQ'])
            except Exception as _e:
                logger.warning(f"edit_faq audit failed: {_e}")
            await update.message.reply_text("✅ ویرایش ذخیره شد.",
                reply_markup=_back_btn("🔙 بازگشت", 'ca:faq'))
        else:
            await update.message.reply_text("❌ ویرایش انجام نشد.",
                reply_markup=_back_btn("🔙 بازگشت", 'ca:faq'))

    else:
        _clear(context)
        await update.message.reply_text("⚠️ لطفاً از منوی ربات استفاده کنید.")
        return ConversationHandler.END
