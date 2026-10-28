"""
🚀 Start — ثبت‌نام و ورود کاربر
"""
import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import db
from utils import (
    main_keyboard, admin_keyboard, content_admin_keyboard, get_keyboard_for_user,
    esc as _esc,   # 🛡 P0-FIX: نامِ کاربر داخل parse_mode='HTML' باید escape شود
)

logger = logging.getLogger(__name__)

ADMIN_ID  = int(os.getenv('ADMIN_ID', '0'))
REGISTER        = 0
STEP_NAME       = 10
STEP_GROUP      = 12
STEP_INTAKE     = 13
STEP_STUDENT_ID = 14   # FIX: مرحله جدید — فقط وقتی require_student_id فعال است


# ══════════════════════════════════════════════════
#  /start
# ══════════════════════════════════════════════════

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid        = update.effective_user.id
    first_name = update.effective_user.first_name or ''
    user       = await db.get_user(uid)

    # ── کاربر جدید ──
    if not user:
        # FIX جدید: بلاک کامل — کاربرانی که با آیدی عددی‌شان بلاک شده‌اند
        # (نه فقط حذف) حتی اجازه‌ی دیدن دکمه‌ی «شروع ثبت‌نام» را ندارند.
        if await db.is_blacklisted(uid):
            context.user_data.clear()
            await update.message.reply_text(
                "🚫 <b>دسترسی مسدود است</b>\n\n"
                "حساب شما توسط مدیریت ربات مسدود شده و امکان ثبت‌نام مجدد وجود ندارد.\n"
                "در صورت اعتراض، از طریق راه‌های ارتباطی خارج از ربات با مدیریت در تماس باشید.",
                parse_mode='HTML'
            )
            return ConversationHandler.END

        context.user_data.clear()
        # 🌱 W13 — لینک دعوت (?start=ref_XXXX)؛ تا پایان ثبت‌نام نگه داشته می‌شود
        try:
            _sargs = getattr(context, 'args', None) or []
            if _sargs:
                import growth_rules as _gr
                _rcode = _gr.parse_ref_start_arg(_sargs[0])
                if _rcode:
                    context.user_data['pending_ref'] = _rcode
        except Exception:
            pass
        await update.message.reply_text(
            f"🩺 <b>به ربات آموزشی پزشکی خوش آمدید!</b>\n\n"
            f"سلام <b>{first_name}</b> عزیز 👋\n\n"
            "این ربات به شما کمک می‌کند:\n"
            "📚 منابع و جزوات درسی\n"
            "🧪 بانک سوال و تمرین هوشمند\n"
            "📅 برنامه کلاس‌ها و امتحانات\n"
            "🎫 پشتیبانی و پاسخ سریع\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "برای شروع، ابتدا ثبت‌نام کنید.\n"
            "فقط <b>۲ مرحله</b> ساده! 🚀",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ شروع ثبت‌نام", callback_data='register:start')
            ]])
        )
        return REGISTER

    # ── در انتظار تأیید ──
    if not user.get('approved') and uid != ADMIN_ID:
        await update.message.reply_text(
            "⏳ <b>در انتظار تأیید</b>\n\n"
            f"سلام <b>{user.get('name', '')}</b> عزیز،\n"
            "ثبت‌نام شما انجام شده و منتظر تأیید ادمین است.\n\n"
            "به زودی دسترسی شما فعال می‌شود. 🙏",
            parse_mode='HTML'
        )
        return ConversationHandler.END

    # FIX: کاربر تأییدشده، اما شماره دانشجویی ندارد و الان اجباری شده
    require_sid = await db.get_setting('require_student_id', False)
    if require_sid and not user.get('student_id') and uid != ADMIN_ID:
        context.user_data['reg_name']   = user.get('name', '')
        context.user_data['reg_group']  = user.get('group', '1')
        context.user_data['reg_intake'] = user.get('intake', '')
        context.user_data['completing_profile'] = True
        await update.message.reply_text(
            "🎓 <b>تکمیل ثبت‌نام لازم است</b>\n\n"
            "ادمین وارد کردن شماره دانشجویی را برای همه دانشجویان الزامی کرده است.\n\n"
            "لطفاً شماره دانشجویی خود را وارد کنید تا بتوانید از ربات استفاده کنید:",
            parse_mode='HTML'
        )
        return STEP_STUDENT_ID

    # ── کاربر تأییدشده ──
    kb = await get_keyboard_for_user(user, uid)   # FIX: حالا async است
    await update.message.reply_text(
        f"🩺 <b>خوش برگشتید {user.get('name', '')} عزیز!</b>",
        parse_mode='HTML',
        reply_markup=kb
    )
    # 🎙 م9 — دیپ‌لینک شروع تماس صوتی زنده از گروه (?start=ai_live)
    _sargs = getattr(context, 'args', None) or []
    if _sargs and str(_sargs[0]).strip().lower() in ('ai_live', 'live', 'voicechat'):
        from ai_solver import show_ai_live_card
        await show_ai_live_card(update, context)
        return ConversationHandler.END
    await _show_dashboard(update, context)
    return ConversationHandler.END


# ══════════════════════════════════════════════════
#  ثبت‌نام — Callbacks
# ══════════════════════════════════════════════════

async def register_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data  = query.data

    if data == 'register:start':
        uid = update.effective_user.id
        # FIX جدید: لایه‌ی دوم دفاعی — اگر کاربر بعد از دیدن دکمه‌ی
        # «شروع ثبت‌نام» و قبل از لمسش بلاک شده باشد.
        if await db.is_blacklisted(uid):
            context.user_data.clear()
            await query.edit_message_text(
                "🚫 حساب شما توسط مدیریت ربات مسدود شده و امکان ثبت‌نام ندارید."
            )
            return ConversationHandler.END
        context.user_data['reg_step'] = 'name'
        await query.edit_message_text(
            "📝 <b>مرحله ۱ از ۲ — نام و نام خانوادگی</b>\n\n"
            "👤 لطفاً نام کامل خود را بنویسید:\n\n"
            "<i>مثال: علی احمدی</i>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ انصراف", callback_data='register:cancel')
            ]])
        )
        return STEP_NAME

    elif data == 'register:cancel':
        # 🐞 P1-FIX — لغو باید وضعیت گفتگو را هم پاک کند؛ قبلاً reg_name /
        # reg_group / reg_edu_group در user_data می‌ماندند و ثبت‌نام بعدی
        # با داده‌های نیمه‌کارهٔ قبلی شروع می‌شد.
        context.user_data.clear()
        await query.edit_message_text(
            "❌ ثبت‌نام لغو شد.\n\nبرای شروع مجدد /start بزنید."
        )
        return ConversationHandler.END

    elif data == 'register:group1':
        return await _save_group(update, context, '1')

    elif data == 'register:group2':
        return await _save_group(update, context, '2')

    elif data in ('register:edugroup:male', 'register:edugroup:female'):
        edu_grp = 'male' if data.endswith(':male') else 'female'
        context.user_data['reg_edu_group'] = edu_grp
        group = context.user_data.get('reg_group', '1')
        return await _proceed_to_intake(update, context, group)

    return REGISTER


async def step_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if len(name) < 3:
        await update.message.reply_text("⚠️ نام باید حداقل ۳ حرف باشد. مجدد وارد کنید:")
        return STEP_NAME
    if len(name) > 50:
        await update.message.reply_text("⚠️ نام نباید بیشتر از ۵۰ حرف باشد:")
        return STEP_NAME

    context.user_data['reg_name'] = name

    await update.message.reply_text(
        f"✅ <b>نام ثبت شد:</b> {name}\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "📝 <b>مرحله ۲ از ۲ — انتخاب گروه درسی</b>\n\n"
        "👥 گروه خود را انتخاب کنید:",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("1️⃣ گروه ۱", callback_data='register:group1'),
                InlineKeyboardButton("2️⃣ گروه ۲", callback_data='register:group2'),
            ],
            [InlineKeyboardButton("❌ انصراف", callback_data='register:cancel')],
        ])
    )
    return STEP_GROUP


async def _save_group(update, context, group: str):
    query    = update.callback_query
    name     = context.user_data.get('reg_name', '')

    if not name:
        await query.edit_message_text("❌ خطا. لطفاً /start بزنید.")
        return ConversationHandler.END

    context.user_data['reg_group'] = group
    ai_sug = db.suggest_educational_group_from_name(name)
    sug_grp = ai_sug.get('ai_suggested_group', 'unknown')
    hint_line = ""
    if sug_grp == 'male':
        hint_line = "💡 <i>پیشنهاد هوشمند بر اساس نام شما: <b>کلاس‌های آقایان</b> (لطفاً تأیید یا اصلاح کنید)</i>\n\n"
    elif sug_grp == 'female':
        hint_line = "💡 <i>پیشنهاد هوشمند بر اساس نام شما: <b>کلاس‌های بانوان</b> (لطفاً تأیید یا اصلاح کنید)</i>\n\n"

    male_lbl = "✅ 👨 کلاس‌های آقایان" if sug_grp == 'male' else "👨 کلاس‌های آقایان"
    female_lbl = "✅ 👩 کلاس‌های بانوان" if sug_grp == 'female' else "👩 کلاس‌های بانوان"

    await query.edit_message_text(
        f"✅ <b>گروه {group} انتخاب شد</b>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "🎓 <b>تعیین گروه آموزشی کلاس‌ها</b>\n\n"
        f"{hint_line}"
        "برخی دروس دانشگاه به صورت تفکیک‌شده (ویژه آقایان یا ویژه بانوان) ارائه می‌شوند.\n"
        "لطفاً گروه آموزشی خود را برای نمایش دقیق برنامه کلاسی و انتخاب واحد مشخص کنید:",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(male_lbl, callback_data='register:edugroup:male'),
                InlineKeyboardButton(female_lbl, callback_data='register:edugroup:female'),
            ],
            [InlineKeyboardButton("❌ انصراف", callback_data='register:cancel')],
        ]),
    )
    return STEP_GROUP


async def _proceed_to_intake(update, context, group: str):
    query    = update.callback_query
    uid      = update.effective_user.id
    username = update.effective_user.username
    name     = context.user_data.get('reg_name', '')

    if not name:
        await query.edit_message_text("❌ خطا. لطفاً /start بزنید.")
        return ConversationHandler.END

    intakes = await db.get_active_intakes()
    if not intakes:
        return await _after_intake_step(update, context, uid, name, group, '', username, query=query)

    keyboard = [[InlineKeyboardButton(i['label'], callback_data=f'register:intake:{i["code"]}')]
                for i in intakes]
    keyboard.append([InlineKeyboardButton("❌ انصراف", callback_data='register:cancel')])
    edu_lbl = 'آقایان' if context.user_data.get('reg_edu_group') == 'male' else 'بانوان'
    await query.edit_message_text(
        f"✅ <b>گروه {group} ({edu_lbl}) انتخاب شد</b>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "📝 <b>مرحله ۳ — ورودی تحصیلی</b>\n\n"
        "📅 ورودی خود را انتخاب کنید:",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return STEP_INTAKE


async def _active_intake_codes() -> set:
    """کد ورودی‌های فعال — تنها منبع مجاز برای مقدارِ `intake`."""
    try:
        return {str(i.get('code') or '') for i in await db.get_active_intakes()}
    except Exception:
        logger.warning('خواندن ورودی‌های فعال ناموفق بود', exc_info=True)
        return set()


async def _reply_registration(update, context, text: str, query=None, reply_markup=None):
    """پاسخ به کاربر در هر دو حالت (کلیک دکمه = callback، یا پیام متنی).

    🐞 P0-FIX: `_finish_registration` قبلاً همیشه `update.callback_query` را
    فرض می‌کرد؛ در فلوی «شماره دانشجویی اجباری» پایانِ ثبت‌نام از یک
    MessageHandler می‌آید و `callback_query=None` است ⇒ AttributeError
    درست در آخرین قدم ثبت‌نام. این تابع هر دو مسیر را پوشش می‌دهد.
    """
    if query is not None:
        try:
            await query.edit_message_text(text, parse_mode='HTML', reply_markup=reply_markup)
            return
        except Exception:
            # پیام قابل ویرایش نبود (کهنه/حذف‌شده) ⇒ ارسال تازه
            logger.info('edit_message_text ناموفق بود؛ پیام تازه ارسال می‌شود', exc_info=True)
    msg = getattr(update, 'effective_message', None) or getattr(update, 'message', None)
    if msg is not None:
        await msg.reply_text(text, parse_mode='HTML', reply_markup=reply_markup)
    elif query is not None:
        await query.message.reply_text(text, parse_mode='HTML', reply_markup=reply_markup)


async def _already_registered_notice(update, context, uid: int, query=None) -> int:
    """کاربر از قبل ثبت‌نام کرده — پیام روشن، بدون ساخت رکورد دوم."""
    context.user_data.clear()
    user = await db.get_user(uid, use_cache=False) or {}
    if user.get('approved') or uid == ADMIN_ID:
        body = ("ℹ️ <b>شما قبلاً ثبت‌نام کرده‌اید.</b>\n\n"
                f"👤 نام: <b>{_esc(user.get('name', ''))}</b>\n\n"
                "برای دیدن داشبورد /start بزنید.")
    else:
        body = ("⏳ <b>ثبت‌نام شما قبلاً ثبت شده است.</b>\n\n"
                f"👤 نام: <b>{_esc(user.get('name', ''))}</b>\n\n"
                "درخواست شما در انتظار تأیید ادمین است؛ نیازی به ثبت‌نام دوباره نیست.")
    await _reply_registration(update, context, body, query=query)
    return ConversationHandler.END


async def _after_intake_step(update, context, uid, name, group, intake, username, query=None):
    """
    نقطه‌ی مشترک بعد از انتخاب ورودی — تصمیم می‌گیرد آیا مرحله‌ی
    شماره دانشجویی لازم است (require_student_id) یا مستقیم ثبت‌نام تکمیل شود.
    """
    # 🛡 P0-FIX — اعتبارسنجی `intake`: مقدار از callback_data می‌آید و
    # قبلاً بدون بررسی داخل سند کاربر نوشته می‌شد. فقط کدهای فعال مجازند
    # (دکمه‌ی کهنه/دستکاری‌شده نباید داده‌ی نامعتبر ثبت کند).
    codes = await _active_intake_codes()
    if intake and codes and intake not in codes:
        await _reply_registration(
            update, context,
            "⚠️ این ورودی دیگر فعال نیست. لطفاً /start بزنید و دوباره ثبت‌نام کنید.",
            query=query)
        context.user_data.clear()
        return ConversationHandler.END
    if not codes:
        intake = ''          # مثل مینی‌اپ/API: بدون ورودی فعال این مرحله حذف است
    elif not intake:
        # callback_data باید کد ورودی داشته باشد؛ نبودنش یعنی دکمهٔ قدیمی/خراب
        await _reply_registration(
            update, context,
            "⚠️ انتخاب ورودی نامعتبر بود. لطفاً /start بزنید و دوباره ثبت‌نام کنید.",
            query=query)
        context.user_data.clear()
        return ConversationHandler.END
    context.user_data['reg_intake'] = intake

    # 🛡 P0-FIX — ثبت‌نام تکراری: قبل از هر نوشتنی در دیتابیس
    try:
        if await db.get_user(uid, use_cache=False):
            return await _already_registered_notice(update, context, uid, query=query)
    except Exception:
        logger.warning('بررسی کاربر موجود ناموفق بود (ادامه می‌دهیم)', exc_info=True)

    require_sid = await db.get_setting('require_student_id', False)

    if require_sid:
        text = (
            "✅ <b>اطلاعات قبلی ثبت شد</b>\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "📝 <b>مرحله نهایی — شماره دانشجویی</b>\n\n"
            "🎓 لطفاً شماره دانشجویی خود را وارد کنید:\n"
            "<i>این فیلد برای تکمیل ثبت‌نام الزامی است.</i>"
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data='register:cancel')]])
        await _reply_registration(update, context, text, query=query, reply_markup=kb)
        return STEP_STUDENT_ID

    # FIX جدید: لایه‌ی دوم دفاعی در برابر بلاک — حتی اگر کاربری بین
    # نمایش دکمه‌ی «شروع ثبت‌نام» و رسیدن به همین نقطه بلاک شده باشد.
    if await db.is_blacklisted(uid):
        context.user_data.clear()
        await _reply_registration(
            update, context,
            "🚫 حساب شما توسط مدیریت مسدود شده و امکان ثبت‌نام ندارید.", query=query)
        return ConversationHandler.END

    edu_group = context.user_data.get('reg_edu_group', 'unknown')
    # قرارداد واحد: create_user خودش تأیید را از منبع/گروه استنتاج می‌کند
    res = await db.create_user(
        uid, name, '', group, username, intake=intake,
        educational_group=edu_group,
        group_source='user_confirmed' if edu_group in ('male', 'female') else 'ai_suggested',
        group_verified=(edu_group in ('male', 'female')),
    )
    if res and res.get('duplicate'):
        return await _already_registered_notice(update, context, uid, query=query)
    # 🌱 W13 — attribution دعوت (exception-safe؛ ثبت‌نام را نمی‌شکند)
    try:
        _pr = context.user_data.pop('pending_ref', None)
        if _pr:
            from referral import attribute as _ref_attribute
            await _ref_attribute(uid, _pr, 'bot')
    except Exception:
        pass
    return await _finish_registration(update, context, uid, name, group, intake, username, query=query)


async def step_student_id_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    گرفتن شماره دانشجویی — هم در فلوی ثبت‌نام تازه، هم برای کاربران
    قدیمی که باید پروفایلشان را تکمیل کنند (completing_profile).
    """
    sid = update.message.text.strip()
    if len(sid) < 5:
        await update.message.reply_text("⚠️ شماره دانشجویی باید حداقل ۵ کاراکتر باشد. دوباره وارد کنید:")
        return STEP_STUDENT_ID
    if len(sid) > 30:
        await update.message.reply_text("⚠️ شماره دانشجویی نامعتبر است. دوباره وارد کنید:")
        return STEP_STUDENT_ID

    uid      = update.effective_user.id
    username = update.effective_user.username
    name     = context.user_data.get('reg_name', '')
    group    = context.user_data.get('reg_group', '1')
    intake   = context.user_data.get('reg_intake', '')

    if context.user_data.get('completing_profile'):
        await db.update_user(uid, {'student_id': sid})
        context.user_data.pop('completing_profile', None)
        for k in ('reg_name', 'reg_group', 'reg_intake'):
            context.user_data.pop(k, None)
        user = await db.get_user(uid)
        kb   = await get_keyboard_for_user(user, uid)
        await update.message.reply_text(
            f"✅ <b>شماره دانشجویی ثبت شد!</b>\n\nخوش برگشتید <b>{name}</b> عزیز 🎉",
            parse_mode='HTML', reply_markup=kb
        )
        await _show_dashboard(update, context)
        return ConversationHandler.END

    # FIX جدید: لایه‌ی دوم دفاعی در برابر بلاک (نگاه کنید به _after_intake_step)
    if await db.is_blacklisted(uid):
        context.user_data.clear()
        await update.message.reply_text("🚫 حساب شما توسط مدیریت مسدود شده و امکان ثبت‌نام ندارید.")
        return ConversationHandler.END

    edu_group = context.user_data.get('reg_edu_group', 'unknown')
    res = await db.create_user(
        uid, name, sid, group, username, intake=intake,
        educational_group=edu_group,
        group_source='user_confirmed' if edu_group in ('male', 'female') else 'ai_suggested',
        group_verified=(edu_group in ('male', 'female')),
    )
    if res and res.get('duplicate'):
        return await _already_registered_notice(update, context, uid)
    # 🌱 W13 — attribution دعوت (exception-safe؛ ثبت‌نام را نمی‌شکند)
    try:
        _pr = context.user_data.pop('pending_ref', None)
        if _pr:
            from referral import attribute as _ref_attribute
            await _ref_attribute(uid, _pr, 'bot')
    except Exception:
        pass
    # این مسیر از MessageHandler می‌آید ⇒ callback_query وجود ندارد
    return await _finish_registration(update, context, uid, name, group, intake, username, query=None)


# ══════════════════════════════════════════════════
#  هندلر انتخاب ورودی در ثبت‌نام
# ══════════════════════════════════════════════════

async def register_intake_callback(update, context):
    """وقتی کاربر ورودی رو انتخاب کرد

    🛡 P0-FIX:
      • `query.data.split(':')[2]` روی دادهٔ ناقص (مثلاً «register:intake»)
        IndexError می‌داد و در پیوی ادمین «خطای ربات» می‌شد.
      • اگر نام/گروه از user_data رفته باشد (ری‌استارت ربات یا context
        پاک‌شده) ثبت‌نام نیمه‌کاره نباید ساخته شود.
    """
    query    = update.callback_query
    await query.answer()
    uid      = update.effective_user.id
    username = update.effective_user.username

    parts  = str(query.data or '').split(':')
    intake = parts[2].strip() if len(parts) > 2 else ''

    name  = context.user_data.get('reg_name', '')
    group = context.user_data.get('reg_group', '1')

    if not name:
        await _reply_registration(
            update, context,
            "⌛️ اطلاعات این ثبت‌نام منقضی شده است. لطفاً /start بزنید و از ابتدا شروع کنید.",
            query=query)
        context.user_data.clear()
        return ConversationHandler.END

    return await _after_intake_step(update, context, uid, name, group, intake, username, query=query)


async def _finish_registration(update, context, uid, name, group, intake, username, query=None):
    """پایان ثبت‌نام — اطلاع به ادمین + پیام کاربر

    🐞 P0-FIX: `query` از پارامتر می‌آید (نه از `update.callback_query`).
    پایانِ ثبت‌نام در فلوی «شماره دانشجویی اجباری» از MessageHandler
    می‌آید و callback_query وجود ندارد ⇒ قبلاً AttributeError می‌داد.
    همچنین ورودیِ کاربر با `_esc` امن می‌شود (تزریق markup به پیام ادمین
    و خطای «can't parse entities»).
    """
    if query is None:
        query = getattr(update, 'callback_query', None)
    intake_label = intake or 'نامشخص'
    safe_name = _esc(name)
    safe_user = _esc(username) if username else ''

    if uid == ADMIN_ID:
        await db.update_user(uid, {'approved': True})
        await _reply_registration(
            update, context,
            f"🎉 <b>ثبت‌نام کامل شد!</b>\n\n"
            f"👤 نام: <b>{safe_name}</b>  |  👥 گروه: <b>{_esc(group)}</b>\n"
            f"📅 ورودی: <b>{_esc(intake_label)}</b>\n"
            f"🔑 نقش: <b>ادمین</b>  |  ✅ دسترسی فعال",
            query=query
        )

        await context.bot.send_message(uid, "به پنل ادمین خوش آمدید! 👨‍⚕️",
            reply_markup=admin_keyboard())
        await _send_dashboard_by_id(context, uid)
    else:
        # طبق درخواست صریح: درخواست ثبت‌نام جدید همیشه به پیوی شخصی
        # ادمین ارشد می‌رود (نه فقط گروه) — چون اقدام فوری لازم دارد.
        try:
            await context.bot.send_message(
                ADMIN_ID,
                f"🔔 <b>درخواست ثبت‌نام جدید</b>\n\n"
                f"👤 نام: <b>{safe_name}</b>\n"
                f"👥 گروه: <b>{_esc(group)}</b>\n"
                f"📅 ورودی: <b>{_esc(intake_label)}</b>\n"
                f"📱 یوزرنیم: @{safe_user or 'ندارد'}\n"
                f"🆔 آیدی: <code>{uid}</code>",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅ تأیید", callback_data=f'admin:approve:{uid}'),
                    InlineKeyboardButton("❌ رد",    callback_data=f'admin:reject:{uid}'),
                ]])
            )
        except Exception as e:
            logger.warning(f"Cannot notify admin: {e}")

        # FIX جدید: ثبت در Audit Log گروه ادمین هم (severity پایین —
        # رویداد روزمره است، اما باید در تاریخچه باشد)
        from utils import send_audit_log
        await send_audit_log(
            context.bot, 'admin', name, uid,
            "ثبت‌نام کاربر جدید", module='Users', severity='INFO',
            actor_role='دانشجو', target_type='user', target_label=name,
            details=f"گروه: {group} | ورودی: {intake_label}",
            tags=['ثبت_نام']
        )

        await _reply_registration(
            update, context,
            f"🎉 <b>ثبت‌نام با موفقیت انجام شد!</b>\n\n"
            f"👤 نام: <b>{safe_name}</b>\n"
            f"👥 گروه: <b>{_esc(group)}</b>  |  📅 ورودی: <b>{_esc(intake_label)}</b>\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "⏳ <b>در انتظار تأیید ادمین...</b>\n\n"
            "پس از تأیید، پیام دریافت خواهید کرد. 🙏",
            query=query
        )

    # پاک‌سازی کامل وضعیت گفتگو؛ reg_edu_group/reg_intake قبلاً جا می‌ماندند
    # و ثبت‌نام بعدی با گروه آموزشیِ قبلی شروع می‌شد.
    for k in ('reg_name', 'reg_step', 'reg_group', 'reg_intake',
              'reg_edu_group', 'pending_ref'):
        context.user_data.pop(k, None)
    return ConversationHandler.END


# ══════════════════════════════════════════════════
#  توابع کمکی داشبورد
# ══════════════════════════════════════════════════

async def _show_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from dashboard import build_dashboard_text
    uid = update.effective_user.id
    try:
        text, kb = await build_dashboard_text(uid)
        await update.effective_message.reply_text(text, parse_mode='HTML', reply_markup=kb)
    except Exception as e:
        logger.error(f"Dashboard error: {e}")


async def _send_dashboard_by_id(context: ContextTypes.DEFAULT_TYPE, uid: int):
    from dashboard import build_dashboard_text
    try:
        text, kb = await build_dashboard_text(uid)
        await context.bot.send_message(uid, text, parse_mode='HTML', reply_markup=kb)
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
