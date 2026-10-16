# 📜 قرارداد داده (DATA_CONTRACT) — فاز ۳ ماموریت تکمیل

> برنچ `feat/complete-and-sync` · مبنای حقیقت: کد در کامیت `11df60a`
> هدف: مرجع واحد برای فیلدها/enumها/تنظیمات مشترک بین ۴ لایه. هر تغییر مشترک باید اول این‌جا به‌روز شود.

## ۱. قواعد کلی

1. **تنها DAL مجاز:** همه‌ی خواندن/نوشتن دیتابیس از `db/*` (متدهای کلاس در db/core.py + ماژول‌های db/content,finance,ring,rbac,prestige). دسترسی مستقیم `db.client['medicalbot'][...]` فقط در موارد استثنای مستندشده (مثل `bot_notifications` در web_admin.py — باید به DAL منتقل شود؛ بند ۶).
2. **ObjectId خام** فقط در «جزئیات فنی» با دکمه‌ی کپی نمایش داده می‌شود؛ رابط کاربری با نام/برچسب کار می‌کند.
3. **enum انگلیسی در DB؛ برچسب فارسی در UI** — جدول‌های مرجع بند ۴. هیچ enum جدیدی بدون برچسب فارسی در هر دو اپ (webadmin + miniapp) اضافه نشود.
4. **نوشتن‌های حساس** (پرداخت/نقش/کاربر) همیشه با: `$set` هدفمند + چک `modified_count` (الگوی موجود در ai_practice.answer و finance) + رخداد audit.
5. **زمان‌ها:** ISO-8601 یونیت‌سی (`utc_now_iso` از time_utils)؛ نمایش شمسی فقط در UI.

## ۲. کالکشن‌ها (۷۱ عدد؛ گروه‌بندی دامنه‌ای)

| دامنه | کالکشن‌ها |
|---|---|
| کاربر/دسترسی | users, blacklist, admin_roles, roles, user_roles, perm_catalog, feature_policies, feature_usage, feature_events, web_admin_otps, web_admin_sessions, admin_op_locks |
| محتوا | questions, qbank_files, question_import_jobs, question_import_items, question_migration_backups, url_import_jobs, bs_lessons, bs_sessions, bs_content, ref_subjects, ref_books, ref_files, faq, content_reports, schedules, schedule_templates |
| تمرین/آزمون | question_progress, question_topic_stats, ai_practice_questions, question_ai_quotas, answers, exam_sessions, question_pdf_generations, ai_documents, ai_quiz_sessions, ai_quiz_questions, ai_generation_logs |
| AI گفتگو | ai_conversations (+ ai_mem مسیر قدیمی ربات) |
| پرداخت/اشتراک | sub_plans, subscriptions, sub_payments, family_invites |
| تعامل | tickets, ticket_canned, ticket_overflow, user_notifications, bot_notifications, notif_runs, broadcast_campaigns, feed_reactions, prestige_history |
| زیرساخت | bot_settings, settings_meta, db_counters, migrations, stats, audit_logs, audit_outbox, audit_delivery_metrics, client_errors, wa_saved_filters, wa_api_metrics |

## ۳. فیلدهای کلیدی و نویسنده/خواننده‌ی هر لایه

| فیلد | نویسنده‌ها | خواننده‌ها | نکته |
|---|---|---|---|
| `users.approved` (bool) | ربات (ثبت‌نام/ادمین)، پنل (wa_user_action) | همه‌ی لایه‌ها (گیت‌ها) | تأیید حساب |
| `users.suspended` (bool) | پنل (wa_user_action: suspend/unsuspend) | گیت‌های ربات | تعلیق موقت — بند ۵ |
| `users.blocked_bot` (bool) | ربات (block_user) | notif/dashboards | مسدودسازی از سمت ربات |
| `blacklist` (کالکشن) | پنل (block)، ربات | ثبت‌نام | منع ثبت‌نام مجدد |
| `users.last_active` (ISO) | ربات (update_last_active، گیت −۱) | داشبورد/گزارش‌ها | مبنا‌ی KPI «فعال» بند ۷ |
| `sub_payments.status` | finance.py (زرین‌پال/تصمیم ادمین) | ربات (subscription.py)، پنل | enum بند ۴.۱ |
| `questions.status` | content_admin/qbank | همه | enum بند ۴.۲ |
| `tickets.status` | ربات، API تیکت، مینی‌اپ | پنل، مینی‌اپ | enum بند ۴.۳ |
| `ai_practice_questions` | ai_practice.py | miniapp (EP-01)، بکاپ | سند اختصاصی کاربر؛ quality_status: validated/duplicate_warning |
| `bot_settings` (سند global) | set_setting (دو فرایند) | get_setting/get_settings_by_prefix | کش ۳۰s per-process — بند ۶ |

## ۴. enumهای مرجع + برچسب فارسی واحد

### ۴.۱ وضعیت پرداخت (`sub_payments.status`) — نویسنده: db/finance.py
| مقدار | برچسب پنل (Subscriptions.jsx PAY_STATUS_FA) | آیکون ربات (subscription.py status_icons) |
|---|---|---|
| pending | در انتظار بررسی | ⏳ |
| approved | تأییدشده | ✅ |
| rejected | ردشده | ❌ |
| zarinpal_pending | در انتظار پرداخت | 💳 |
| cancelled | لغوشده | 🚫 |
| refunded | بازگشت وجه | ↩️ |

> `failed` هرگز نوشته نمی‌شود (EN-01 حذف شد). مقدار جدید فقط با به‌روزرسانی هم‌زمان هر دو جدول اضافه شود.

### ۴.۲ وضعیت سؤال (`questions.status`) — نویسنده: content_admin/qbank
pending=در انتظار · approved=تأییدشده · rejected=ردشده · needs_changes=نیازمند اصلاح (برچسب‌ها: Questions.jsx)

### ۴.۳ وضعیت تیکت (`tickets.status`)
open=باز · in_progress=در حال بررسی · waiting_user=منتظر کاربر · resolved=حل‌شده · answered=پاسخ‌داده‌شده · closed=بسته (برچسب‌ها: Tickets.jsx)

### ۴.۴ وضعیت سؤال هوشمند (`ai_practice_questions.status/quality_status`)
status: ready → answered · quality_status: validated | duplicate_warning

### ۴.۵ منبع تغییر سؤال (`content_source` + `generated_by`)
CONTENT_SOURCES در question_bank/contracts.py مرجع است؛ `generated_by: gemini` + `prompt_version` در provenance.

## ۵. معناشناسی «قطع دسترسی» (چهار مکانیزم — EN-04)

| مکانیزم | فیلد/کالکشن | معنا | برگشت‌پذیر از پنل؟ |
|---|---|---|---|
| تأیید نشده | `approved: false` | ثبت‌نام در انتظار؛ دسترسی محدود | ✅ approve |
| تعلیق | `suspended: true` (+approved=false) | دسترسی موقتاً قطع؛ اعلان تعلیق | ✅ unsuspend (approved=true) |
| مسدود ربات | `blocked_bot: true` | ربات پیام نمی‌فرستد | ✅ (ادمین ربات) |
| بلک‌لیست | doc در `blacklist` | منع ثبت‌نام مجدد (سخت‌گیرانه) | ✅ unblock (wa_user_action) |

ترتیب ارزیابی گیت‌ها در ربات: maintenance → channel_lock → broadcast → last_active → (ConversationHandler/دسترسی دامنه). `wa_user_action` (web_admin.py:4676) تنها نقطه‌ی پنل برای هر چهار عملیات، با `_audit` و اعلان bot_notifications.

## ۶. قرارداد تنظیمات (settings)

- **منبع حقیقت:** سند واحد `bot_settings._id='global'` (کلید→مقدار تخت) + `settings_meta` برای متادیتا.
- **خواندن:** `get_setting(key, default)` / `get_settings_by_prefix` — کش in-process ۳۰ ثانیه (PERF-O2) که با `set_setting` همان فرایند فوری به‌روز می‌شود.
- **همگام‌سازی دو فرایند:** ربات و API دو فرایند جدا هستند؛ تغییر تنظیم از پنل حداکثر تا ۳۰ ثانیه بعد در ربات اثر می‌کند (eventual consistency). برای تنظیمات حساسِ فوری، بعد از set عمدی restart/gateway نیست — TTL کوتاه پذیرفته شده است.
- **کلیدهای شناخته‌شده:** ۶۵ کلید (فهرست کامل و وضعیت نویسنده/خواننده: `docs/audit2-data/04_settings_matrix.txt`).
- **Vault کلید AI:** `ai_api_keys` (JSON رمزنگاری‌شده، provider→key) + legacy `ai_api_key` — نوشتن: ai_admin rotation + web_admin rotate؛ خواندن: `_load_vault` در ai_solver.py:883 (به‌روزرسانی ST-02: هر دو زنده‌اند؛ خوانده‌شدن از طریق prefix-dict است نه get_setting مستقیم — علت گزارش کاذب «بدون خواننده»). مقدار کلید هرگز در لاگ/audit/response نمی‌آید.
- **کلیدهای state-marker** (نوشتنی/خواندنی فقط توسط همان نویسنده): index_status، audit_retention_last_run/deleted، grades_term_backfill، __warmup__.

## ۷. تعریف واحد KPI «کاربر فعال»

- **فعال روزانه:** `last_active` در بازه‌ی ۲۴ ساعت گذشته (نویسنده‌ی واحد: گیت −۱ ربات، bot.py:1716 — روی هر Update).
- داشبورد/گزارش‌ها آستانه‌های مختلف همین فیلد را می‌خوانند؛ هر گزارش جدید باید صراحتاً بازه‌ی خودش را ذکر کند (روزانه/هفتگی/ماهانه). عدد واحد جدیدی اختراع نشود.

## ۸. مهاجرت و تغییر قرارداد

- هر تغییر enum/فیلد = migration ایمن idempotent (الگوی `migrations` + db_counters + migrate_round1.py) بدون حذف داده؛ مقادیر قدیمی تا یک نسخه پشتیبانی می‌شوند.
- عملیات تخریبی فقط گزارش (DRY-RUN) — اجرا با پرچم صریح.
