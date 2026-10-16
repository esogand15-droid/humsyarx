# 🏗 معماری هامزیار — سند فاز ۱ (سرشماری کامل)

> تاریخ: ۱۴۰۵/۰۷/۲۴ · برنچ: `feat/complete-and-sync` · مبنای ممیزی: کامیت `a8d9df0`
> این سند نقشه‌ی ۴ لایه و فهرست «یک مفهوم، چند پیاده‌سازی» است. جزئیات ناقص‌کاری‌ها → `COMPLETION_MATRIX.md`

## ۱. نقشه‌ی کلی

```
┌─────────────┐   Telegram Bot API (python-telegram-bot)   ┌──────────────┐
│  ربات تلگرام │ ─────────────────────────────────────────▶ │  مونگو (DB)   │
│  (ماژول‌های  │                                             │  db/core.py  │
│   سطح ریشه) │ ◀──────────────┐                            │  + db/*.py   │
└─────────────┘                │                            └──────┬───────┘
                                │                                   ▲
┌─────────────┐  FastAPI (:8000)│  api/main.py mounts ۲۷ روتر     │
│  پنل وب‌ادمین │ ───────────────┼────────────────────────────────▶│
│  webadmin/   │  React+Vite    │  (prefix /api/…)                 │
│  src/api.js  │                │                                  │
└─────────────┘                │                                  │
┌─────────────┐                │                                  │
│  مینی‌اپ تلگرام│ ──────────────┴─────────────────────────────────┘
│  miniapp/     │   axios same-origin (/api/…) + initData هش‌شده HMAC
│  React+Vite   │
└─────────────┘
```

- **ربات** (`bot.py` ۲۶۶۷ خط + ماژول‌ها): `Application` تک‌پروسه با ConversationHandler مرکزی (فقط ثبت‌نام) + جدول `cbs` از CallbackQueryHandler های standalone (bot.py:2154) + گیت‌های گروه −۴ تا −۱ (maintenance / channel_lock / broadcast / update_last_active در bot.py:1716).
- **بک‌اند** (`api/`): FastAPI با ۲۷ فایل روتر در `api/routers/`؛ همه mount در `api/main.py` با prefixهای `/api/<domain>`؛ احراز پنل با کوکی `wa_session` (OTP)، مینی‌اپ با initData (+nonce اختیاری)، RBAC با `core/rbac.py` + `db.has_permission`.
- **پنل** (`webadmin/`): React/Vite؛ **تنها** دروازه‌ی HTTP آن `src/api.js` است (۳۴۰ wrapper نامدار → `req()` با dedupe و timeout و پیام خطای فارسی).
- **مینی‌اپ** (`miniapp/`): React/Vite؛ axios مستقیم (بدون wrapper مرکزی) + مسیرهای نسبی `/api/…`.
- **دیتابیس**: MongoDB؛ DAL در `db/` (core.py ~۲۴۷KB + content/finance/ring/rbac/prestige/ai_quiz). نام دیتابیس پیش‌فرض `medicalbot`.
- **تنظیمات**: کالکشن settings با `get_setting/set_setting` (پیشوند-محور: ai_، qbank_، gift_، topup_، …) — جزئیات در `audit2-data/04_settings_matrix.txt`.

## ۲. جدول دامنه‌ها ↔ چهار لایه

| دامنه | ربات (ماژول) | API (روتر) | پنل (صفحه) | مینی‌اپ (صفحه) |
|---|---|---|---|---|
| احراز/ثبت‌نام | start.py | registration.py, auth.py | Login.jsx | (initData) |
| کاربران/دسترسی | admin.py, profile.py | admin_panel.py, web_admin.py | Users.jsx, Rbac.jsx | Me/ |
| محتوا (منابع/رفرنس/علوم پایه) | resources.py†, references.py, basic_science.py, content_admin.py | content_admin.py, web_admin.py, references.py, resources.py | Content.jsx | Learn/ |
| بانک سؤال | questions.py, qbank/, question_bank/ | questions.py | Questions.jsx | Learn/, Search/ |
| آزمون‌ساز | hooshyar_quiz.py | questions.py (custom-exam) | Exams.jsx | Learn/ |
| هوشیار (AI) | ai_solver.py, ai_admin.py | ai.py, ai_management.py, web_admin.py (ai/*) | AiAdmin.jsx | Ai/ |
| اشتراک/پرداخت | subscription.py, subscription_admin.py, dunning.py | subscription.py, subscription_management.py | Subscriptions.jsx, TransferCenter.jsx | Payment/ |
| برنامه‌ی هفتگی | schedule.py, schedule_pdf.py | schedule.py, academic_admin.py, content_admin.py | — (در Operations/Exams) | Schedule/ |
| نمرات | grades.py | grades.py, academic_admin.py | — | Grades/ |
| رینگ (گفتگوی ناشناس) | ring/ (۱۳ فایل) | ring_admin.py, ring.py | RingStreet.jsx | (بدون صفحه) |
| تیکت | ticket.py | tickets.py, admin_panel.py | Tickets.jsx | Me/ (inbox) |
| گزارش/آمار | reports.py, audit.py | dashboard.py, reports.py, admin_panel.py | Dashboard.jsx, Analytics.jsx, Audit.jsx, Growth.jsx | Dashboard/, Rank/, Leaderboard/ |
| ارسال اعلان/همگانی | admin.py (broadcast) | admin_panel.py, notifications.py | Notify.jsx, Operations.jsx | Me/ (inbox) |

† ماژول مرده — بند ۳.۱

## ۳. «یک مفهوم، چند پیاده‌سازی» (یافته‌های معماری فاز ۱)

### ۳.۱. سطح API: نسل‌های موازی پنل
دو نسل endpoint برای پنل وب موازی زنده‌اند:
- **نسل قدیم** `api/routers/admin_panel.py` با prefix `/api/admin/*` (۵۹ endpoint) + `content_admin.py` با `/api/content/*` و `academic_admin.py`، `subscription_management.py`، `ai_management.py`.
- **نسل جدید** `api/routers/web_admin.py` (۸۴۳۴ خط، ۲۵۶ endpoint) با `/api/web-admin/*`.
- `webadmin/src/api.js` تقریباً همه‌ی صفحه‌ها را به نسل جدید می‌برد؛ اما ۲۴ wrapper قدیمی بی‌استفاده مانده (`api.userAction`، `api.stats`، `api.userDetail`/`Patch`، `api.ticketClose`/`Reopen`، `api.ringBans`/`ringState`/`ringSession`/… ، `api.pendingUsers`، …) و ۲۸+۴۵ endpoint نسل قدیم بدون مصرف‌کننده‌اند (فهرست کامل: `audit2-data/03_endpoint_matrix.txt`).
- **استثنا**: `/api/subscription/zarinpal/callback` یتیمِ ظاهری نیست — webhook سرویس بیرونی زرین‌پال است.

### ۳.۲. ربات: سه نسل ساخت دکمه/هندلر
- جدول `cbs` متمرکز (bot.py:2154) برای اکثر دامنه‌ها؛
- ثبت مستقیم `app.add_handler(CallbackQueryHandler(...))` برای چند مورد (ثبت‌نام، رینگ)؛
- ثابت‌های پیشوند در هر ماژول (`CB = 'ring:'` در ring/keyboards.py:19، `CB = 'dun:'` در dunning.py:16) — قرارداد یکسان است اما سه الگوی ثبت.

### ۳.۳. DAL: سه سبک دسترسی به کالکشن‌ها
- متدهای کلاس اصلی در `db/core.py` (get_user/update_user/…)؛
- ماژول‌های subject-specific (`db/content.py`، `db/finance.py`، `db/ring.py`…) با متدهای standalone؛
- دسترسی مستقیم `db.client['medicalbot']['bot_notifications']` داخل روترها (مثلاً web_admin.py:4684) — دور زدن DAL.

### ۳.۴. enum وضعیت
- پرداخت: `pending/approved/rejected/cancelled/refunded` (db/finance.py:1109,1216) — پنل فقط ۴ تای اول + `failed`ِ بی‌استفاده را برچسب می‌زند (Subscriptions.jsx:16).
- سؤال: `pending/approved/rejected/needs_changes` — پنل کامل دارد (Questions.jsx:11).
- تیکت: ۶ وضعیت — پنل inline-map کامل دارد (Tickets.jsx:193).
- کاربر: `approved` (bool) + `suspended` (bool) + `blocked_bot` (bool) + کالکشن blacklist جدا — چهار مکانیزم «قطع دسترسی» با معنای متفاوت.

### ۳.۵. تنظیمات: دو منبع حقیقت
- کالکشن settings (`get_setting`/`set_setting` با ۶۵ کلید یکتا)؛
- env varها (فقط راه‌اندازی: TOKEN، MONGO، INIT_NONCE_ENABLED و… — مستند در vps.env.example).
- ۲۲ کلید فقط-خواندنی در کد که نویسنده‌ی پایتونی ندارند → باید از پنل/env ست شوند ولی همه‌شان UI ندارند (فهرست: `audit2-data/04_settings_matrix.txt`).

### ۳.۶. «کاربر فعال»
`update_last_active` (گیت −۱، هر آپدیت) فیلد `last_active` می‌نویسد؛ داشبورد/گزارش‌ها آستانه‌های متفاوتی از همین فیلد می‌خوانند (تعریف واحد KPI هنوز متمرکز نشده — بند SYNC در COMPLETION_MATRIX).

## ۴. ابزارهای ممیزی (قابل بازتولید)

| ابزار | خروجی | چه می‌سنجد |
|---|---|---|
| `tools/audit2/m01_markers.py` | `docs/audit2-data/01_markers.txt` | نشانه‌های ناقص‌کاری (TODO/stub/به‌زودی/…) |
| `tools/audit2/m02_callback_matrix.py` | `02_callback_matrix.txt` | callback_data ↔ هندلر + پوشش answer() |
| `tools/audit2/m03_endpoint_matrix.py` | `03_endpoint_matrix.txt` | endpoint ↔ مصرف‌کننده‌ی فرانت + alias |
| `tools/audit2/m04_settings_dead.py` | `04_settings_matrix.txt` + `05_dead_funcs.txt` | کلیدهای settings + توابع صفرارجاع |

همه با `python3 tools/audit2/m0X_*.py` از ریشه‌ی پروژه اجرا می‌شوند و خروجی متنی می‌نویسند (بدون تغییر کد).
