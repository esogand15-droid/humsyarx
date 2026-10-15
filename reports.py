"""
⚠️ سیستم گزارش ایراد سوال/جزوه
  ✅ دانشجو دلیل را انتخاب می‌کند (پاسخ اشتباه، فایل خراب و غیره)
  ✅ همزمان به مدیریت اصلی + ادمین محتوا + طراح سوال + رول خرخون ارسال می‌شود
  ✅ داشبورد مدیریت گزارشات با وضعیت (جدید/در حال بررسی/رفع شده/رد شده)
"""
import os
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import db
from utils import fmt_jalali_dt, send_audit_log

logger   = logging.getLogger(__name__)
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))


def _esc_safe(text) -> str:
    """escape سبک برای متن‌های داخل جزئیات گزارش"""
    import html
    return html.escape(str(text or ''))[:500]


async def _safe_edit(query, text: str, parse_mode: str = 'HTML', reply_markup=None):
    """
    FIX باگ مهم: query.edit_message_text روی پیام‌های بدون متن
    (PDF/ویدیو/ویس/عکس) خطای BadRequest می‌دهد چون فقط caption دارند
    نه text. این تابع چک می‌کند پیام اصلی متن قابل‌ویرایش دارد یا نه؛
    اگر نداشت (یا caption دارد)، به‌جای edit یک پیام جدید می‌فرستد.
    """
    msg = query.message
    has_text = msg is not None and getattr(msg, 'text', None)
    if has_text:
        try:
            await query.edit_message_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
            return
        except Exception as e:
            logger.debug(f"_safe_edit fallback to send: {e}")
    # پیام اصلی media است (caption دارد نه text) یا edit fail شد
    try:
        await msg.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
    except Exception as e:
        logger.warning(f"_safe_edit failed completely: {e}")


async def report_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ورودی: report:question:<qid> یا report:resource:<rid> یا report:reason:<reason>"""
    query  = update.callback_query
    await query.answer()
    uid    = update.effective_user.id
    parts  = query.data.split(':')
    action = parts[1] if len(parts) > 1 else ''

    # FIX امنیتی: دکمه‌های مدیریتی (manage/view/status) داخل پیام‌های
    # گروه لاگ محتوا فرستاده می‌شوند — هر عضو آن گروه نباید بتواند
    # با زدن دکمه، گزارش‌ها را مدیریت کند؛ فقط ادمین محتوا/ارشد.
    MANAGEMENT_ACTIONS = {'manage', 'view', 'status'}
    if action in MANAGEMENT_ACTIONS and not await db.is_content_admin(uid):
        await query.answer("❌ شما دسترسی مدیریت گزارشات را ندارید.", show_alert=True)
        return

    if action in ('question', 'resource'):
        target_type = action
        target_id   = parts[2]
        context.user_data['report_target_type'] = target_type
        context.user_data['report_target_id']   = target_id
        await _show_reason_picker(query, target_type)

    elif action == 'reason':
        reason = parts[2]
        if reason == 'other':
            context.user_data['report_reason'] = reason
            context.user_data['mode'] = 'report_note'
            await _safe_edit(
                query, "📝 <b>توضیح ایراد را بنویسید:</b>",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("❌ لغو", callback_data='report:cancel')
                ]])
            )
            return
        await _finalize_report(update, context, reason, '')

    elif action == 'cancel':
        for k in ('report_target_type', 'report_target_id', 'report_reason', 'mode'):
            context.user_data.pop(k, None)
        await _safe_edit(query, "❌ گزارش لغو شد.")

    elif action == 'manage':
        await _show_reports_dashboard(query, parts[2] if len(parts) > 2 else None)

    elif action == 'view':
        rid_key = parts[2]
        try:
            rid = int(rid_key)
        except ValueError:
            rid = rid_key
        await _show_report_detail(query, rid)

    elif action == 'status':
        # 🔴 FIX-R1 (مورد ۵) — rid می‌تواند report_id عددی یا ObjectId
        # سند باشد؛ update با کلید یکتای _id انجام می‌شود تا گزارشِ
        # دارای report_id تکراری (legacy) هم دقیق تغییر کند.
        rid_key = parts[2]
        try:
            rid = int(rid_key)
        except ValueError:
            rid = rid_key
        status = parts[3]
        old_report = await db.get_content_report(rid)
        old_status_fa = {'new': 'جدید', 'reviewing': 'در حال بررسی',
                         'resolved': 'رفع شد', 'rejected': 'رد شد'}.get(
            old_report.get('status', '') if old_report else '', 'نامشخص')
        result = {'updated': False}
        if old_report:
            result = await db.update_report_status(
                old_report['_id'], status, resolved_by=uid)
        if not result.get('updated'):
            await query.answer("⚠️ وضعیت گزارش تغییر نکرد — دوباره تلاش کن یا گزارش را از لیست باز کن.",
                               show_alert=True)
            return
        admin_user = await db.get_user(uid)
        actor_name = admin_user.get('name', 'ادمین') if admin_user else 'ادمین'
        actor_role = await db.get_actor_role_label(uid)
        status_fa  = {'reviewing': 'در حال بررسی', 'resolved': 'رفع شد', 'rejected': 'رد شد'}.get(status, status)
        # FIX طبق سند: رد گزارش/رفع گزارش = HIGH (نتیجه‌گیری مدیریتی مهم)
        sev = 'HIGH' if status in ('resolved', 'rejected') else 'INFO'
        await send_audit_log(
            context.bot, 'content', actor_name, uid,
            "بررسی گزارش محتوا", module='Reports', severity=sev,
            actor_role=actor_role,
            target_id=str(old_report.get('report_id') or rid), target_type='report',
            before={'وضعیت': old_status_fa}, after={'وضعیت': status_fa},
            tags=['بررسی_گزارش']
        )
        await query.answer(f"✅ وضعیت: {status_fa}", show_alert=True)
        await _show_report_detail(query, old_report['_id'])


async def _show_reason_picker(query, target_type: str):
    """
    FIX باگ مهم: قبلاً اینجا edit_message_text مستقیم صدا می‌شد که
    روی پیام‌های فایل (PDF/ویدیو/ویس) خطای BadRequest می‌داد چون آن‌ها
    caption دارند نه text. حالا با _safe_edit ایمن است.
    """
    label = "سوال" if target_type == 'question' else "فایل"
    keyboard = [
        [InlineKeyboardButton(f"❌ {v}", callback_data=f'report:reason:{k}')]
        for k, v in db.REPORT_REASONS.items()
    ]
    keyboard.append([InlineKeyboardButton("🔙 انصراف", callback_data='report:cancel')])
    await _safe_edit(
        query,
        f"⚠️ <b>گزارش ایراد {label}</b>\n\n"
        "دلیل گزارش را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_report_note_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت متن توضیح وقتی دلیل 'سایر' انتخاب شده"""
    note = update.message.text.strip()
    reason = context.user_data.get('report_reason', 'other')
    context.user_data.pop('mode', None)
    await _finalize_report(update, context, reason, note)


async def _finalize_report(update_or_query, context, reason: str, note: str):
    """
    FIX طبق سند: قبلاً مشخص نبود کدام درس/ترم/مبحث/استاد مشکل دارد.
    حالا مسیر کامل محتوا (یا سوال) استخراج و در پیام نوتیف نمایش
    داده می‌شود، تا ادمین مدیریت بلافاصله بفهمد دقیقاً کدام فایل/سوال.
    """
    target_type = context.user_data.pop('report_target_type', '')
    target_id   = context.user_data.pop('report_target_id', '')
    context.user_data.pop('report_reason', None)

    is_callback = hasattr(update_or_query, 'callback_query') and update_or_query.callback_query is not None
    query = update_or_query.callback_query if is_callback else None
    uid   = update_or_query.effective_user.id
    reporter = await db.get_user(uid)
    reporter_name = reporter.get('name', 'کاربر') if reporter else 'کاربر'

    # FIX جدید: استخراج مسیر کامل — درس، ترم، مبحث، استاد، نوع، نام فایل
    designer_id = None
    title = ''
    detail_lines = []
    if target_type == 'question':
        q = await db.get_question_by_id(target_id)
        if q:
            title = q.get('question', '')[:80]
            designer_id = q.get('creator_id')
            lesson_doc = await db.bs_lessons.find_one({'name': q.get('lesson', '')})
            term = lesson_doc.get('term', '') if lesson_doc else ''
            detail_lines = [
                f"📚 درس: {q.get('lesson', '') or '—'}",
                f"🗓 ترم: {term or '—'}",
                f"📌 مبحث: {q.get('topic', '') or '—'}",
            ]
    else:
        path = await db.bs_get_content_full_path(target_id)
        if path:
            title = path.get('description', '') or 'فایل بدون توضیح'
            type_fa = {'pdf': 'PDF', 'video': 'ویدیو', 'voice': 'ویس',
                       'pptx': 'پاورپوینت', 'test': 'نمونه سوال'}.get(path.get('content_type', ''), path.get('content_type', ''))
            detail_lines = [
                f"📚 درس: {path.get('lesson_name', '') or '—'}",
                f"🗓 ترم: {path.get('term', '') or '—'}",
                f"📌 مبحث: {path.get('topic', '') or '—'}",
                f"👨‍🏫 استاد: {path.get('teacher', '') or '—'}",
                f"📁 نوع محتوا: {type_fa or '—'}",
                f"📄 نام فایل: {title}",
            ]

    report_id = await db.create_content_report(
        target_type, target_id, uid, reporter_name, reason, note, designer_id
    )

    # §W9 — سقفِ نرخ خورده است. هرگز نباید بگوییم «ثبت شد» وقتی نشده
    # (§۴۴). کاربر همچنان باید بتواند تمرین را ادامه دهد.
    if not report_id:
        rate_max, window_min = await db.report_rate_limit()
        busy_kb = None
        if context.user_data.get('quiz') and target_type == 'question':
            busy_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("▶️ ادامه تمرین",
                                      callback_data='questions:practice_next')],
                [InlineKeyboardButton("🏠 منو", callback_data='questions:main')],
            ])
        busy_text = (
            "⏳ <b>فعلاً نمی‌توانی گزارش جدیدی ثبت کنی.</b>\n\n"
            f"سقفِ ثبتِ گزارش {rate_max} مورد در هر {window_min} دقیقه است. "
            "کمی بعد دوباره تلاش کن — گزارش‌های قبلی‌ات ثبت شده‌اند."
        )
        if query:
            await _safe_edit(query, busy_text, reply_markup=busy_kb)
        else:
            await update_or_query.message.reply_text(
                busy_text, parse_mode='HTML', reply_markup=busy_kb)
        return

    reason_fa = db.REPORT_REASONS.get(reason, reason)
    target_label = "🧪 سوال" if target_type == 'question' else "📁 فایل"
    detail_block = '\n'.join(detail_lines)

    notify_text = (
        f"🆕 <b>گزارش ایراد جدید #{report_id}</b>\n"
        f"━━━━━━━━━━━━━━━━\n\n"
        f"{target_label}: {title}\n"
        + (f"{detail_block}\n\n" if detail_block else "\n") +
        f"⚠️ علت گزارش: {reason_fa}\n"
        + (f"📝 توضیح: {note}\n" if note else "") +
        f"\n👤 گزارش‌دهنده: {reporter_name}"
    )
    notify_kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔍 بررسی گزارش", callback_data=f'report:view:{report_id}')
    ]])

    # FIX جدید: ثبت در Audit Log گروه محتوا — قبلاً اصلاً ثبت نمی‌شد.
    # نکته: انجام‌دهنده اینجا یک دانشجو است، نه ادمین — نقش او
    # 'دانشجو' ثبت می‌شود تا با اعمال مدیریتی اشتباه گرفته نشود.
    await send_audit_log(
        context.bot, 'content', reporter_name, uid,
        "ثبت گزارش ایراد محتوا", module='Reports', severity='INFO',
        actor_role='دانشجو',
        target_id=target_id, target_type=target_type, target_label=title,
        details=f"علت: {reason_fa}" + (f" | {note}" if note else ""),
        tags=['ثبت_گزارش']
    )

    # ── ارسال همزمان به همه ذی‌نفعان ──
    recipients = set()
    recipients.add(ADMIN_ID)
    content_admins = await db.get_content_admins()
    for ca in content_admins:
        recipients.add(ca['user_id'])
    reviewers = await db.get_reviewers()
    recipients.update(reviewers)
    if designer_id:
        recipients.add(designer_id)
    recipients.discard(uid)  # خود گزارش‌دهنده نباید نوتیف بگیرد

    for rid_target in recipients:
        try:
            # برای طراح سوال متن کمی متفاوت — لحن همکارانه
            if rid_target == designer_id and rid_target not in (ADMIN_ID,):
                designer_text = (
                    f"🔔 <b>گزارش روی سوال شما ثبت شد</b>\n\n"
                    f"🧪 سوال: {title}\n"
                    + (f"{detail_block}\n" if detail_block else "") +
                    f"❌ دلیل: {reason_fa}\n"
                    + (f"📝 توضیح: {note}\n" if note else "") +
                    f"\nلطفاً سوال را بررسی و در صورت نیاز اصلاح کنید 🙏"
                )
                await context.bot.send_message(rid_target, designer_text, parse_mode='HTML')
            else:
                await context.bot.send_message(rid_target, notify_text, parse_mode='HTML',
                                               reply_markup=notify_kb)
        except Exception as e:
            logger.debug(f"report notify failed for {rid_target}: {e}")

    # 🐛 §W8 — گزارش «خروج از تمرین» نیست، یک اکشنِ داخلِ آن است.
    #
    # پیش‌تر پیامِ سؤال با متنِ تأیید جایگزین می‌شد و هیچ دکمه‌ای نمی‌ماند،
    # پس کاربر در بن‌بست می‌افتاد و مجبور بود کلِ مسیرِ
    # «بانک سؤال → تمرین آزاد → ترم → مبحث» را از نو برود. وضعیتِ تمرین
    # (`quiz`) در user_data سالم بود؛ فقط راهِ بازگشت به آن وجود نداشت.
    #
    # حالا اگر کاربر وسطِ تمرین بوده، دکمهٔ «ادامه تمرین» می‌گذاریم که
    # مستقیم سؤالِ بعدی همان مبحث را می‌آورد.
    in_practice = bool(context.user_data.get('quiz')) and target_type == 'question'
    confirm_text = (
        f"✅ <b>گزارش شما با شماره #{report_id} ثبت شد!</b>\n\n"
        "تیم مدیریت و طراح محتوا مطلع شدند. متشکریم از همکاری شما 🙏"
    )
    if in_practice:
        confirm_text += "\n\n<i>این سؤال دیگر به شما نمایش داده نمی‌شود.</i>"

    confirm_kb = None
    if in_practice:
        confirm_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("▶️ ادامه تمرین", callback_data='questions:practice_next')],
            [InlineKeyboardButton("🏠 منو", callback_data='questions:main')],
        ])

    if query:
        await _safe_edit(query, confirm_text, reply_markup=confirm_kb)
    else:
        await update_or_query.message.reply_text(confirm_text, parse_mode='HTML',
                                                 reply_markup=confirm_kb)


# ══════════════════════════════════════════════════
#  داشبورد مدیریت گزارشات
# ══════════════════════════════════════════════════

async def show_reports_main(message, uid: int):
    """فراخوانی از منوی پنل ادمین/محتوا"""
    stats = await db.content_reports_stats()
    text = (
        "📋 <b>گزارشات سوال و جزوه</b>\n━━━━━━━━━━━━━━━━\n\n"
        f"🆕 جدید: <b>{stats['new']}</b>\n"
        f"🔍 در حال بررسی: <b>{stats['reviewing']}</b>\n"
        f"✅ رفع شده: <b>{stats['resolved']}</b>\n"
        f"❌ رد شده: <b>{stats['rejected']}</b>"
    )
    keyboard = [
        [InlineKeyboardButton(f"🆕 جدید ({stats['new']})", callback_data='report:manage:new')],
        [InlineKeyboardButton(f"🔍 در حال بررسی ({stats['reviewing']})", callback_data='report:manage:reviewing')],
        [InlineKeyboardButton("📋 همه گزارشات", callback_data='report:manage:all')],
    ]
    await message.reply_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _show_reports_dashboard(query, status_filter: str = None):
    status = None if status_filter in (None, 'all') else status_filter
    reports = await db.get_content_reports(status, limit=20)
    status_fa = {'new': 'جدید', 'reviewing': 'در حال بررسی', None: 'همه'}.get(status, status)

    if not reports:
        await _safe_edit(
            query,
            f"📋 گزارشات ({status_fa}): هیچ موردی یافت نشد.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 بازگشت", callback_data='admin:cat_content')
            ]])
        )
        return

    keyboard = []
    for r in reports:
        rid = r['report_id']
        icon = {'new': '🆕', 'reviewing': '🔍', 'resolved': '✅', 'rejected': '❌'}.get(r['status'], '❔')
        label = f"{icon} #{rid} — {db.REPORT_REASONS.get(r['reason'], r['reason'])}"
        keyboard.append([InlineKeyboardButton(label, callback_data=f'report:view:{rid}')])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='admin:cat_content')])
    await _safe_edit(
        query,
        f"📋 <b>گزارشات — {status_fa}</b>\n━━━━━━━━━━━━━━━━",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def _show_report_detail(query, report_key):
    """🔴 FIX-R1 (مورد ۵) — جزئیات گزارش با اطلاعات خوانای «هدف».

    به‌جای ObjectId خام: متن سؤال (و گزینه‌ها) یا نام فایل + درس/جلسه/
    استاد. دکمه‌های تغییر وضعیت با کلید یکتای _id ساخته می‌شوند تا حتی
    با report_id تکراریِ legacy دقیق همین گزارش تغییر کند."""
    r = await db.get_content_report(report_key)
    if not r:
        await query.answer("❌ گزارش پیدا نشد!", show_alert=True)
        return

    oid = str(r['_id'])
    info = await db.content_report_target_info(r)
    if info.get('target_missing'):
        target_block = "⚠️ <i>محتوای هدف‌گرفته حذف شده است (در بانک موجود نیست).</i>"
    else:
        target_block = (
            f"📌 عنوان: <b>{_esc_safe(info.get('title') or '—')}</b>\n"
            f"🏷 نوع: {info.get('type_label') or '—'}\n"
            + (f"📚 درس: {info.get('lesson')}\n" if info.get('lesson') else "")
            + (f"🗂 جلسه/مبحث: {info.get('session')}\n" if info.get('session') else "")
            + (f"👨‍🏫 استاد: {info.get('teacher')}\n" if info.get('teacher') else "")
            + (f"ℹ️ {info.get('detail')}\n" if info.get('detail') else "")
        )

    status_fa = {'new': '🆕 جدید', 'reviewing': '🔍 در حال بررسی',
                 'resolved': '✅ رفع شده', 'rejected': '❌ رد شده'}.get(r['status'], r['status'])
    reason_fa = db.REPORT_REASONS.get(r['reason'], r['reason'])

    # سابقه‌ی تغییر وضعیت (audit) — حداکثر ۳ مورد آخر
    history_lines = []
    for h in (r.get('status_history') or [])[-3:]:
        h_fa = {'new': 'جدید', 'reviewing': 'در بررسی',
                'resolved': 'حل‌شده', 'rejected': 'ردشده'}.get(h.get('status'), h.get('status'))
        history_lines.append(f"   • {h_fa} — {fmt_jalali_dt(h.get('at'))}")
    history_block = ("\n<b>🕰 سابقه:</b>\n" + "\n".join(history_lines)) if history_lines else ""

    text = (
        f"📋 <b>گزارش #{r.get('report_id') or '—'}</b>\n━━━━━━━━━━━━━━━━\n\n"
        + target_block + "\n"
        f"❌ دلیل: {reason_fa}\n"
        + (f"📝 توضیح: {_esc_safe(r.get('note',''))}\n" if r.get('note') else "") +
        f"👤 گزارش‌دهنده: {r['reporter_name']}\n"
        f"🕐 تاریخ: {fmt_jalali_dt(r.get('created_at'))}\n\n"
        f"📊 وضعیت: <b>{status_fa}</b>"
        + history_block
    )
    keyboard = []
    if r['status'] not in ('resolved', 'rejected'):
        keyboard.append([
            InlineKeyboardButton("🔍 در حال بررسی", callback_data=f'report:status:{oid}:reviewing'),
        ])
        keyboard.append([
            InlineKeyboardButton("✅ رفع شد",  callback_data=f'report:status:{oid}:resolved'),
            InlineKeyboardButton("❌ رد شد",   callback_data=f'report:status:{oid}:rejected'),
        ])
    else:
        # امکان بازگشایی گزارش بسته‌شده
        keyboard.append([
            InlineKeyboardButton("🔄 بازگشایی (در بررسی)", callback_data=f'report:status:{oid}:reviewing'),
        ])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت به لیست", callback_data='report:manage:all')])
    await _safe_edit(query, text, reply_markup=InlineKeyboardMarkup(keyboard))
