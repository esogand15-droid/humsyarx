"""
پنل ادمین محتوا — نسخه نهایی با:
  ✅ ترتیب‌بندی درس‌ها (بالا/پایین)
  ✅ ترتیب‌بندی فایل‌های جلسه
  ✅ چند جلد برای رفرنس
  ✅ توضیحات اضافه (اختیاری) برای فایل
  ✅ لغو با /cancel در هر مرحله
  ✅ ویرایش و حذف همه موارد
"""
import os, logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import db

logger   = logging.getLogger(__name__)
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))

TERMS = ['ترم ۱', 'ترم ۲', 'ترم ۳', 'ترم ۴', 'ترم ۵']
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
    for k in ['ca_mode','ca_pending_file','ca_content_type',
              'ca_edit_target','ca_edit_field','ca_ref_lang','ca_ref_volume']:
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
        label = await _intake_label(scope.get('intake') or '')
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
}


# 🌊 C1.5 — اکشن‌های «فقط‌مشاهده»: ادمین ورودی خاص حق دارد محتوای
# سراسری (intake='') را فقط‌خواندنی باز کند (§۲۲ spec: Global = هسته‌ی
# پایه، read-only برای scoped)؛ mutationها در همان map قبلی می‌مانند.
ITEM_VIEW_ACTIONS = {'lesson', 'session', 'ref_subject', 'ref_book'}


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
    except Exception:
        pass
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
    await _deny_scope(query, uid)
    return False


def _back_btn(label, cb):
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=cb)]])


# ══════════════════════════════════════════════════════════
#  Callback اصلی
# ══════════════════════════════════════════════════════════

async def _audit(context, uid, action, *, severity='INFO', details='',
                 target_id='', target_type='', target_label='', tags=None):
    """🧹 موج Q2/W6 — helper مشترک audit پنل محتوا (حذف ۱۲ بلوک تکراری).
    فرمت/رفتار لاگ عیناً حفظ شده؛ خطای audit هرگز اقدام اصلی را نمی‌شکند."""
    try:
        from utils import send_audit_log
        actor = await db.get_user(uid)
        actor_name = actor.get('name', 'ادمین محتوا') if actor else 'ادمین محتوا'
        await send_audit_log(
            context.bot, 'content', actor_name, uid, action,
            module='Content', severity=severity,
            actor_role=await db.get_actor_role_label(uid),
            target_id=target_id, target_type=target_type, target_label=target_label,
            details=details, tags=tags)
    except Exception:
        pass


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
    except Exception:
        pass
    await query.answer("⭐ نسخه‌ی اختصاصی ساخته شد — حالا قابل ویرایش است")
    _ls = await db.bs_get_session(base_id)
    await _show_sessions(query, context, (_ls or {}).get('lesson_id', ''))
    return ConversationHandler.END


async def _h_unfork_session(query, context, uid: int, _cscope, is_scoped: bool, parts: list):
    """شاخه‌ی unfork_session — بازگردانی جلسه‌ی فورک‌شده به سراسری."""
    fork_id = parts[2]
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
    except Exception:
        pass
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
    except Exception:
        pass
    await query.answer("⭐ نسخه‌ی اختصاصی کتاب ساخته شد")
    _bk = await db.ref_get_book(base_bid)
    await _show_ref_books(query, context, (_bk or {}).get('subject_id', ''))
    return ConversationHandler.END


async def _h_unfork_book(query, context, uid: int, _cscope, is_scoped: bool, parts: list):
    """شاخه‌ی unfork_book — بازگردانی کتاب فورک‌شده به سراسری."""
    fork_bid = parts[2]
    _fi = await db.ref_book_intake(fork_bid)
    if not await db.can_access_intake(uid, _fi):
        await _deny_scope(query, uid)
        return ConversationHandler.END
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
    except Exception:
        pass
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

    # 🌊 C1.5 — دکمه‌ی 🔒/جداکننده‌ی فقط‌خواندنی (بدون عملکرد نوشتاری)
    elif action == 'ro_info':
        await query.answer(
            "🔒 محتوای سراسری — فقط‌خواندنی؛ "
            "مدیریت آن نزد 🎓 ادمین ارشد محتواست.",
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
                 'upload_ref_volume_prompt','upload_content',
                 'edit_lesson_prompt','edit_session_prompt',
                 'edit_ref_subject_prompt','edit_ref_book_prompt')
    if action not in KEEP_MODE:
        _clear(context)

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
        await _show_terms(query, back=back_main)

    elif action == 'term':
        idx = int(parts[2])
        context.user_data.update({'ca_term': TERMS[idx], 'ca_term_idx': idx})
        fa  = context.user_data.get('ca_from_admin', False)
        await _show_lessons(query, context, TERMS[idx],
                            back='ca:terms_admin' if fa else 'ca:terms')

    # ─ افزودن درس ─
    elif action == 'add_lesson_prompt':
        idx  = int(parts[2]); term = TERMS[idx]
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
        await db.reorder_up('bs_lessons', lid,
            {'term': TERMS[idx], 'intake': context.user_data.get('ca_intake', '')})
        fa = context.user_data.get('ca_from_admin', False)
        await _show_lessons(query, context, TERMS[idx],
                            back='ca:terms_admin' if fa else 'ca:terms')

    elif action == 'lesson_down':
        lid = parts[2]; idx = context.user_data.get('ca_term_idx', 0)
        await db.reorder_down('bs_lessons', lid,
            {'term': TERMS[idx], 'intake': context.user_data.get('ca_intake', '')})
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
        await query.edit_message_text(
            f"⚠️ <b>حذف درس «{lesson['name']}»؟</b>\nتمام جلسات و محتوا حذف می‌شود!",
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
        sessions = await db.bs_get_sessions(lid); next_n = len(sessions) + 1
        lesson   = await db.bs_get_lesson(lid)
        await query.edit_message_text(
            f"➕ <b>جلسه جدید — {lesson.get('name','') if lesson else ''}</b>\n\n"
            f"فرمت: <code>شماره, موضوع, استاد</code>\n"
            f"مثال: <code>{next_n}, فیزیولوژی کلیه, دکتر احمدی</code>\n"
            f"<i>شماره پیشنهادی: {next_n} — استاد اختیاری</i>\n\n⌨️ /cancel",
            parse_mode='HTML', reply_markup=_back_btn("❌ لغو", f'ca:lesson:{lid}'))

    elif action == 'edit_session_menu':
        sid = parts[2]; session = await db.bs_get_session(sid)
        if not session: return
        kb = [
            [InlineKeyboardButton("✏️ موضوع",      callback_data=f'ca:edit_session_prompt:{sid}:topic')],
            [InlineKeyboardButton("✏️ نام استاد",  callback_data=f'ca:edit_session_prompt:{sid}:teacher')],
            [InlineKeyboardButton("✏️ شماره جلسه", callback_data=f'ca:edit_session_prompt:{sid}:number')],
            [InlineKeyboardButton("🔙 بازگشت",     callback_data=f'ca:session:{sid}')],
        ]
        await query.edit_message_text(
            f"✏️ <b>ویرایش جلسه {session.get('number','')} — {session.get('topic','')}</b>",
            parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))

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
        await query.edit_message_text(
            f"⚠️ <b>حذف جلسه {session.get('number','')} — {session.get('topic','')}؟</b>",
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
        return await _h_fork_session(query, context, uid, _cscope, is_scoped, parts)
    elif action == 'unfork_session':
        return await _h_unfork_session(query, context, uid, _cscope, is_scoped, parts)
    elif action == 'upload_content':
        sid = parts[2]; context.user_data['ca_session_id'] = sid
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
        cid = parts[2]; sid = context.user_data.get('ca_session_id','')
        await db.reorder_content_up(cid, sid)
        await _show_session_content(query, context, sid)

    elif action == 'content_down':
        cid = parts[2]; sid = context.user_data.get('ca_session_id','')
        await db.reorder_content_down(cid, sid)
        await _show_session_content(query, context, sid)

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
        cid = parts[2]
        # FIX طبق سند: حذف منابع/جزوات قبلاً اصلاً لاگ نمی‌شد
        item_before = await db.bs_get_content_item(cid)
        await db.bs_delete_content(cid)
        sid = context.user_data.get('ca_session_id','')
        if item_before:
            type_fa = dict(CONTENT_TYPES).get(item_before.get('type', ''), 'فایل')
            await _audit(context, uid, f"حذف {type_fa}",
                severity='HIGH',
                target_id=cid,
                target_type='content',
                target_label=item_before.get('description', '')[:60] or type_fa,
                tags=['حذف_محتوا'])
        await query.edit_message_text("✅ محتوا حذف شد.",
            reply_markup=_back_btn("🔙 بازگشت", f'ca:session:{sid}'))

    # ══════════ رفرنس‌ها ══════════

    elif action in ('refs','refs_admin'):
        context.user_data['ca_ref_from_admin'] = from_admin
        await _show_ref_subjects(query, back=back_main, context=context)

    # ─ ترتیب درس‌های رفرنس ─
    elif action == 'ref_subject_up':
        sid = parts[2]
        await db.reorder_up('ref_subjects', sid,
            {'intake': context.user_data.get('ca_intake', '')})
        fa = context.user_data.get('ca_ref_from_admin', False)
        back = 'ca:refs_admin' if fa else 'ca:refs'
        await _show_ref_subjects(query, back=back, context=context)

    elif action == 'ref_subject_down':
        sid = parts[2]
        await db.reorder_down('ref_subjects', sid,
            {'intake': context.user_data.get('ca_intake', '')})
        fa = context.user_data.get('ca_ref_from_admin', False)
        back = 'ca:refs_admin' if fa else 'ca:refs'
        await _show_ref_subjects(query, back=back, context=context)

    elif action == 'add_ref_subject_prompt':
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
        sid = parts[2]; await db.ref_delete_subject(sid)
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
        await db.reorder_up('ref_books', bid, {'subject_id': sid})
        fa = context.user_data.get('ca_ref_from_admin', False)
        back = 'ca:refs_admin' if fa else 'ca:refs'
        await _show_ref_books(query, context, sid, back=back)

    elif action == 'ref_book_down':
        bid = parts[2]; sid = context.user_data.get('ca_ref_subject_id','')
        await db.reorder_down('ref_books', bid, {'subject_id': sid})
        fa = context.user_data.get('ca_ref_from_admin', False)
        back = 'ca:refs_admin' if fa else 'ca:refs'
        await _show_ref_books(query, context, sid, back=back)

    elif action == 'add_ref_book_prompt':
        sid = parts[2]
        context.user_data.update({'ca_ref_subject_id': sid, 'ca_mode': 'add_ref_book'})
        await query.edit_message_text(
            "➕ <b>کتاب جدید</b>\n\nنام کتاب را بنویسید:\n⌨️ /cancel",
            parse_mode='HTML', reply_markup=_back_btn("❌ لغو", f'ca:ref_subject:{sid}'))

    elif action == 'edit_ref_book_prompt':
        bid = parts[2]; book = await db.ref_get_book(bid)
        if not book: return
        context.user_data.update({'ca_mode':'edit_ref_book','ca_edit_target':bid})
        await query.edit_message_text(
            f"✏️ <b>ویرایش نام کتاب</b>\n\nفعلی: <b>{book['name']}</b>\n\nجدید:\n⌨️ /cancel",
            parse_mode='HTML', reply_markup=_back_btn("❌ لغو", f'ca:ref_book:{bid}'))

    elif action == 'del_ref_book':
        bid = parts[2]; book = await db.ref_get_book(bid)
        if not book: return
        sid = context.user_data.get('ca_ref_subject_id','')
        await query.edit_message_text(
            f"⚠️ <b>حذف رفرنس «{book['name']}»؟</b>",
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
        await db.ref_delete_book(bid)
        sid = context.user_data.get('ca_ref_subject_id','')
        await query.edit_message_text("✅ رفرنس حذف شد.",
            reply_markup=_back_btn("🔙 بازگشت", f'ca:ref_subject:{sid}'))

    elif action == 'ref_book':
        bid = parts[2]; context.user_data['ca_ref_book_id'] = bid
        await _show_ref_book_files(query, context, bid)

    # ── 🍴 موج C2 — سفارشی‌سازی کتاب سراسری برای یک ورودی ──
    elif action == 'fork_book':
        return await _h_fork_book(query, context, uid, _cscope, is_scoped, parts)
    elif action == 'unfork_book':
        return await _h_unfork_book(query, context, uid, _cscope, is_scoped, parts)
    elif action == 'upload_ref_volume_prompt':
        bid  = parts[2]; lang = parts[3]
        files = await db.ref_get_files(bid)
        existing_vols = [f.get('volume', 1) for f in files if f.get('lang') == lang]
        next_vol = max(existing_vols, default=0) + 1
        ll = "🇮🇷 فارسی" if lang == 'fa' else "🌐 لاتین"
        context.user_data.update({
            'ca_ref_book_id': bid,
            'ca_ref_lang':    lang,
            'ca_ref_volume':  next_vol,
            'ca_mode':        'waiting_ref_file',
        })
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
        context.user_data.update({
            'ca_ref_book_id': bid,
            'ca_ref_lang':    lang,
            'ca_ref_volume':  vol,
            'ca_mode':        'waiting_ref_file',
        })
        await query.edit_message_text(
            f"🔄 <b>جایگزین {ll} جلد {vol}</b>\n\nفایل جدید ارسال کنید:\n⌨️ /cancel",
            parse_mode='HTML', reply_markup=_back_btn("❌ لغو", f'ca:ref_book:{bid}'))

    elif action == 'del_ref_file':
        fid = parts[2]; await db.ref_delete_file(fid)
        bid = context.user_data.get('ca_ref_book_id','')
        await query.edit_message_text("✅ فایل حذف شد.",
            reply_markup=_back_btn("🔙 بازگشت", f'ca:ref_book:{bid}'))

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

    elif action == 'del_faq':
        await db.faq_delete(parts[2]); await _show_faq(query)

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

    from utils import now_tehran
    now = now_tehran().strftime('%H:%M — %Y/%m/%d')

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

async def _show_terms(query, back='ca:main'):
    kb = []
    for i in range(0, len(TERMS), 2):
        row = [InlineKeyboardButton(f"📘 {TERMS[i]}", callback_data=f'ca:term:{i}')]
        if i+1 < len(TERMS):
            row.append(InlineKeyboardButton(f"📘 {TERMS[i+1]}", callback_data=f'ca:term:{i+1}'))
        kb.append(row)
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data=back)])
    await query.edit_message_text("📘 <b>انتخاب ترم — علوم پایه</b>",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))


async def _show_lessons(query, context, term, back='ca:terms'):
    # 🌊 C1 — لیست درس‌ها فقط در scope انتخاب‌شده/قفل‌شده
    # 🌊 C1.5 — ادمین ورودی خاص: درس‌های سراسری هم «فقط‌خواندنی» دیده
    # می‌شوند (گروه‌بندی: اول ورودی من، بعد 🌐 سراسری با 🔒)
    uid     = query.from_user.id
    _cscope = await db.get_content_scope(uid)
    is_scoped = bool(_cscope and _cscope.get('kind') == 'scoped')
    ctx     = context.user_data.get('ca_intake', '')
    lessons = await db.bs_get_lessons(
        term, intake=[ctx, ''] if is_scoped else ctx)
    idx     = context.user_data.get('ca_term_idx', 0)
    kb = []

    if is_scoped:
        own_items  = [l for l in lessons if (l.get('intake') or '') == ctx]
        glob_items = [l for l in lessons if (l.get('intake') or '') != ctx]
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

    if glob_items:
        kb.append([InlineKeyboardButton(
            "── 🌐 منابع سراسری (🔒 فقط‌خواندنی) ──",
            callback_data='ca:ro_info')])
        for l in glob_items:
            lid = str(l['_id'])
            t   = f" | {l['teacher']}" if l.get('teacher') else ''
            kb.append([InlineKeyboardButton(
                f"🌐 {l['name']}{t}", callback_data=f'ca:lesson:{lid}')])

    kb.append([InlineKeyboardButton("➕ درس جدید", callback_data=f'ca:add_lesson_prompt:{idx}')])
    kb.append([InlineKeyboardButton("🔙 بازگشت",   callback_data=back)])
    ro_line = ("\n🔒 🌐=سراسری — فقط‌خواندنی (مدیریت: 🎓 ادمین ارشد)"
               if glob_items else '')
    await query.edit_message_text(
        f"📘 <b>{term}</b> — {len(lessons)} درس\n"
        f"<i>✏️=ویرایش  🗑=حذف  ⬆️⬇️=ترتیب</i>{ro_line}",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))


async def _show_sessions(query, context, lid):
    lesson   = await db.bs_get_lesson(lid)
    sessions = await db.bs_get_sessions(lid)
    idx      = context.user_data.get('ca_term_idx', 0)
    uid      = query.from_user.id
    # 🌊 C1.5 — درس سراسری برای ادمین ورودی خاص: فقط‌خواندنی
    writable = await db.can_access_intake(
        uid, (lesson or {}).get('intake') or '')
    # 🍴 C2 — نمای مؤثر برای scoped روی درس سراسری: fork خودش جایگزین base
    _cscope    = await db.get_content_scope(uid)
    is_scoped  = bool(_cscope and _cscope.get('kind') == 'scoped')
    ctx        = context.user_data.get('ca_intake', '')
    if not writable and is_scoped:
        sessions = await db.bs_get_sessions_effective(lid, [ctx, ''])
    kb = []
    for s in sessions:
        sid = str(s['_id'])
        is_fork  = bool(s.get('fork_of'))
        own_fork = is_scoped and is_fork and (s.get('intake') or '') == ctx
        if writable:
            badge = ''
            if is_fork:  # ادمین ارشد: forkهای هر ورودی با نشان دیده می‌شوند
                badge = f" ⭐({await _intake_label(s.get('intake') or '')})"
            kb.append([
                InlineKeyboardButton(
                    f"📌 {s['number']} — {s.get('topic','')[:20]}{badge}",
                    callback_data=f'ca:session:{sid}'),
                InlineKeyboardButton("✏️", callback_data=f'ca:edit_session_menu:{sid}'),
                InlineKeyboardButton("🗑",  callback_data=f'ca:del_session:{sid}'),
            ])
        elif own_fork:
            kb.append([
                InlineKeyboardButton(
                    f"⭐ {s['number']} — {s.get('topic','')[:20]} (نسخه‌ی من)",
                    callback_data=f'ca:session:{sid}'),
                InlineKeyboardButton("↩️", callback_data=f'ca:unfork_session:{sid}'),
            ])
        else:
            row = [InlineKeyboardButton(
                f"🌐 {s['number']} — {s.get('topic','')[:20]}",
                callback_data=f'ca:session:{sid}')]
            if is_scoped:
                row.append(InlineKeyboardButton(
                    "✂️", callback_data=f'ca:fork_session:{sid}'))
            kb.append(row)
    if writable:
        kb.append([InlineKeyboardButton("➕ جلسه جدید", callback_data=f'ca:add_session_prompt:{lid}')])
    kb.append([InlineKeyboardButton("🔙 بازگشت",    callback_data=f'ca:term:{idx}')])
    lname = lesson.get('name','') if lesson else ''
    if writable:
        ro_line = "<i>✏️=ویرایش  🗑=حذف  ⭐=نسخه‌ی اختصاصی ورودی</i>"
    elif is_scoped:
        ro_line = ("🔒 🌐 سراسری — فقط‌خواندنی\n"
                   "<i>✂️=سفارشی‌سازی برای ورودی من  ⭐=نسخه‌ی من  ↩️=حذف نسخه</i>")
    else:
        ro_line = "🔒 🌐 سراسری — فقط‌خواندنی"
    await query.edit_message_text(
        f"📖 <b>{lname}</b> — {len(sessions)} جلسه\n{ro_line}",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))


async def _show_session_content(query, context, sid):
    session  = await db.bs_get_session(sid)
    contents = await db.bs_get_content(sid)
    lid      = context.user_data.get('ca_lesson_id','')
    ICONS    = dict(CONTENT_TYPES)
    # 🌊 C1.5 — جلسه‌ی سراسری برای ادمین ورودی خاص: فقط‌خواندنی
    writable = await db.can_access_intake(
        query.from_user.id, await db.session_intake(sid))
    kb = []
    for i, c in enumerate(contents):
        cid  = str(c['_id'])
        ctype = c.get('type','pdf')
        desc  = c.get('description','')[:18] or f'فایل {i+1}'
        if writable:
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

    if writable:
        if not contents:
            kb.append([InlineKeyboardButton("📤 آپلود اولین فایل", callback_data=f'ca:upload_content:{sid}')])
        else:
            kb.append([InlineKeyboardButton("📤 ➕ افزودن فایل جدید", callback_data=f'ca:upload_content:{sid}')])
        kb.append([InlineKeyboardButton("✏️ ویرایش اطلاعات جلسه", callback_data=f'ca:edit_session_menu:{sid}')])
    elif not (session or {}).get('fork_of'):
        # 🍴 C2 — روی جلسه‌ی سراسری: ادمین ورودی خاص می‌تواند سفارشی کند
        _cs2 = await db.get_content_scope(query.from_user.id)
        if _cs2 and _cs2.get('kind') == 'scoped':
            _ctx2 = context.user_data.get('ca_intake', '')
            _fk2 = await db.session_superseded_by_fork(sid, _ctx2)
            if _fk2:
                kb.append([InlineKeyboardButton(
                    "⭐ ویرایش نسخه‌ی اختصاصی من",
                    callback_data=f'ca:session:{str(_fk2["_id"])}')])
            else:
                kb.append([InlineKeyboardButton(
                    "✂️ سفارشی‌سازی این جلسه برای ورودی من",
                    callback_data=f'ca:fork_session:{sid}')])
    kb.append([InlineKeyboardButton("🔙 بازگشت",              callback_data=f'ca:lesson:{lid}')])

    by_type = {}
    for c in contents:
        by_type.setdefault(c.get('type','pdf'), []).append(c)
    summary = '  '.join(f"{ICONS.get(t,'📎')}×{len(v)}" for t,v in by_type.items()) if by_type else '❌ بدون فایل'

    if session:
        footer = "<i>⬆️⬇️=ترتیب  🗑=حذف</i>" if writable \
            else "🔒 🌐 سراسری — فقط‌خواندنی"
        header = (f"📌 <b>جلسه {session.get('number','')}</b>\n"
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
        intake=[intake, ''] if is_scoped else intake)
    if is_scoped:
        own_items  = [s for s in subjects if (s.get('intake') or '') == intake]
        glob_items = [s for s in subjects if (s.get('intake') or '') != intake]
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
    if glob_items:
        kb.append([InlineKeyboardButton(
            "── 🌐 منابع سراسری (🔒 فقط‌خواندنی) ──",
            callback_data='ca:ro_info')])
        for s in glob_items:
            kb.append([InlineKeyboardButton(
                f"🌐 {s['name']}",
                callback_data=f'ca:ref_subject:{str(s["_id"])}')])
    kb.append([InlineKeyboardButton("➕ درس جدید", callback_data='ca:add_ref_subject_prompt')])
    kb.append([InlineKeyboardButton("🔙 بازگشت",   callback_data=back)])
    ro_line = ("\n🔒 🌐=سراسری — فقط‌خواندنی (مدیریت: 🎓 ادمین ارشد)"
               if glob_items else '')
    await query.edit_message_text(
        f"📚 <b>رفرنس‌ها</b> — {len(subjects)} درس\n<i>✏️=ویرایش  🗑=حذف  ⬆️⬇️=ترتیب</i>{ro_line}",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))


async def _show_ref_books(query, context, sid, back='ca:refs'):
    subj  = await db.ref_get_subject(sid)
    books = await db.ref_get_books(sid)
    uid   = query.from_user.id
    # 🌊 C1.5 — موضوع سراسری برای ادمین ورودی خاص: فقط‌خواندنی
    writable = await db.can_access_intake(
        uid, (subj or {}).get('intake') or '')
    # 🍴 C2 — نمای مؤثر برای scoped روی موضوع سراسری: fork جایگزین base
    _cscope   = await db.get_content_scope(uid)
    is_scoped = bool(_cscope and _cscope.get('kind') == 'scoped')
    ctx       = context.user_data.get('ca_intake', '')
    if not writable and is_scoped:
        books = await db.ref_get_books_effective(sid, [ctx, ''])
    kb = []
    for i, b in enumerate(books):
        bid = str(b['_id'])
        is_fork  = bool(b.get('fork_of'))
        own_fork = is_scoped and is_fork and (b.get('intake') or '') == ctx
        if writable:
            badge = ''
            if is_fork:
                badge = f" ⭐({await _intake_label(b.get('intake') or '')})"
            kb.append([
                InlineKeyboardButton(f"📘 {b['name']}{badge}", callback_data=f'ca:ref_book:{bid}'),
                InlineKeyboardButton("✏️", callback_data=f'ca:edit_ref_book_prompt:{bid}'),
                InlineKeyboardButton("🗑",  callback_data=f'ca:del_ref_book:{bid}'),
            ])
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
        else:
            row = [InlineKeyboardButton(
                f"🌐 {b['name']}", callback_data=f'ca:ref_book:{bid}')]
            if is_scoped:
                row.append(InlineKeyboardButton(
                    "✂️", callback_data=f'ca:fork_book:{bid}'))
            kb.append(row)
    if writable:
        kb.append([InlineKeyboardButton("➕ کتاب جدید", callback_data=f'ca:add_ref_book_prompt:{sid}')])
    kb.append([InlineKeyboardButton("🔙 بازگشت",    callback_data=back)])
    name = subj.get('name','') if subj else ''
    if writable:
        ro_line = "<i>✏️=ویرایش  🗑=حذف  ⬆️⬇️=ترتیب  ⭐=نسخه‌ی اختصاصی ورودی</i>"
    elif is_scoped:
        ro_line = ("🔒 🌐 سراسری — فقط‌خواندنی\n"
                   "<i>✂️=سفارشی‌سازی برای ورودی من  ⭐=نسخه‌ی من  ↩️=حذف نسخه</i>")
    else:
        ro_line = "🔒 🌐 سراسری — فقط‌خواندنی"
    await query.edit_message_text(
        f"📖 <b>{name}</b> — {len(books)} رفرنس\n{ro_line}",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))


async def _show_ref_book_files(query, context, bid):
    book    = await db.ref_get_book(bid)
    files   = await db.ref_get_files(bid)
    sid     = context.user_data.get('ca_ref_subject_id','')
    # 🌊 C1.5 — کتاب سراسری برای ادمین ورودی خاص: فقط‌خواندنی
    writable = await db.can_access_intake(
        query.from_user.id, await db.ref_book_intake(bid))
    kb      = []

    # گروه‌بندی بر اساس زبان
    fa_files = sorted([f for f in files if f.get('lang') == 'fa'], key=lambda x: x.get('volume',1))
    en_files = sorted([f for f in files if f.get('lang') == 'en'], key=lambda x: x.get('volume',1))

    for lang, items, label_prefix in [('fa', fa_files, '🇮🇷 فارسی'), ('en', en_files, '🌐 لاتین')]:
        for f in items:
            fid = str(f['_id']); vol = f.get('volume',1); dl = f.get('downloads',0)
            desc = f.get('description','')
            row_label = f"✅ {label_prefix} جلد {vol}" + (f" — {desc[:15]}" if desc else '') + f"  ⬇️{dl}"
            if writable:
                kb.append([
                    InlineKeyboardButton(row_label, callback_data=f'ca:ref_book:{bid}'),
                    InlineKeyboardButton("🔄", callback_data=f'ca:upload_ref:{bid}:{lang}:{vol}'),
                    InlineKeyboardButton("🗑", callback_data=f'ca:del_ref_file:{fid}'),
                ])
            else:
                kb.append([InlineKeyboardButton(
                    row_label, callback_data=f'ca:ref_book:{bid}')])
        # دکمه افزودن جلد جدید
        if writable:
            kb.append([InlineKeyboardButton(
                f"📤 ➕ جلد جدید {label_prefix}",
                callback_data=f'ca:upload_ref_volume_prompt:{bid}:{lang}'
            )])

    if writable:
        kb.append([InlineKeyboardButton("✏️ ویرایش نام کتاب", callback_data=f'ca:edit_ref_book_prompt:{bid}')])
    elif not (book or {}).get('fork_of'):
        # 🍴 C2 — روی کتاب سراسری: ادمین ورودی خاص می‌تواند سفارشی کند
        _cs3 = await db.get_content_scope(query.from_user.id)
        if _cs3 and _cs3.get('kind') == 'scoped':
            _ctx3 = context.user_data.get('ca_intake', '')
            _fk3 = await db.book_superseded_by_fork(bid, _ctx3)
            if _fk3:
                kb.append([InlineKeyboardButton(
                    "⭐ ویرایش نسخه‌ی اختصاصی من",
                    callback_data=f'ca:ref_book:{str(_fk3["_id"])}')])
            else:
                kb.append([InlineKeyboardButton(
                    "✂️ سفارشی‌سازی این کتاب برای ورودی من",
                    callback_data=f'ca:fork_book:{bid}')])
    kb.append([InlineKeyboardButton("🔙 بازگشت",           callback_data=f'ca:ref_subject:{sid}')])
    name = book.get('name','') if book else ''
    footer = "🔄=جایگزین  🗑=حذف  ➕=جلد جدید" if writable \
        else "🔒 🌐 سراسری — فقط‌خواندنی"
    await query.edit_message_text(
        f"📘 <b>{name}</b>\n"
        f"📁 {len(files)} فایل\n\n"
        f"{footer}",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))


async def _show_faq(query, back='ca:main'):
    faqs = await db.faq_get_all()
    kb   = []
    for f in faqs[:15]:
        fid = str(f['_id'])
        kb.append([
            InlineKeyboardButton(f"❓ {f.get('question','')[:30]}", callback_data='ca:faq'),
            InlineKeyboardButton("🗑", callback_data=f'ca:del_faq:{fid}'),
        ])
    kb.append([InlineKeyboardButton("➕ سوال جدید", callback_data='ca:add_faq_prompt')])
    kb.append([InlineKeyboardButton("🔙 بازگشت",   callback_data=back)])
    await query.edit_message_text(
        f"❓ <b>سوالات متداول</b> — {len(faqs)} سوال",
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

    file_obj = (update.message.document or update.message.video or
                update.message.audio    or update.message.voice)
    if not file_obj:
        await update.message.reply_text("❌ فایل معتبر ارسال کنید.\n⌨️ /cancel")
        return CA_WAITING_FILE

    fid = file_obj.file_id

    if ca_mode == 'waiting_ref_file':
        bid  = context.user_data.get('ca_ref_book_id','')
        lang = context.user_data.get('ca_ref_lang','fa')
        vol  = context.user_data.get('ca_ref_volume', 1)
        ll   = "🇮🇷 فارسی" if lang == 'fa' else "🌐 لاتین"
        # بپرس توضیح اضافه بخواد بده
        context.user_data.update({'ca_pending_file': fid, 'ca_mode': 'waiting_ref_description'})
        await update.message.reply_text(
            f"✅ فایل {ll} جلد {vol} دریافت شد!\n\n"
            "📝 توضیح اختیاری (مثلاً: ویرایش سوم):\n"
            "اگر توضیحی ندارید <code>-</code> بزنید:\n⌨️ /cancel",
            parse_mode='HTML',
            reply_markup=_back_btn("❌ لغو (بدون توضیح)", f'ca:ref_book:{bid}'))
        return CA_WAITING_TEXT

    # فایل محتوای جلسه
    context.user_data.update({'ca_pending_file': fid, 'ca_mode': 'waiting_description'})
    sid = context.user_data.get('ca_session_id','')
    await update.message.reply_text(
        "✅ فایل دریافت شد!\n\n"
        "📝 توضیح اختیاری برای این فایل:\n"
        "(مثلاً: ویدیو قسمت اول — فیزیولوژی کلیه)\n"
        "اگر توضیحی ندارید <code>-</code> بزنید:\n⌨️ /cancel",
        parse_mode='HTML',
        reply_markup=_back_btn("❌ لغو", f'ca:session:{sid}'))
    return CA_WAITING_TEXT


# ══════════════════════════════════════════════════════════
#  هندلر متن
# ══════════════════════════════════════════════════════════

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
        'waiting_description', 'waiting_ref_description',
        'add_faq', 'add_ref_subject', 'add_ref_book',
        'edit_ref_subject', 'edit_ref_book',
    }
    if ca_mode not in VALID_CA_MODES:
        from message_router import route_message
        return await route_message(update, context)

    if ca_mode == 'add_lesson':
        ps = [p.strip() for p in text.split(',')]
        name = ps[0]; teacher = ps[1] if len(ps) > 1 else ''
        term = context.user_data.get('ca_term',''); idx = context.user_data.get('ca_term_idx',0)
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
        if not await db.can_access_intake(uid, await db.lesson_intake(lid)):
            _clear(context)
            await update.message.reply_text("⛔ دسترسی غیرمجاز — این درس در scope شما نیست.")
            return ConversationHandler.END
        if len(ps) < 2:
            await update.message.reply_text(
                "❌ فرمت اشتباه!\nمثال: <code>3, فیزیولوژی کلیه, دکتر احمدی</code>\n⌨️ /cancel",
                parse_mode='HTML', reply_markup=_back_btn("❌ لغو", f'ca:lesson:{lid}'))
            return CA_WAITING_TEXT
        try:    number = int(ps[0])
        except:
            sessions = await db.bs_get_sessions(lid); number = len(sessions) + 1
        topic = ps[1]; teacher = ps[2] if len(ps) > 2 else ''
        await db.bs_add_session(lid, number, topic, teacher)
        _clear(context)
        await _audit(context, uid, "ایجاد جلسه جدید",
            severity='INFO',
            target_type='session',
            target_label=f"جلسه {number} — {topic}",
            tags=['ایجاد_جلسه'])
        await update.message.reply_text(f"✅ جلسه {number} — «{topic}» اضافه شد!",
            reply_markup=_back_btn("🔙 برگشت", f'ca:lesson:{lid}'))

    elif ca_mode == 'edit_session':
        sid = context.user_data.get('ca_edit_target',''); field = context.user_data.get('ca_edit_field','')
        if not await db.can_access_intake(uid, await db.session_intake(sid)):
            _clear(context)
            await update.message.reply_text("⛔ دسترسی غیرمجاز — این جلسه در scope شما نیست.")
            return ConversationHandler.END
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
        await update.message.reply_text("✅ جلسه ویرایش شد." if ok else "❌ خطا.",
            reply_markup=_back_btn("🔙 برگشت", f'ca:session:{sid}'))

    elif ca_mode == 'waiting_description':
        desc = '' if text == '-' else text
        fid  = context.user_data.get('ca_pending_file','')
        sid  = context.user_data.get('ca_session_id','')
        ct   = context.user_data.get('ca_content_type','pdf')
        if not await db.can_access_intake(uid, await db.session_intake(sid)):
            _clear(context)
            await update.message.reply_text("⛔ دسترسی غیرمجاز — این جلسه در scope شما نیست.")
            return ConversationHandler.END
        await db.bs_add_content(sid, ct, fid, description=desc)
        tl = dict(CONTENT_TYPES).get(ct, ct)
        _clear(context)
        await update.message.reply_text(f"✅ {tl} اضافه شد!",
            reply_markup=_back_btn("🔙 برگشت", f'ca:session:{sid}'))

    elif ca_mode == 'waiting_ref_description':
        desc  = '' if text == '-' else text
        fid   = context.user_data.get('ca_pending_file','')
        bid   = context.user_data.get('ca_ref_book_id','')
        lang  = context.user_data.get('ca_ref_lang','fa')
        vol   = context.user_data.get('ca_ref_volume', 1)
        if not await db.can_access_intake(uid, await db.ref_book_intake(bid)):
            _clear(context)
            await update.message.reply_text("⛔ دسترسی غیرمجاز — این رفرنس در scope شما نیست.")
            return ConversationHandler.END
        await db.ref_add_file(bid, lang, fid, volume=vol, description=desc)
        ll = "🇮🇷 فارسی" if lang == 'fa' else "🌐 لاتین"
        _clear(context)
        await update.message.reply_text(
            f"✅ {ll} جلد {vol} آپلود شد!" + (f"\n📝 {desc}" if desc else ''),
            reply_markup=_back_btn("🔙 برگشت", f'ca:ref_book:{bid}'))

    elif ca_mode == 'add_ref_subject':
        # 🌊 C1 — موضوع جدید در scope جاری context
        result = await db.ref_add_subject(text, intake=_ctx_intake)
        fa = context.user_data.get('ca_ref_from_admin', False)
        back = 'ca:refs_admin' if fa else 'ca:refs'
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
        ok  = await db.ref_update_subject(sid, {'name': text})
        _clear(context)
        await update.message.reply_text(f"✅ نام به «{text}» تغییر یافت." if ok else "❌ خطا.",
            reply_markup=_back_btn("🔙 برگشت", f'ca:ref_subject:{sid}'))

    elif ca_mode == 'add_ref_book':
        sid = context.user_data.get('ca_ref_subject_id','')
        if not await db.can_access_intake(uid, await db.ref_subject_intake(sid)):
            _clear(context)
            await update.message.reply_text("⛔ دسترسی غیرمجاز — این موضوع در scope شما نیست.")
            return ConversationHandler.END
        await db.ref_add_book(sid, text)
        _clear(context)
        await update.message.reply_text(f"✅ رفرنس «{text}» اضافه شد!",
            reply_markup=_back_btn("🔙 برگشت", f'ca:ref_subject:{sid}'))

    elif ca_mode == 'edit_ref_book':
        bid = context.user_data.get('ca_edit_target','')
        if not await db.can_access_intake(uid, await db.ref_book_intake(bid)):
            _clear(context)
            await update.message.reply_text("⛔ دسترسی غیرمجاز — این رفرنس در scope شما نیست.")
            return ConversationHandler.END
        ok  = await db.ref_update_book(bid, {'name': text})
        _clear(context)
        await update.message.reply_text(f"✅ نام کتاب به «{text}» تغییر یافت." if ok else "❌ خطا.",
            reply_markup=_back_btn("🔙 برگشت", f'ca:ref_book:{bid}'))

    elif ca_mode == 'add_faq':
        ps = [p.strip() for p in text.split('|')]
        if len(ps) < 2:
            await update.message.reply_text(
                "❌ فرمت اشتباه!\nمثال: <code>سوال | جواب | دسته</code>\n⌨️ /cancel",
                parse_mode='HTML'); return CA_WAITING_TEXT
        question = ps[0]; answer = ps[1]; category = ps[2] if len(ps) > 2 else 'عمومی'
        await db.faq_add(question, answer, category)
        _clear(context)
        await update.message.reply_text(f"✅ سوال اضافه شد!",
            reply_markup=_back_btn("🔙 برگشت", 'ca:faq'))

    else:
        _clear(context)
        await update.message.reply_text("⚠️ لطفاً از منوی ربات استفاده کنید.")
        return ConversationHandler.END
