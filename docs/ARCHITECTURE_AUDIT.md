# 🗺️ نقشه معماری پروژه «هامزیار» — سند ممیزی (AUDIT-R1)

> تاریخ: ۱۴۰۵/۰۷/۲۳ (2026-10-15) · برنچ: `chore/audit-polish-round-1`
> این سند خروجی فاز ۱ ممیزی کامل است؛ یافته‌ها در `docs/AUDIT_REPORT.md`.

## ۱. نمای کلی

هامزیار = **ربات تلگرام آموزشی پزشکی** (ثبت‌نام/منابع/بانک سؤال/آزمون/برنامه کلاسی/تیکت/اشتراک) + **مینی‌اپ تلگرام** (React/Vite در `miniapp/`) + **پنل ادمین وب** (React/Vite در `webadmin/`) + **API یکپارچه** (FastAPI).

- دیتابیس: **MongoDB** (تأیید در کد: `motor`، `db/core.py:38` → `_db = client['medicalbot']`) — ۷۰+ کالکشن.
- زمان اجرا: Docker دو-مرحله‌ای (`Dockerfile`) — بیلد فرانت‌ها با npm، ران‌تایم `python:3.11-slim` با **supervisor** که دو پروسه را بالا می‌آورد: `bot` (`python -u bot.py`) و `api` (uvicorn). استقرار: Railway (وبهوک یا polling).
- حجم: ~۹۸,۸۰۰ خط پایتون در ~۹۰ فایل + دو اپ فرانت‌اند.

## ۲. ساختار پوشه‌ها

| مسیر | نقش |
|---|---|
| `bot.py` (2.6k خط) | نقطه ورود ربات؛ ساخت Application، هندلرهای سراسری، jobها، خطایاب مرکزی، polling (`run_polling` با retry) یا webhook (`BOT_WEBHOOK_MODE`؛ `allowed_updates=Update.ALL_TYPES` شامل `my_chat_member`) |
| `start.py`, `message_router.py` | ثبت‌نام (تنها ConversationHandler واقعی) + مسیریابی متن بر اساس `user_data['mode']` |
| `admin.py` (3.8k) | پنل ادمین داخل تلگرام (کاربران/اعلان/تنظیمات) |
| `content_admin.py`, `basic_science.py`, `references.py` | پنل محتوا + جریان مدرن «علوم پایه» (`bs:term:{idx}` ایندکس‌محور) و رفرنس‌ها (`ref:`) |
| `questions.py`, `qbank/`, `question_bank/` | بانک سؤال، آزمون، درون‌ریزی، taxonomy |
| `schedule.py` (1.7k) | برنامه کلاسی/امتحان + اعلان‌های تغییر |
| `ai_solver.py` (3.2k) | «هوشیار» — لایه AI مشترک ربات/پنل (Gemini/OpenAI-compat/Anthropic، vault کلیدها) |
| `ai_admin.py` | پنل مدیریت هوشیار در ربات |
| `reports.py` | گردش کار گزارش محتوا (ربات) |
| `subscription.py`, `subscription_admin.py`, `payments/`, `dunning.py`, `discount_campaign.py` | اشتراک/پرداخت/خانواده/تخفیف |
| `grades.py`, `grade_utils.py` | نمرات |
| `ring/` | «رینگ» — گفتگوی ناشناس دوطرفه (سرویس/مدریشن/relayed notify) |
| `utils.py` | `safe_send*`، `broadcast_message`، لاگ حسابرسی (audit) |
| `http_client.py` | کلاینت httpx اشتراکی (pool مشترک، بسته در shutdown) |
| `db/` | `core.py` (DBCore: کالکشن‌ها، ایندکس‌ها، آمار)، `content.py`، `rbac.py`، `prestige.py`، `finance.py`، `ring.py`، `migrations.py` (نسخه‌دار، idempotent، v5) |
| `api/` | `main.py` (lifespan/migrations/mount استاتیک)، `auth.py` (initData HMAC + سشن وب)، `rate_limit.py`، `routers/*` (~۲۰ روتر) |
| `webadmin/src/` | پنل وب (React، صفحات: Users/Dashboard/Content/Questions/Tickets/Subscriptions/AiAdmin/RingStreet/System/Operations/…) |
| `miniapp/src/` | مینی‌اپ (React + zustand، صفحه‌ها: Learn/Rank/Ai/Schedule/Me/…) |
| `tests/` | ۳۷ فایل تست (موج‌های QA قبلی + roundtrip بکاپ + قراردادهای ایستا) |
| `migrate_round1.py` | migration دور اول فیکس‌ها (بلاک‌کنندگان/report_id/…) |

## ۳. نقاط ورود و جریان‌ها

### ربات
- ورود: `bot.py::main` → `_run_polling_with_retry(_build_application_with_post_init)`.
- مسیریابی callback: `build_application` — جدول regex→هندلر (`bot.py:2120-2165`): `bs[_:]`, `ref[_:]`, `resources:`, `download_resource:` (legacy)، `dashboard`, `questions`, `schedule`, `notif`, `admin`, `ai` و…
- TypeHandlerهای گروه منفی: `maintenance_gate(-4)`، `broadcast_gate`، `update_last_active(-1/2)`، error handler سراسری با `SILENT_ERRORS`/`TRANSIENT_ERRORS`.
- jobها: ۱۴+ job با `JobQueue` (یادآوری امتحان، سؤال روزانه، منابع جدید، بکاپ خودکار، retention، inbox، dunning، heartbeat…).

### API (FastAPI)
- lifespan: warm http client → `run_migrations` (نسخه‌دار) → `ensure_indexes` → بستن jobهای نیمه‌کاره → `notif_runs_close_stale`.
- احراز مینی‌اپ: هدر `X-Init-Data` → `verify_telegram_init_data` (HMAC-SHA256 با توکن ربات + پنجره `auth_date` + nonce اختیاری).
- احراز پنل: OTP یک‌بارمصرف (هش+salt، سقف تلاش، مقاوم به enumeration) → کوکی `wa_session` (HttpOnly/Secure/SameSite=lax، TTL 12h، توکن هش‌شده در `web_admin_sessions` با TTL ایندکس).
- RBAC: `require_perm`/`_perm`/`_perm_any` — پوشش کامل (ممیز: از ۲۵۶ endpoint وب‌ادمین فقط ۲ endpoint ورود عمومی است).
- استاتیک: `miniapp/` و `webadmin/` بیلدشده روی همان سرویس mount می‌شوند.

### جریان‌های اصلی
1. **ثبت‌نام**: /start → ConversationHandler ثبت‌نام → تأیید ادمین (approved) → منوی اصلی (ReplyKeyboard).
2. **آپلود محتوا**: پنل ربات content_admin یا پنل وب → `bs_lessons/bs_sessions/bs_content` (+`ref_*`) → نوتیف scope-aware (`notif_users_by_intake`).
3. **آزمون/سؤال**: بانک سؤال (`questions`، status: pending/approved/…)، `exam_sessions`، `question_progress`، `answers`.
4. **گزارش محتوا**: مینی‌اپ/ربات → `content_reports` (report_id تکرارناپذیر پس از FIX-R1، status_history) → بررسی در ربات/پنل.
5. **اعلان/برودکست**: سه لایه — jobهای زمان‌بندی (شمارش blocked جدا)، `bot_notifs` (صف + زمان‌بندی + DLQ + retry)، کمپین‌های `broadcast_campaigns`.
6. **هوشیار**: `ai_solver.ask_ai` مشترک ربات/پنل؛ کلیدها در `bot_settings.ai_api_keys` (Fernet اختیاری).
7. **احراز پنل**: کد تلگرامی → سشن کوکی (بالا).

## ۴. مدل داده (خلاصه ۷۰+ کالکشن)

- **هویت**: `users` (user_id یکتا، approved/suspended/blocked_bot، intake/group، notification_settings، prestige_xp)، `user_roles`, `admin_roles`, `web_admin_sessions/otps`, `init_nonces`.
- **محتوا**: `bs_lessons → bs_sessions → bs_content` (رشته ObjectId در `lesson_id/session_id` — همیشه string)، `ref_subjects → ref_books → ref_files`.
- **سؤال**: `questions` (+`question_progress/stats/import_jobs/items`)، `answers`.
- **پشتیبانی/گردش کار**: `tickets`, `content_reports`, `audit_logs` (+`audit_outbox`), `bot_notifs`, `notif_runs`, `broadcast_campaigns`.
- **مالی**: `subscriptions`, `sub_payments`, `wallets`, `wallet_transactions`, `discount_codes/uses`.
- **معماری شمارنده**: `db_counters` (find_one_and_update atomic) — پس از FIX-R1 با bootstrap از max موجود.
- **ایندکس‌ها**: ۱۰۰+ ایندکس در `ensure_indexes` (کامل‌ترین بخش پروژه). افزودنی‌های AUDIT-R1: `users.blocked_bot/last_active/registered_at`، `notif_runs.started_at`.

## ۵. نقاط دوگانگی (ریشه باگ‌های تاریخی)

| مفهوم | پیاده‌سازی ۱ | پیاده‌سازی ۲ | وضعیت |
|---|---|---|---|
| منوی منابع | `basic_science.py` مدرن (`bs:` ایندکس‌محور) | `resources.py` legacy (نام در callback_data + `db.get_resources` ناموجود) | legacy ثبت‌نشده/مرده — ⚠️ گزارش A-08 |
| آپلود منبع | `content_admin.py` مدرن | `resources.py::upload_*_handler` (به `db.add_resource` ناموجود) | مرده — A-08 |
| جستجو | `search.py` مدرن (`bs_dl:`) | `download_resource:` legacy | legacy فقط پیام «قدیمی» می‌دهد ✓ |
| وضعیت گزارش | enum مشترک `new/reviewing/resolved/rejected` | — | پس از FIX-R1 یکدست ✓ |
| «کاربر فعال» | `count_reachable_users` (بدون بلاک) | شمارش‌های محلی | پس از FIX-R1 یکدست ✓ |
| کلید AI | vault `ai_api_keys` | `ai_api_key` تک‌مقداری legacy | fallback خوانده می‌شود (هشدار در گزارش) |

## ۶. وابستگی‌ها و پیکربندی

- پین‌شده: `python-telegram-bot[job-queue]==21.3`، `motor==3.3.2`، `fastapi==0.115.4`، `httpx==0.28.1`، `pydantic==2.9.2`، `pyrogram==2.0.106` (فقط سرویس رینیم فایل)، `cryptography==50.0.1`.
- پیکربندی کامل محیطی در `vps.env.example` (۵۶+ متغیر؛ در AUDIT-R1 موارد جاافتاده اضافه شد).
- Deploy: Docker + supervisor (bot+api) روی Railway؛ healthcheck + heartbeat (`bot_heartbeat.py`).
