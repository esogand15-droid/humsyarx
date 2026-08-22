"""
سیستم پشتیبان‌گیری و بازیابی ربات
- Export: JSON کامل از همه دیتابیس‌ها
- Import: بازیابی از فایل JSON
- فقط ادمین اصلی دسترسی دارد
"""
import os, json, logging, io
from datetime import datetime
from utils import fmt_jalali_dt, now_tehran, now_tehran_str
from time_utils import utc_now_iso
from bson import ObjectId
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import db

logger   = logging.getLogger(__name__)
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))


# ── JSON encoder برای ObjectId و datetime ──
class _Enc(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, ObjectId): return str(o)
        if isinstance(o, datetime):  return o.isoformat()
        return super().default(o)


class BackupIntegrityError(RuntimeError):
    """Raised instead of silently producing a truncated/inconsistent backup."""


def _backup_settings_view(document: dict | None) -> dict:
    """Return restorable non-secret settings; credentials never enter artifacts."""
    safe = dict(document or {})
    safe.pop('ai_api_key', None)
    return safe


async def _snapshot_collection(collection, limit: int, key: str, manifest: dict) -> list:
    """Count-verified bounded snapshot; fail closed before any silent truncation.

    Mongo writes may continue while a backup is built, so this is explicitly a
    best-effort count-consistent snapshot rather than a transactional claim.
    One retry absorbs a normal concurrent insert/delete; persistent drift fails
    the backup and is surfaced to the owner.
    """
    for _attempt in range(2):
        before = int(await collection.count_documents({}))
        if before > limit:
            manifest[key] = {"source_count": before, "exported_count": 0,
                             "limit": limit, "complete": False,
                             "reason": "capacity_exceeded"}
            raise BackupIntegrityError(
                f"backup capacity exceeded for {key}: {before}>{limit}")
        rows = await collection.find({}).to_list(limit + 1)
        after = int(await collection.count_documents({}))
        if before == after == len(rows):
            manifest[key] = {"source_count": after, "exported_count": len(rows),
                             "limit": limit, "complete": True}
            return rows
    manifest[key] = {"source_count": after, "exported_count": len(rows),
                     "limit": limit, "complete": False,
                     "reason": "collection_changed_during_backup"}
    raise BackupIntegrityError(f"collection changed during backup: {key}")


# ══════════════════════════════════════════════════
#  Callback اصلی
# ══════════════════════════════════════════════════
async def backup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid   = update.effective_user.id
    if uid != ADMIN_ID:
        await query.answer("❌ فقط ادمین اصلی دسترسی دارد!", show_alert=True); return
    await query.answer()

    data   = query.data
    parts  = data.split(':')
    action = parts[1] if len(parts) > 1 else 'menu'

    if action == 'menu':
        await _show_menu(query)

    elif action == 'export_all':
        await query.edit_message_text(
            "⏳ <b>در حال آماده‌سازی پشتیبان...</b>\n\nلطفاً چند ثانیه صبر کنید.",
            parse_mode='HTML')
        await _export_all(query, context)

    elif action == 'export_users':
        await query.edit_message_text("⏳ در حال آماده‌سازی...", parse_mode='HTML')
        await _export_section(query, context, 'users')

    elif action == 'export_content':
        await query.edit_message_text("⏳ در حال آماده‌سازی...", parse_mode='HTML')
        await _export_section(query, context, 'content')

    elif action == 'export_refs':
        await query.edit_message_text("⏳ در حال آماده‌سازی...", parse_mode='HTML')
        await _export_section(query, context, 'refs')

    elif action == 'export_qbank':
        await query.edit_message_text("⏳ در حال آماده‌سازی...", parse_mode='HTML')
        await _export_section(query, context, 'qbank')

    elif action == 'export_subscription':
        await query.edit_message_text("⏳ در حال آماده‌سازی...", parse_mode='HTML')
        await _export_section(query, context, 'subscription')

    elif action == 'export_grades':
        await query.edit_message_text("⏳ در حال آماده‌سازی...", parse_mode='HTML')
        await _export_section(query, context, 'grades')

    elif action == 'export_access':
        await query.edit_message_text("⏳ در حال آماده‌سازی...", parse_mode='HTML')
        await _export_section(query, context, 'access')

    elif action == 'restore_prompt':
        await query.edit_message_text(
            "📥 <b>بازیابی از فایل پشتیبان</b>\n\n"
            "⚠️ <b>هشدار:</b> این عملیات رکوردهای فایل را با روش <b>merge/upsert</b> بازیابی می‌کند؛ رکوردهای فعلیِ غایب از فایل حذف نمی‌شوند.\n\n"
            "فایل JSON پشتیبان را ارسال کنید:\n"
            "<i>(فایلی که قبلاً با دکمه «پشتیبان کامل» دریافت کرده‌اید)</i>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ لغو", callback_data='backup:menu')
            ]]))
        context.user_data['backup_mode'] = 'waiting_restore'

    # ══════════════════════════════════════════════
    # FIX جدید: بکاپ خودکار زمان‌بندی‌شده
    # ══════════════════════════════════════════════
    elif action == 'auto_settings':
        await _show_auto_settings(query)

    elif action == 'auto_toggle':
        current = await db.get_setting('auto_backup_enabled', False)
        await db.set_setting('auto_backup_enabled', not current)
        await query.answer("✅ بکاپ خودکار فعال شد" if not current else "❌ بکاپ خودکار غیرفعال شد", show_alert=True)
        await _show_auto_settings(query)

    elif action == 'auto_hour':
        hour = int(parts[2])
        await db.set_setting('auto_backup_hour', hour)
        await query.answer(f"✅ ساعت بکاپ خودکار: {hour}:00", show_alert=True)
        await _show_auto_settings(query)

    elif action == 'auto_hour_custom':
        context.user_data['mode'] = 'set_auto_backup_hour'
        await query.edit_message_text(
            "✏️ <b>ساعت بکاپ خودکار</b>\n\n"
            "عددی بین ۰ تا ۲۳ بفرستید (به‌وقت تهران):",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ لغو", callback_data='backup:auto_settings')
            ]])
        )


async def _show_auto_settings(query):
    """
    FIX جدید: تنظیمات بکاپ خودکار — روشن/خاموش + انتخاب ساعت اجرا.
    بکاپ تولیدشده مستقیماً برای ادمین ارشد (ADMIN_ID) ارسال می‌شود.
    """
    enabled = await db.get_setting('auto_backup_enabled', False)
    hour    = await db.get_setting('auto_backup_hour', 3)
    last_run = await db.get_setting('auto_backup_last_run', None)
    last_run_label = last_run[:16].replace('T', ' ') if last_run else 'هنوز اجرا نشده'

    status_label = f"✅ فعال — هر روز ساعت {hour}:00" if enabled else "⬜ غیرفعال"
    toggle_label  = "🔴 غیرفعال کردن" if enabled else "🟢 فعال کردن"

    text = (
        "⏰ <b>بکاپ خودکار</b>\n━━━━━━━━━━━━━━━━\n\n"
        f"وضعیت: <b>{status_label}</b>\n"
        f"🕐 آخرین اجرا: <code>{last_run_label}</code>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "📌 بکاپ کامل هر روز در ساعت تعیین‌شده (به‌وقت تهران) "
        "خودکار ساخته و برای شما ارسال می‌شود."
    )
    keyboard = [
        [InlineKeyboardButton(toggle_label, callback_data='backup:auto_toggle')],
        [
            InlineKeyboardButton("01:00" + (" ✅" if hour == 1 else ""), callback_data='backup:auto_hour:1'),
            InlineKeyboardButton("02:00" + (" ✅" if hour == 2 else ""), callback_data='backup:auto_hour:2'),
            InlineKeyboardButton("03:00" + (" ✅" if hour == 3 else ""), callback_data='backup:auto_hour:3'),
        ],
        [
            InlineKeyboardButton("04:00" + (" ✅" if hour == 4 else ""), callback_data='backup:auto_hour:4'),
            InlineKeyboardButton("05:00" + (" ✅" if hour == 5 else ""), callback_data='backup:auto_hour:5'),
            InlineKeyboardButton("23:00" + (" ✅" if hour == 23 else ""), callback_data='backup:auto_hour:23'),
        ],
        [InlineKeyboardButton("✏️ ساعت دیگر (عدد ۰ تا ۲۳)", callback_data='backup:auto_hour_custom')],
        [InlineKeyboardButton("🔙 بازگشت", callback_data='backup:menu')],
    ]
    await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _show_menu(query):
    now = now_tehran_str()
    auto_on = await db.get_setting('auto_backup_enabled', False)
    auto_hour = await db.get_setting('auto_backup_hour', 3)
    auto_label = f"⏰ بکاپ خودکار: {'فعال — ساعت ' + str(auto_hour) + ':00' if auto_on else 'غیرفعال'}"
    kb = [
        [InlineKeyboardButton("💾 پشتیبان کامل (همه بخش‌ها)", callback_data='backup:export_all')],
        [InlineKeyboardButton("👥 فقط کاربران",    callback_data='backup:export_users'),
         InlineKeyboardButton("📚 علوم پایه",       callback_data='backup:export_content')],
        [InlineKeyboardButton("📖 رفرنس‌ها",        callback_data='backup:export_refs'),
         InlineKeyboardButton("🧪 بانک سوال",       callback_data='backup:export_qbank')],
        [InlineKeyboardButton("💳 اشتراک و پرداخت", callback_data='backup:export_subscription'),
         InlineKeyboardButton("📊 نمرات",           callback_data='backup:export_grades')],
        [InlineKeyboardButton("🔐 دسترسی‌ها و تنظیمات", callback_data='backup:export_access')],
        [InlineKeyboardButton("📥 بازیابی از فایل", callback_data='backup:restore_prompt')],
        [InlineKeyboardButton(auto_label, callback_data='backup:auto_settings')],
        [InlineKeyboardButton("🔙 بازگشت به پنل",   callback_data='admin:cat_settings')],
    ]
    await query.edit_message_text(
        f"💾 <b>پشتیبان‌گیری و بازیابی</b>\n"
        f"━━━━━━━━━━━━━━━━\n\n"
        f"🕐 زمان سرور: <code>{now}</code>\n\n"
        f"برای <b>پشتیبان‌گیری</b>، یکی از بخش‌ها را انتخاب کنید.\n"
        f"برای <b>بازیابی</b>، فایل JSON را آپلود کنید.\n\n"
        f"<i>⚠️ فایل پشتیبان شامل file_id های تلگرام است —\n"
        f"برای بازیابی کامل فایل‌ها، ربات باید به همان bot token دسترسی داشته باشد.</i>",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(kb))


# ══════════════════════════════════════════════════
#  Export توابع
# ══════════════════════════════════════════════════

async def build_full_backup_data() -> dict:
    """
    FIX جدید: منطق ساخت بکاپ کامل از _export_all جدا شد تا هم از
    callback پنل ادمین و هم از job بکاپ خودکار قابل استفاده باشد.
    """
    integrity = {}
    data = {
        'backup_version': '3.0',
        'created_at':     utc_now_iso(),
        'restore_semantics': 'merge_upsert',
        'integrity': {
            'complete': True,
            'consistency': 'count-verified-best-effort',
            'datasets': integrity,
            'excluded_security_data': ['web_admin_otps', 'web_admin_sessions'],
            'excluded_secrets': ['bot_settings.ai_api_key'],
            'excluded_ephemeral_data': ['bot_notifications', 'wa_api_metrics'],
            'exclusion_reason': 'از بازپخش پیام قدیمی و بازیابی نشست/OTP جلوگیری می‌شود',
        },
        'sections':       {}
    }

    # ── کاربران ──
    users = await _snapshot_collection(db.users, 100000, 'users', integrity)
    data['sections']['users'] = {
        'description': 'اطلاعات کاربران ثبت‌نام شده',
        'count':       len(users),
        'data':        users
    }

    # ── علوم پایه ──
    lessons  = await _snapshot_collection(db.bs_lessons, 10000, 'bs_lessons', integrity)
    sessions = await _snapshot_collection(db.bs_sessions, 100000, 'bs_sessions', integrity)
    content  = await _snapshot_collection(db.bs_content, 100000, 'bs_content', integrity)
    data['sections']['basic_science'] = {
        'description': 'علوم پایه — درس‌ها، جلسات و محتوا',
        'lessons':     {'count': len(lessons),  'data': lessons},
        'sessions':    {'count': len(sessions), 'data': sessions},
        'content':     {'count': len(content),  'data': content},
    }

    # ── رفرنس‌ها ──
    subjects  = await _snapshot_collection(db.ref_subjects, 10000, 'ref_subjects', integrity)
    books     = await _snapshot_collection(db.ref_books, 50000, 'ref_books', integrity)
    ref_files = await _snapshot_collection(db.ref_files, 100000, 'ref_files', integrity)
    data['sections']['references'] = {
        'description': 'رفرنس‌های درسی — درس‌ها، کتاب‌ها و فایل‌ها',
        'subjects':    {'count': len(subjects),  'data': subjects},
        'books':       {'count': len(books),     'data': books},
        'files':       {'count': len(ref_files), 'data': ref_files},
    }

    # ── دامنه ساختاریافته بانک سؤال (بانک فایل legacy عمداً جدا archive می‌شود) ──
    questions = await _snapshot_collection(db.questions, 100000, 'questions', integrity)
    qprogress = await _snapshot_collection(db.question_progress, 1000000, 'question_progress', integrity)
    qtopics = await _snapshot_collection(db.question_topic_stats, 500000, 'question_topic_stats', integrity)
    qai = await _snapshot_collection(db.ai_practice_questions, 500000, 'ai_practice_questions', integrity)
    qai_quotas = await _snapshot_collection(db.question_ai_quotas, 100000, 'question_ai_quotas', integrity)
    exams = await _snapshot_collection(db.exam_sessions, 500000, 'exam_sessions', integrity)
    pdf_generations = await _snapshot_collection(db.question_pdf_generations, 500000, 'question_pdf_generations', integrity)
    import_jobs = await _snapshot_collection(db.question_import_jobs, 100000, 'question_import_jobs', integrity)
    import_items = await _snapshot_collection(db.question_import_items, 1000000, 'question_import_items', integrity)
    migration_backups = await _snapshot_collection(db.question_migration_backups, 200000, 'question_migration_backups', integrity)
    data['sections']['qbank'] = {
        'description': 'دامنه ساختاریافته بانک سؤال، تمرین، آزمون، PDF و import',
        'questions': {'count': len(questions), 'data': questions},
        'progress': {'count': len(qprogress), 'data': qprogress},
        'topic_stats': {'count': len(qtopics), 'data': qtopics},
        'ai_personal': {'count': len(qai), 'data': qai},
        'ai_quotas': {'count': len(qai_quotas), 'data': qai_quotas},
        'exams': {'count': len(exams), 'data': exams},
        'pdf_generations': {'count': len(pdf_generations), 'data': pdf_generations},
        'import_jobs': {'count': len(import_jobs), 'data': import_jobs},
        'import_items': {'count': len(import_items), 'data': import_items},
        'migration_backups': {'count': len(migration_backups), 'data': migration_backups},
    }

    # ── برنامه ──
    schedules = await _snapshot_collection(db.schedules, 100000, 'schedules', integrity)
    data['sections']['schedules'] = {
        'description': 'برنامه کلاس‌ها و امتحانات',
        'count':       len(schedules),
        'data':        schedules
    }

    # ── FAQ ──
    faqs = await _snapshot_collection(db.faq, 10000, 'faq', integrity)
    data['sections']['faq'] = {
        'description': 'سوالات متداول',
        'count':       len(faqs),
        'data':        faqs
    }

    # ── تیکت‌ها ──
    tickets = await _snapshot_collection(db.tickets, 100000, 'tickets', integrity)
    data['sections']['tickets'] = {
        'description': 'تیکت‌های پشتیبانی',
        'count':       len(tickets),
        'data':        tickets
    }

    # ── FIX جدید: دسترسی‌ها و امنیت — نقش‌های ادمین، بلک‌لیست، ورودی‌ها ──
    # این‌ها حیاتی‌اند: اگه گم بشن، همه‌ی نقش‌های تفویض‌شده (نماینده‌ها،
    # مدیران محتوای محدود و...) و لیست کاربران بلاک‌شده از دست می‌ره.
    roles       = await _snapshot_collection(db.roles, 10000, 'roles', integrity)
    user_roles  = await _snapshot_collection(db.user_roles, 100000, 'user_roles', integrity)
    perm_catalog= await _snapshot_collection(db.perm_catalog, 10000, 'perm_catalog', integrity)
    admin_roles = await _snapshot_collection(db.admin_roles, 10000, 'admin_roles', integrity)
    blacklist   = await _snapshot_collection(db.blacklist, 100000, 'blacklist', integrity)
    intakes     = await _snapshot_collection(db.intakes, 10000, 'intakes', integrity)
    data['sections']['access_control'] = {
        'description': 'دسترسی‌ها و امنیت — RBAC اصلی، projection میراثی، بلک‌لیست و ورودی‌ها',
        'roles':       {'count': len(roles), 'data': roles},
        'user_roles':  {'count': len(user_roles), 'data': user_roles},
        'perm_catalog': {'count': len(perm_catalog), 'data': perm_catalog},
        'admin_roles': {'count': len(admin_roles), 'data': admin_roles},
        'blacklist':   {'count': len(blacklist),   'data': blacklist},
        'intakes':     {'count': len(intakes),     'data': intakes},
    }

    # ── FIX جدید: سیستم اشتراک — دقیقاً همون چیزی که قبلاً توی بکاپ نبود ──
    sub_plans     = await _snapshot_collection(db.sub_plans, 10000, 'sub_plans', integrity)
    subscriptions = await _snapshot_collection(db.subscriptions, 100000, 'subscriptions', integrity)
    sub_payments  = await _snapshot_collection(db.sub_payments, 100000, 'sub_payments', integrity)
    discount_codes= await _snapshot_collection(db.discount_codes, 10000, 'discount_codes', integrity)
    # کمپین تخفیف: سوابق مصرف هر کاربر (per_user_limit) + کمپین‌های برودکست
    discount_uses  = await _snapshot_collection(db.discount_uses, 100000, 'discount_uses', integrity)
    discount_bcasts= await _snapshot_collection(db.discount_bcasts, 50000, 'discount_broadcasts', integrity)
    data['sections']['subscription_system'] = {
        'description': 'سیستم اشتراک — پلن‌ها، وضعیت هر کاربر، رسیدهای پرداخت، کدهای تخفیف و کمپین‌ها',
        'plans':          {'count': len(sub_plans),      'data': sub_plans},
        'subscriptions':  {'count': len(subscriptions),  'data': subscriptions},
        'payments':       {'count': len(sub_payments),   'data': sub_payments},
        'discount_codes': {'count': len(discount_codes), 'data': discount_codes},
        'discount_uses':  {'count': len(discount_uses),  'data': discount_uses},
        'discount_broadcasts': {'count': len(discount_bcasts), 'data': discount_bcasts},
    }

    # ── FIX جدید: نمرات ──
    grades = await _snapshot_collection(db.grades, 100000, 'grades', integrity)
    data['sections']['grades'] = {
        'description': 'نمرات ثبت‌شده توسط ادمین/نماینده‌های ورودی',
        'count':       len(grades),
        'data':        grades
    }

    # ── FIX جدید: تنظیمات کلی ربات — یک سند واحد (شماره کارت، کلید
    # اجباری اشتراک، بازه نوتیف، حالت تعمیر، لینک حمایت مالی و...) ──
    settings_doc_raw = await db.settings.find_one({'_id': 'global'})
    settings_doc = _backup_settings_view(settings_doc_raw)
    integrity['settings'] = {'source_count': 1 if settings_doc_raw else 0,
                             'exported_count': 1 if settings_doc else 0,
                             'limit': 1, 'complete': True}
    data['sections']['settings'] = {
        'description': 'تنظیمات کلی ربات (یک سند واحد)',
        'count':       1 if settings_doc else 0,
        'data':        settings_doc or {},
    }

    # ── FIX جدید: گزارش‌ها و لاگ‌ها — کمتر حیاتی، ولی برای پیگیری مفیدن ──
    content_reports = await _snapshot_collection(db.content_reports, 100000, 'content_reports', integrity)
    audit_logs       = await _snapshot_collection(db.audit_logs, 100000, 'audit_logs', integrity)
    notif_runs        = await _snapshot_collection(db.notif_runs, 50000, 'notif_runs', integrity)
    data['sections']['logs'] = {
        'description': 'گزارش محتوا، لاگ فعالیت‌های حساس، تاریخچه‌ی اجرای نوتیف‌ها',
        'content_reports': {'count': len(content_reports), 'data': content_reports},
        'audit_logs':       {'count': len(audit_logs),       'data': audit_logs},
        'notif_runs':        {'count': len(notif_runs),        'data': notif_runs},
    }

    # ── FIX جدید: آمار خام — پاسخ‌های دانشجویان به سوالات ──
    stats_rows = await _snapshot_collection(db.stats_col, 100000, 'stats', integrity)
    answers    = await _snapshot_collection(db.answers, 100000, 'answers', integrity)
    data['sections']['stats'] = {
        'description': 'آمار خام تمرین‌ها — snapshot شمارش‌شده؛ بالاتر از ظرفیت بدون تولید فایل ناقص متوقف می‌شود',
        'stats':   {'count': len(stats_rows), 'data': stats_rows},
        'answers': {'count': len(answers),    'data': answers},
    }

    # ── داده‌های durable جدید که در بکاپ v2 جا افتاده بودند ──
    broadcast_campaigns = await _snapshot_collection(db.broadcast_campaigns, 100000, 'broadcast_campaigns', integrity)
    user_notifications = await _snapshot_collection(db.user_notifs, 100000, 'user_notifications', integrity)
    data['sections']['communications'] = {
        'description': 'کمپین‌های ارسال همگانی و صندوق اعلان پایدار دانشجو؛ outbox اجرایی عمداً مستثنا است',
        'broadcast_campaigns': {'count': len(broadcast_campaigns), 'data': broadcast_campaigns},
        'user_notifications': {'count': len(user_notifications), 'data': user_notifications},
    }

    ai_reports = await _snapshot_collection(db.ai_reports, 100000, 'ai_reports', integrity)
    ai_conversations = await _snapshot_collection(db.ai_conversations, 100000, 'ai_conversations', integrity)
    data['sections']['ai'] = {
        'description': 'گزارش‌های هوشیار و گفت‌وگوهای پایدار؛ فقط در پشتیبان owner-only',
        'reports': {'count': len(ai_reports), 'data': ai_reports},
        'conversations': {'count': len(ai_conversations), 'data': ai_conversations},
    }

    prestige_history = await _snapshot_collection(db.prestige_history, 100000, 'prestige_history', integrity)
    feed_reactions = await _snapshot_collection(db.feed_reactions, 100000, 'feed_reactions', integrity)
    exam_sessions = await _snapshot_collection(db.exam_sessions, 100000, 'exam_sessions', integrity)
    data['sections']['prestige'] = {
        'description': 'تاریخچه Prestige، واکنش فید و جلسات آزمون/چالش',
        'history': {'count': len(prestige_history), 'data': prestige_history},
        'feed_reactions': {'count': len(feed_reactions), 'data': feed_reactions},
        'exam_sessions': {'count': len(exam_sessions), 'data': exam_sessions},
    }

    saved_views = await _snapshot_collection(db.wa_saved_filters, 100000, 'wa_saved_filters', integrity)
    settings_meta = await _snapshot_collection(db.settings_meta, 100000, 'settings_meta', integrity)
    migrations = await _snapshot_collection(db.migrations, 10000, 'migrations', integrity)
    data['sections']['webadmin_state'] = {
        'description': 'نماهای ذخیره‌شده، متای تنظیمات و وضعیت مهاجرت‌ها؛ بدون نشست و telemetry',
        'saved_views': {'count': len(saved_views), 'data': saved_views},
        'settings_meta': {'count': len(settings_meta), 'data': settings_meta},
        'migrations': {'count': len(migrations), 'data': migrations},
    }

    # آمار خلاصه
    data['summary'] = {
        'users':          len(users),
        'lessons':        len(lessons),
        'sessions':       len(sessions),
        'content_files':  len(content),
        'ref_subjects':   len(subjects),
        'ref_books':      len(books),
        'ref_files':      len(ref_files),
        'questions':      len(questions),
        'schedules':      len(schedules),
        'faqs':           len(faqs),
        'tickets':         len(tickets),
        'roles':           len(roles),
        'user_roles':      len(user_roles),
        'permissions':     len(perm_catalog),
        'admin_roles':     len(admin_roles),
        'blacklist':       len(blacklist),
        'intakes':        len(intakes),
        'sub_plans':      len(sub_plans),
        'subscriptions':  len(subscriptions),
        'sub_payments':   len(sub_payments),
        'discount_codes': len(discount_codes),
        'discount_uses':  len(discount_uses),
        'discount_broadcasts': len(discount_bcasts),
        'grades':         len(grades),
        'settings':       1 if settings_doc else 0,
        'content_reports':len(content_reports),
        'audit_logs':     len(audit_logs),
        'notif_runs':     len(notif_runs),
        'stats_rows':     len(stats_rows),
        'answers':        len(answers),
        'broadcast_campaigns': len(broadcast_campaigns),
        'user_notifications': len(user_notifications),
        'ai_reports':      len(ai_reports),
        'ai_conversations': len(ai_conversations),
        'prestige_history': len(prestige_history),
        'feed_reactions':  len(feed_reactions),
        'exam_sessions':   len(exam_sessions),
        'saved_views':     len(saved_views),
        'settings_meta':   len(settings_meta),
        'migrations':      len(migrations),
    }
    return data


async def _export_all(query, context):
    """پشتیبان کامل از همه بخش‌ها — برای دکمه پنل ادمین"""
    try:
        data = await build_full_backup_data()
        await _send_json_file(query, data, filename='backup_full')
        # FIX لاگ: دانلود کل دیتابیس حساس‌ترین عملیات است و قبلاً
        # هیچ‌جا ثبت نمی‌شد — حالا مثل خروجی اکسل، در audit_logs و
        # گروه لاگ ثبت می‌شود که کی و چه زمانی بکاپ گرفته است.
        from utils import send_audit_log
        uid = query.from_user.id
        admin_user = await db.get_user(uid)
        actor_name = admin_user.get('name', 'مدیر ارشد') if admin_user else 'مدیر ارشد'
        actor_role = await db.get_actor_role_label(uid)
        await send_audit_log(
            context.bot, 'admin', actor_name, uid,
            "دریافت پشتیبان کامل دیتابیس", module='Backup', severity='HIGH',
            actor_role=actor_role,
            details=f"👥 کاربران: {data['summary'].get('users',0)} | 🧪 سوالات: {data['summary'].get('questions',0)}",
            tags=['پشتیبان']
        )
    except Exception as e:
        logger.error(f"Backup error: {e}")
        await query.edit_message_text(
            f"❌ خطا در پشتیبان‌گیری:\n<code>{e}</code>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 بازگشت", callback_data='backup:menu')
            ]]))


def _count_section_records(data: dict) -> int:
    """شمارش کل رکوردهای یک بکاپ بخشی — یا از فیلد count یا جمع count زیربخش‌ها"""
    total = data.get('count')
    if isinstance(total, int):
        return total
    return sum(
        v.get('count', 0) for v in data.values()
        if isinstance(v, dict) and isinstance(v.get('count'), int)
    )


async def send_backup_to_bot_chat(bot, chat_id: int, data: dict, filename: str = 'backup_auto',
                                   title: str = None):
    """
    ارسال فایل بکاپ مستقیماً با bot.send_document — برای job بکاپ
    خودکار و همچنین درخواست‌های پنل وب (صف bot_notifications) که
    query/callback در دسترس نیست.

    FIX جدید: پارامتر title اختیاری — برای بکاپ خودکار «روزانه» و برای
    درخواست دستی وب «پشتیبان‌گیری دستی (از پنل وب)» نمایش داده می‌شود.
    FIX جدید: برای بکاپ بخشی (بدون summary کامل)، کپشن به‌جای آمار
    صفرگونه، توضیح بخش و تعداد رکوردهایش را نشان می‌دهد.
    """
    json_str   = json.dumps(data, ensure_ascii=False, indent=2, cls=_Enc)
    file_bytes = json_str.encode('utf-8')
    file_obj   = io.BytesIO(file_bytes)
    now_str    = now_tehran().strftime('%Y%m%d_%H%M')
    fname      = f"{filename}_{now_str}.json"
    file_obj.name = fname

    summary = data.get('summary', {})
    if summary:
        stats_text = '\n'.join([
            f"👥 کاربران: {summary.get('users',0)}",
            f"📖 درس‌ها: {summary.get('lessons',0)}",
            f"🧪 سوالات: {summary.get('questions',0)}",
            f"🎫 تیکت‌ها: {summary.get('tickets',0)}",
        ])
    else:
        desc  = data.get('description', 'بخشی از دیتابیس')
        total = _count_section_records(data)
        stats_text = f"🗂 بخش: {desc}\n📊 رکوردها: {total}"

    caption = (
        f"{title or '💾 <b>بکاپ خودکار روزانه</b>'}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🕐 {now_tehran_str()}\n\n"
        f"{stats_text}\n\n"
        f"📦 حجم: {len(file_bytes)//1024} KB"
    )
    await bot.send_document(
        chat_id, document=file_obj, caption=caption,
        parse_mode='HTML', filename=fname
    )


async def send_backup_from_web(bot, chat_id: int, section: str = 'all') -> int:
    """
    FIX جدید: بکاپ درخواستی از پنل وب مینی‌اپ — توسط mini_app_outbox_job
    از روی سیگنال __BACKUP_REQUEST__ صدا زده می‌شود و فایل را به چت
    درخواست‌کننده می‌فرستد. خروجی تعداد رکوردهاست (برای لاگ سرور).
    """
    if section == 'all':
        data = await build_full_backup_data()
        filename = 'backup_full_web'
        total = sum(data.get('summary', {}).values())
    else:
        data = await build_section_backup_data(section)
        filename = f'backup_{section}_web'
        total = _count_section_records(data)
    await send_backup_to_bot_chat(
        bot, chat_id, data, filename=filename,
        title="💾 <b>پشتیبان‌گیری دستی (از پنل وب)</b>"
    )
    return total


# برچسب فارسی بخش‌های بکاپ — بین callback ربات، API وب و مینی‌اپ مشترک
BACKUP_SECTION_LABELS = {
    'users':        'کاربران',
    'content':      'علوم پایه',
    'refs':         'رفرنس‌ها',
    'qbank':        'بانک سوال',
    'subscription': 'اشتراک و پرداخت',
    'grades':       'نمرات',
    'access':       'دسترسی‌ها و تنظیمات',
}


async def build_section_backup_data(section: str) -> dict:
    """
    FIX جدید: منطق ساخت بکاپ یک بخش خاص از _export_section جدا شد تا
    علاوه بر دکمه‌های ربات، از پنل وب (صف bot_notifications) هم همان
    خروجی یکسان تولید شود. بخش نامعتبر → ValueError.
    """
    integrity = {}
    data = {
        'backup_version': '3.0',
        'section':        section,
        'created_at':     utc_now_iso(),
        'restore_semantics': 'merge_upsert',
        'integrity': {
            'complete': True, 'consistency': 'count-verified-best-effort',
            'datasets': integrity,
            'excluded_security_data': ['web_admin_otps', 'web_admin_sessions'],
            'excluded_secrets': ['bot_settings.ai_api_key'],
            'excluded_ephemeral_data': ['bot_notifications', 'wa_api_metrics'],
            'exclusion_reason': 'از بازپخش پیام قدیمی و بازیابی نشست/OTP جلوگیری می‌شود',
        },
    }

    if section == 'users':
        rows = await _snapshot_collection(db.users, 100000, 'users', integrity)
        data['description'] = 'کاربران ثبت‌نام شده'
        data['count']       = len(rows)
        data['data']        = rows

    elif section == 'content':
        lessons  = await _snapshot_collection(db.bs_lessons, 10000, 'bs_lessons', integrity)
        sessions = await _snapshot_collection(db.bs_sessions, 100000, 'bs_sessions', integrity)
        content  = await _snapshot_collection(db.bs_content, 100000, 'bs_content', integrity)
        data['description'] = 'علوم پایه'
        data['lessons']     = {'count': len(lessons),  'data': lessons}
        data['sessions']    = {'count': len(sessions), 'data': sessions}
        data['content']     = {'count': len(content),  'data': content}

    elif section == 'refs':
        subjects  = await _snapshot_collection(db.ref_subjects, 10000, 'ref_subjects', integrity)
        books     = await _snapshot_collection(db.ref_books, 50000, 'ref_books', integrity)
        ref_files = await _snapshot_collection(db.ref_files, 100000, 'ref_files', integrity)
        data['description'] = 'رفرنس‌های درسی'
        data['subjects']    = {'count': len(subjects),  'data': subjects}
        data['books']       = {'count': len(books),     'data': books}
        data['files']       = {'count': len(ref_files), 'data': ref_files}

    elif section == 'qbank':
        snapshots = [
            ('questions', db.questions, 100000, 'questions'),
            ('progress', db.question_progress, 1000000, 'question_progress'),
            ('topic_stats', db.question_topic_stats, 500000, 'question_topic_stats'),
            ('ai_personal', db.ai_practice_questions, 500000, 'ai_practice_questions'),
            ('ai_quotas', db.question_ai_quotas, 100000, 'question_ai_quotas'),
            ('exams', db.exam_sessions, 500000, 'exam_sessions'),
            ('pdf_generations', db.question_pdf_generations, 500000, 'question_pdf_generations'),
            ('import_jobs', db.question_import_jobs, 100000, 'question_import_jobs'),
            ('import_items', db.question_import_items, 1000000, 'question_import_items'),
            ('migration_backups', db.question_migration_backups, 200000, 'question_migration_backups'),
        ]
        data['description'] = 'دامنه ساختاریافته بانک سؤال'
        for key, collection, cap, name in snapshots:
            rows = await _snapshot_collection(collection, cap, name, integrity)
            data[key] = {'count': len(rows), 'data': rows}

    elif section == 'subscription':
        sub_plans      = await _snapshot_collection(db.sub_plans, 10000, 'sub_plans', integrity)
        subscriptions  = await _snapshot_collection(db.subscriptions, 100000, 'subscriptions', integrity)
        sub_payments   = await _snapshot_collection(db.sub_payments, 100000, 'sub_payments', integrity)
        discount_codes = await _snapshot_collection(db.discount_codes, 10000, 'discount_codes', integrity)
        discount_uses  = await _snapshot_collection(db.discount_uses, 100000, 'discount_uses', integrity)
        discount_bcasts= await _snapshot_collection(db.discount_bcasts, 50000, 'discount_broadcasts', integrity)
        data['description']     = 'سیستم اشتراک — پلن‌ها، وضعیت کاربران، رسیدها، کدهای تخفیف و کمپین‌ها'
        data['plans']           = {'count': len(sub_plans),      'data': sub_plans}
        data['subscriptions']   = {'count': len(subscriptions),  'data': subscriptions}
        data['payments']        = {'count': len(sub_payments),   'data': sub_payments}
        data['discount_codes']  = {'count': len(discount_codes), 'data': discount_codes}
        data['discount_uses']   = {'count': len(discount_uses),  'data': discount_uses}
        data['discount_broadcasts'] = {'count': len(discount_bcasts), 'data': discount_bcasts}

    elif section == 'grades':
        grades = await _snapshot_collection(db.grades, 100000, 'grades', integrity)
        data['description'] = 'نمرات ثبت‌شده'
        data['count']       = len(grades)
        data['data']        = grades

    elif section == 'access':
        roles        = await _snapshot_collection(db.roles, 10000, 'roles', integrity)
        user_roles   = await _snapshot_collection(db.user_roles, 100000, 'user_roles', integrity)
        perm_catalog = await _snapshot_collection(db.perm_catalog, 10000, 'perm_catalog', integrity)
        admin_roles  = await _snapshot_collection(db.admin_roles, 10000, 'admin_roles', integrity)
        blacklist    = await _snapshot_collection(db.blacklist, 100000, 'blacklist', integrity)
        intakes      = await _snapshot_collection(db.intakes, 10000, 'intakes', integrity)
        settings_doc_raw = await db.settings.find_one({'_id': 'global'})
        settings_doc = _backup_settings_view(settings_doc_raw)
        integrity['settings'] = {'source_count': 1 if settings_doc_raw else 0,
                                 'exported_count': 1 if settings_doc_raw else 0,
                                 'limit': 1, 'complete': True}
        data['description'] = 'RBAC اصلی، projection میراثی، بلک‌لیست، ورودی‌ها و تنظیمات'
        data['roles']       = {'count': len(roles), 'data': roles}
        data['user_roles']  = {'count': len(user_roles), 'data': user_roles}
        data['perm_catalog'] = {'count': len(perm_catalog), 'data': perm_catalog}
        data['admin_roles'] = {'count': len(admin_roles), 'data': admin_roles}
        data['blacklist']   = {'count': len(blacklist),   'data': blacklist}
        data['intakes']     = {'count': len(intakes),     'data': intakes}
        data['settings']    = {'count': 1 if settings_doc else 0, 'data': settings_doc or {}}

    else:
        raise ValueError(f"بخش نامعتبر: {section}")

    return data


async def _export_section(query, context, section: str):
    """پشتیبان از یک بخش خاص — داده را build_section_backup_data می‌سازد"""
    try:
        data = await build_section_backup_data(section)
        await _send_json_file(query, data, filename=f'backup_{section}')
        # FIX لاگ: دریافت پشتیبان بخشی هم مثل بکاپ کامل ثبت شود
        from utils import send_audit_log
        uid = query.from_user.id
        admin_user = await db.get_user(uid)
        actor_name = admin_user.get('name', 'مدیر ارشد') if admin_user else 'مدیر ارشد'
        actor_role = await db.get_actor_role_label(uid)
        section_fa = BACKUP_SECTION_LABELS.get(section, section)
        await send_audit_log(
            context.bot, 'admin', actor_name, uid,
            f"دریافت پشتیبان بخش «{section_fa}»", module='Backup', severity='HIGH',
            actor_role=actor_role,
            details=f"📊 رکوردها: {_count_section_records(data)}",
            tags=['پشتیبان']
        )

    except Exception as e:
        logger.error(f"Backup section error: {e}")
        await query.edit_message_text(
            f"❌ خطا:\n<code>{e}</code>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 بازگشت", callback_data='backup:menu')
            ]]))


async def _send_json_file(query, data: dict, filename: str):
    """ارسال فایل JSON به ادمین"""
    json_str  = json.dumps(data, ensure_ascii=False, indent=2, cls=_Enc)
    file_bytes= json_str.encode('utf-8')
    file_obj  = io.BytesIO(file_bytes)
    now_str   = now_tehran().strftime('%Y%m%d_%H%M')
    fname     = f"{filename}_{now_str}.json"
    file_obj.name = fname

    # خلاصه آمار
    summary = data.get('summary', {})
    if summary:
        stats_lines = [
            f"👥 کاربران: {summary.get('users',0)}",
            f"📖 درس‌ها: {summary.get('lessons',0)}",
            f"📌 جلسات: {summary.get('sessions',0)}",
            f"📁 فایل محتوا: {summary.get('content_files',0)}",
            f"📚 رفرنس (درس): {summary.get('ref_subjects',0)}",
            f"📘 رفرنس (کتاب): {summary.get('ref_books',0)}",
            f"📄 رفرنس (فایل): {summary.get('ref_files',0)}",
            f"🧪 سوالات: {summary.get('questions',0)}",
        ]
        stats_text = "\n".join(stats_lines)
    else:
        size_kb = len(file_bytes) // 1024
        stats_text = f"📦 حجم: {size_kb} KB"

    caption = (
        f"💾 <b>پشتیبان‌گیری موفق</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🕐 {now_tehran_str()}\n\n"
        f"{stats_text}\n\n"
        f"📦 حجم: {len(file_bytes)//1024} KB\n\n"
        f"<i>این فایل را در جای امنی نگه‌دارید.\n"
        f"برای بازیابی، از دکمه «بازیابی از فایل» استفاده کنید.</i>"
    )

    try:
        await query.message.reply_document(
            document=file_obj,
            caption=caption,
            parse_mode='HTML',
            filename=fname
        )
        await query.edit_message_text(
            "✅ <b>پشتیبان با موفقیت ارسال شد!</b>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 بازگشت به پشتیبان‌گیری", callback_data='backup:menu'),
                InlineKeyboardButton("🏠 پنل ادمین", callback_data='admin:main'),
            ]]))
    except Exception as e:
        logger.error(f"Send backup error: {e}")
        await query.edit_message_text(
            f"❌ خطا در ارسال فایل:\n<code>{e}</code>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 بازگشت", callback_data='backup:menu')
            ]]))


# ══════════════════════════════════════════════════
#  Restore — بازیابی از فایل
# ══════════════════════════════════════════════════

async def handle_auto_backup_hour_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """FIX جدید: دریافت ساعت دلخواه بکاپ خودکار به‌صورت متنی"""
    text = update.message.text.strip()
    context.user_data.pop('mode', None)
    if not text.isdigit() or not (0 <= int(text) <= 23):
        await update.message.reply_text("❌ عدد باید بین ۰ تا ۲۳ باشد. دوباره تلاش کنید.")
        return
    hour = int(text)
    await db.set_setting('auto_backup_hour', hour)
    await update.message.reply_text(
        f"✅ ساعت بکاپ خودکار روی <b>{hour}:00</b> تنظیم شد.",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⏰ بازگشت به تنظیمات بکاپ", callback_data='backup:auto_settings')
        ]])
    )


async def backup_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت فایل JSON برای بازیابی"""
    uid = update.effective_user.id
    if uid != ADMIN_ID: return
    if context.user_data.get('backup_mode') != 'waiting_restore': return

    doc = update.message.document
    if not doc or not doc.file_name.endswith('.json'):
        await update.message.reply_text(
            "❌ لطفاً یک فایل <b>.json</b> ارسال کنید.",
            parse_mode='HTML')
        return

    if doc.file_size > 50 * 1024 * 1024:  # 50MB limit
        await update.message.reply_text("❌ فایل خیلی بزرگ است (حداکثر ۵۰ مگابایت).")
        return

    await update.message.reply_text("⏳ <b>در حال بررسی فایل...</b>", parse_mode='HTML')

    try:
        tg_file    = await context.bot.get_file(doc.file_id)
        file_bytes = await tg_file.download_as_bytearray()
        data       = json.loads(file_bytes.decode('utf-8'))
        integrity = data.get('integrity') if isinstance(data, dict) else None
        if isinstance(integrity, dict) and integrity.get('complete') is not True:
            await update.message.reply_text("❌ این فایل پشتیبان ناقص است و بازیابی نمی‌شود.")
            return

        version = data.get('backup_version', '1.0')
        created_raw = data.get('created_at')
        created = fmt_jalali_dt(created_raw) if created_raw else 'نامشخص'
        section = data.get('section', 'full')

        # ذخیره داده برای تأیید
        context.user_data['restore_data']    = data
        context.user_data['restore_section'] = section

        # آمار فایل
        summary = data.get('summary', {})
        if summary:
            info = "\n".join([
                f"👥 کاربران: {summary.get('users',0)}",
                f"📖 درس‌ها: {summary.get('lessons',0)}",
                f"📁 فایل محتوا: {summary.get('content_files',0)}",
                f"📘 رفرنس کتاب: {summary.get('ref_books',0)}",
                f"🧪 سوالات: {summary.get('questions',0)}",
                f"💳 اشتراک‌ها: {summary.get('subscriptions',0)}",
                f"🧾 رسیدهای پرداخت: {summary.get('sub_payments',0)}",
                f"📊 نمرات: {summary.get('grades',0)}",
                f"🔐 نقش‌های ادمین: {summary.get('admin_roles',0)}",
                f"⚙️ تنظیمات ربات: {'دارد' if summary.get('settings',0) else 'ندارد'}",
            ])
        else:
            count = data.get('count', '?')
            info  = f"تعداد رکورد: {count}"
        integrity_info = ("✅ manifest یکپارچگی کامل" if isinstance(integrity, dict)
                          else "⚠️ فایل legacy بدون manifest یکپارچگی")

        await update.message.reply_text(
            f"📋 <b>اطلاعات فایل پشتیبان:</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"📅 تاریخ ساخت: <code>{created}</code>\n"
            f"🔖 نسخه: {version}\n"
            f"📦 بخش: {section}\n"
            f"{integrity_info}\n\n"
            f"{info}\n\n"
            f"⚠️ <b>آیا مطمئن هستید؟</b>\n"
            f"رکوردهای فایل merge/upsert می‌شوند؛ داده‌های فعلیِ غایب از فایل حذف نمی‌شوند!",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ بله، بازیابی کن", callback_data='backup:confirm_restore')],
                [InlineKeyboardButton("❌ لغو",              callback_data='backup:menu')],
            ]))

    except json.JSONDecodeError:
        await update.message.reply_text("❌ فایل معتبر نیست — JSON خراب است.")
    except Exception as e:
        logger.error(f"Restore parse error: {e}")
        await update.message.reply_text(f"❌ خطا در پردازش فایل:\n<code>{e}</code>",
                                        parse_mode='HTML')


async def backup_confirm_restore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تأیید و اجرای بازیابی"""
    query = update.callback_query
    uid   = update.effective_user.id
    if uid != ADMIN_ID:
        await query.answer("❌ دسترسی ندارید!", show_alert=True); return
    await query.answer()

    data    = context.user_data.get('restore_data')
    section = context.user_data.get('restore_section', 'full')
    if not data:
        await query.edit_message_text("❌ داده‌ای برای بازیابی پیدا نشد. دوباره فایل ارسال کنید.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 بازگشت", callback_data='backup:menu')
            ]]))
        return

    await query.edit_message_text("⏳ <b>در حال بازیابی اطلاعات...</b>", parse_mode='HTML')

    try:
        sections = data.get('sections', {})
        if not sections:
            sections = {section: data}
        actor_doc = await db.get_user(uid)
        await db.log_action(
            uid, (actor_doc or {}).get('name', 'ادمین'),
            await db.get_actor_role_label(uid),
            'آغاز بازیابی بکاپ از Bot', 'Backup', category='admin',
            severity='CRITICAL', target_type='backup', target_label=section,
            after={'phase': 'started', 'sections': len(sections),
                   'semantics': data.get('restore_semantics') or 'merge_upsert'},
            tags=['بازیابی_بکاپ', 'restore_started'],
        )
        restored = {}

        for sec_name, sec_data in sections.items():
            count = await _restore_section(sec_name, sec_data)
            restored[sec_name] = count

        context.user_data.pop('restore_data', None)
        context.user_data.pop('restore_section', None)
        context.user_data.pop('backup_mode', None)

        result_lines = []
        labels = {
            'users':               '👥 کاربران',
            'basic_science':       '📘 علوم پایه',
            'references':          '📚 رفرنس‌ها',
            'qbank':                '🧪 بانک سوال',
            'schedules':            '📅 برنامه',
            'faq':                  '❓ FAQ',
            'tickets':              '🎫 تیکت‌ها',
            'access_control':       '🔐 دسترسی‌ها (نقش/بلک‌لیست/ورودی)',
            'subscription_system':  '💳 اشتراک و پرداخت',
            'grades':                '📊 نمرات',
            'settings':              '⚙️ تنظیمات ربات',
            'logs':                  '📋 گزارش‌ها و لاگ‌ها',
            'stats':                 '📈 آمار خام تمرین‌ها',
            'communications':        '📣 کمپین‌ها و صندوق اعلان',
            'ai':                    '🤖 داده‌های پایدار هوشیار',
            'prestige':              '🏅 تاریخچه Prestige و چالش‌ها',
            'webadmin_state':         '🖥 وضعیت پایدار WebAdmin',
        }
        for k, v in restored.items():
            result_lines.append(f"{labels.get(k, k)}: {v} رکورد")

        # FIX جدید طبق سند: بازیابی بکاپ = CRITICAL — این عمل می‌تواند
        # کل دیتابیس را بازنویسی کند، باید بسیار برجسته و قابل ردیابی باشد.
        from utils import send_audit_log
        admin_user_doc = await db.get_user(uid)
        actor_name = admin_user_doc.get('name', 'ادمین') if admin_user_doc else 'ادمین'
        actor_role = await db.get_actor_role_label(uid)
        await send_audit_log(
            context.bot, 'admin', actor_name, uid,
            "بازیابی بکاپ", module='Backup', severity='CRITICAL',
            actor_role=actor_role,
            target_type='backup', target_label=section,
            details=' | '.join(result_lines),
            tags=['بازیابی_بکاپ']
        )

        await query.edit_message_text(
            f"✅ <b>بازیابی با موفقیت انجام شد!</b>\n"
            f"━━━━━━━━━━━━━━━━\n\n"
            + "\n".join(result_lines),
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 پنل ادمین", callback_data='admin:main')
            ]]))

    except Exception as e:
        logger.error(f"Restore error: {e}")
        try:
            from utils import send_audit_log
            await send_audit_log(
                context.bot, 'admin', 'ادمین', uid,
                "خطا در بازیابی بکاپ", module='Backup', severity='CRITICAL',
                details=str(e)[:200], tags=['خطای_بازیابی']
            )
        except Exception:
            pass
        await query.edit_message_text(
            f"❌ خطا در بازیابی:\n<code>{e}</code>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 بازگشت", callback_data='backup:menu')
            ]]))


async def _restore_section(section: str, sec_data: dict) -> int:
    """بازیابی یک بخش — upsert بر اساس _id"""
    from bson import ObjectId

    def _prep(doc):
        """تبدیل string _id به ObjectId"""
        d = dict(doc)
        if '_id' in d and isinstance(d['_id'], str):
            try: d['_id'] = ObjectId(d['_id'])
            except: pass
        # فیلدهای رابطه‌ای
        for fk in ['lesson_id','session_id','subject_id','book_id','user_id']:
            if fk in d and isinstance(d[fk], str) and len(d[fk]) == 24:
                try: d[fk] = str(d[fk])  # نگه داریم به صورت str
                except: pass
        return d

    async def _upsert_many(col, docs):
        count = 0
        for doc in docs:
            doc = _prep(doc)
            _id = doc.get('_id')
            if _id:
                await col.replace_one({'_id': _id}, doc, upsert=True)
            else:
                await col.insert_one(doc)
            count += 1
        return count

    total = 0

    if section == 'users':
        rows = sec_data.get('data', [])
        total += await _upsert_many(db.users, rows)

    elif section in ('basic_science', 'content'):
        for sub, col in [('lessons','bs_lessons'),('sessions','bs_sessions'),('content','bs_content')]:
            rows = sec_data.get(sub, {}).get('data', [])
            total += await _upsert_many(getattr(db, col), rows)

    elif section in ('references', 'refs'):
        for sub, col in [('subjects','ref_subjects'),('books','ref_books'),('files','ref_files')]:
            rows = sec_data.get(sub, {}).get('data', [])
            total += await _upsert_many(getattr(db, col), rows)

    elif section == 'qbank':
        for sub, col in [
            ('questions', 'questions'), ('progress', 'question_progress'),
            ('topic_stats', 'question_topic_stats'), ('ai_personal', 'ai_practice_questions'),
            ('ai_quotas', 'question_ai_quotas'), ('exams', 'exam_sessions'),
            ('pdf_generations', 'question_pdf_generations'),
            ('import_jobs', 'question_import_jobs'), ('import_items', 'question_import_items'),
            ('migration_backups', 'question_migration_backups'),
        ]:
            rows = sec_data.get(sub, {}).get('data', [])
            total += await _upsert_many(getattr(db, col), rows)

    elif section == 'schedules':
        rows = sec_data.get('data', [])
        total += await _upsert_many(db.schedules, rows)

    elif section == 'faq':
        rows = sec_data.get('data', [])
        total += await _upsert_many(db.faq, rows)

    elif section == 'tickets':
        rows = sec_data.get('data', [])
        total += await _upsert_many(db.tickets, rows)

    # ── FIX جدید: بازیابی بخش‌های تازه‌اضافه‌شده — با alias برای هر دو
    # نامی که ممکنه فایل بکاپ داشته باشه (بکاپ کامل در برابر بکاپ سریع) ──
    elif section in ('access_control', 'access'):
        for sub, col in [
            ('roles', 'roles'), ('user_roles', 'user_roles'),
            ('perm_catalog', 'perm_catalog'), ('admin_roles', 'admin_roles'),
            ('blacklist', 'blacklist'), ('intakes', 'intakes'),
        ]:
            rows = sec_data.get(sub, {}).get('data', [])
            total += await _upsert_many(getattr(db, col), rows)
        # بکاپ سریع «دسترسی‌ها و تنظیمات» شامل settings هم می‌شود
        settings_data = dict(sec_data.get('settings', {}).get('data', {}) or {})
        if settings_data:
            settings_data.pop('_id', None)
            await db.settings.update_one({'_id': 'global'}, {'$set': settings_data}, upsert=True)
            total += 1

    elif section in ('subscription_system', 'subscription'):
        for sub, col in [('plans', 'sub_plans'), ('subscriptions', 'subscriptions'),
                          ('payments', 'sub_payments'), ('discount_codes', 'discount_codes'),
                          ('discount_uses', 'discount_uses'),
                          ('discount_broadcasts', 'discount_bcasts')]:
            rows = sec_data.get(sub, {}).get('data', [])
            total += await _upsert_many(getattr(db, col), rows)

    elif section == 'grades':
        rows = sec_data.get('data', [])
        total += await _upsert_many(db.grades, rows)

    elif section == 'settings':
        # سند تنظیمات یک رکورد واحده (_id='global')، نه لیست — merge
        # می‌کنیم (نه جایگزینی کامل) تا تنظیماتی که بعد از این بکاپ
        # روی سرور فعلی ست شده‌اند حذف نشوند.
        settings_data = dict(sec_data.get('data', {}) or {})
        if settings_data:
            settings_data.pop('_id', None)
            await db.settings.update_one({'_id': 'global'}, {'$set': settings_data}, upsert=True)
            total += 1

    elif section == 'logs':
        for sub, col in [('content_reports', 'content_reports'),
                          ('audit_logs', 'audit_logs'), ('notif_runs', 'notif_runs')]:
            rows = sec_data.get(sub, {}).get('data', [])
            total += await _upsert_many(getattr(db, col), rows)

    elif section == 'stats':
        for sub, col in [('stats', 'stats_col'), ('answers', 'answers')]:
            rows = sec_data.get(sub, {}).get('data', [])
            total += await _upsert_many(getattr(db, col), rows)

    elif section == 'communications':
        for sub, col in [('broadcast_campaigns', 'broadcast_campaigns'),
                         ('user_notifications', 'user_notifs')]:
            rows = sec_data.get(sub, {}).get('data', [])
            total += await _upsert_many(getattr(db, col), rows)

    elif section == 'ai':
        for sub, col in [('reports', 'ai_reports'), ('conversations', 'ai_conversations')]:
            rows = sec_data.get(sub, {}).get('data', [])
            total += await _upsert_many(getattr(db, col), rows)

    elif section == 'prestige':
        for sub, col in [('history', 'prestige_history'), ('feed_reactions', 'feed_reactions'),
                         ('exam_sessions', 'exam_sessions')]:
            rows = sec_data.get(sub, {}).get('data', [])
            total += await _upsert_many(getattr(db, col), rows)

    elif section == 'webadmin_state':
        for sub, col in [('saved_views', 'wa_saved_filters'),
                         ('settings_meta', 'settings_meta'), ('migrations', 'migrations')]:
            rows = sec_data.get(sub, {}).get('data', [])
            total += await _upsert_many(getattr(db, col), rows)

    return total
