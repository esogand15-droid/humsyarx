# 🔄 معماری همگام‌سازی چهار لایه (SYNC_DESIGN) — فاز ۳ ماموریت تکمیل

> برنچ `feat/complete-and-sync` · مکمل `ARCHITECTURE.md` (نقشه) و `DATA_CONTRACT.md` (قرارداد)
> پرسش مرکزی: چطور ربات/پنل/دیتابیس/مینی‌اپ بدون مغایرت بمانند؟

## ۱. وضعیت موجود (as-is) و تصمیم‌های طراحی

| نگرانی همگام‌سازی | وضعیت موجود | تصمیم |
|---|---|---|
| منبع حقیقت تنظیمات | سند واحد `bot_settings/global` + کش in-process ۳۰s در هر فرایند | ✅ حفظ؛ DB مبنا، TTL پذیرفته (بند DATA_CONTRACT §۶) |
| دو نسل endpoint پنل | `/api/admin/*` قدیمی + `/api/web-admin/*` جدید موازی | ⏳ EP-20 (نیازمند تصمیم کاربر) — پاک‌سازی تدریجی پیشنهاد می‌شود |
| enumها | انگلیسی در DB، برچسب فارسی در UI — دو جدول مستقل در دو اپ | ✅ جدول مرجع واحد در DATA_CONTRACT §۴؛ قانون: enum جدید = برچسب در هر دو اپ هم‌زمان |
| «کاربر فعال» | last_active ربات + آستانه‌های متفاوت در گزارش‌ها | ✅ تعریف واحد در DATA_CONTRACT §۷ |
| مدیریت ObjectId | DAL یکپارچه + استثناها | بند ۴ این سند |
| رویداد دامنه | audit_logs + audit_outbox + bot_notifications | بند ۳ |

## ۲. جریان‌های همگام‌سازی حیاتی (پس از تکمیل این ماموریت)

### ۲.۱ تصمیم کاربر (block/suspend/approve/delete)
```
پنل (Users.jsx) ──waUserAction──▶ web_admin.wa_user_action
   ├─ db.update_user/blacklist (modified_count+audit)
   ├─ _audit(...) → audit_logs
   └─ bot_notifications.insert (پیامstatus) → ربات در چرخه‌ی ارسال بعدی می‌فرستد
مینی‌اپ هم همان مسیر را می‌بیند (گیت دسترسی، دریافت fresh از /api/profile)
ربات ادمین هم همان معناشناسی دارد (admin.py) — یک قرارداد، دو درِ ورودی.
```

### ۲.۲ تنظیم اشتراک/هوشیار از پنل
پنل → set_setting → DB (فوری) → ربات ≤۳۰s بعد (TTL). پیام‌های حساس (چرخش کلید) از مسیر vault رمزنگاری‌شده می‌روند و هرگز با مقدار خام لاگ نمی‌شوند.

### ۲.۳ سؤال هوشمند (EP-01 — وصل شد)
miniapp Learn → /api/questions/practice → (اتمام بانک) → /practice/ai/generate → answer → propose → صف بازبینی پنل محتوا (pending) → approved → بانک مشترک. یک چرخه‌ی کامل چهارلایه.

### ۲.۴ وضعیت پرداخت
زرین‌پال → zarinpal_callback (webhook) → finance (status: approved + ref_id، اتمیک با شرط status) → ربات (dunning/resume) + پنل (برچسب فارسی DATA_CONTRACT §۴.۱).

## ۳. رویدادهای دامنه (قواعد)

- هر عمل حساس پنل/ربات = یک سند `audit_logs` (actor/action/severity/target) — نویسنده: `_audit` (web_admin) و `audit_event` (ربات)؛ خواننده: Audit.jsx + correlationChain.
- اعلان به کاربر = `bot_notifications` (status پیام) یا `inbox_add` (مینی‌اپ) — هر دو با sent:False تا ارسال موفق.
- **قاعده:** هیچ رویدادی فقط در یک لایه نماند؛ اگر پنل می‌نویسد ربات هم باید بتواند بخواند (و برعکس) — استثنا مستند شود.

## ۴. مدیریت ObjectId (قاعده واحد)

- تولید/تبدیل فقط در DAL (`ObjectId(...)`, `str(...)`)؛ API هرگز ObjectId خام از کلاینت نمی‌پذیرد بدون `ObjectId.is_valid`.
- نمایش: فقط «جزئیات فنی» با دکمه کپی (UI پنل)؛ نام/برچسب در سطح عادی.

## ۵. ماشین وضعیت صریح (موجود — مستندسازی)

| موجودیت | وضعیت‌ها | گذارها |
|---|---|---|
| پرداخت | pending→approved/rejected؛ zarinpal_pending→approved/cancelled؛ approved→refunded | finance (اتمیک، modified_count) |
| سؤال | pending→approved/rejected/needs_changes→(ویرایش)→pending | content_admin/qbank |
| تیکت | open→in_progress→waiting_user→answered→resolved→closed | ربات/API/مینی‌اپ |
| سؤال هوشمند | ready→answered (+proposed) | ai_practice (اتمیک) |
| job درون‌ریزی | created→validating→downloading→validating_file→uploading→registering→completed/failed/cancelled/duplicate | url_import_service (TERMINAL/RUNNING) |

## ۶. گپ‌های باقی‌مانده (فهرست تصمیمی/آینده)

1. **EP-20/EP-31** — حذف یا بایگانی سطح API نسل قدیم (+۷ endpoint فقط-از-راه-wrapper-مرده).
2. **FN-01** — انقضای نقش RBAC: فعال‌سازی `expire_due_roles` نیازمند scheduler (پیشنهاد: job_queue ربات هر ساعت + گزارش شمارش) — تصمیم کاربر.
3. **EP-14** — سرکشی نهایی vault نسل قدیم ai_management.
4. **SY-01** — کش TTL داشبورد (پیشنهاد، عملیاتی).
5. **DAL-گپ:** `db.client['medicalbot']['bot_notifications']` در web_admin.py — انتقال به متد DAL (پیشنهاد فاز بعد).
6. **SY-02** — فعال‌سازی INIT_NONCE_ENABLED (تصمیم امنیتی کاربر).

## ۷. تست همگام‌سازی (فاز ۵ — برنامه)

- تست قرارداد enum: هر مقداری که finance/content_admin می‌نویسد باید در جدول برچسب DATA_CONTRACT §۴ باشد (تست پایتون روی ثابت‌ها).
- E2E دوطرفه‌ی نمونه: decide payment (پنل) → وضعیت در ربات؛ block (پنل) → گیت ربات؛ generate AI (مینی‌اپ) → propose → پنل pending.
- اسکریپت سلامت داده: بررسی enumهای خارج از قرارداد + فیلدهای ناقص (نوشته اما وضعیت نامعتبر).
