# 🔴 FIX-R1 — بسته‌ی اصلاحات دور اول پنل ادمین «هامزیار» (نسخه‌ی ۲ — با هات‌فیکس ربات)

## ⚠️ هات‌فیکس مهم (v2)
**مشکل «ربات جواب نمی‌داد»** ریشه‌یابی شد: ثبت هندلر `my_chat_member` با
`filters.StatusUpdate.MY_CHAT_MEMBER` انجام شده بود که در هیچ نسخه‌ی PTB v20+
وجود ندارد ⇒ `build_application()` با `AttributeError` کرش می‌کرد ⇒ ربات قبل از
شروع polling می‌مُرد (پنل وب سالم بود چون پروسه‌ی جداست).
فیکس: `ChatMemberHandler(my_chat_member_handler, ChatMemberHandler.MY_CHAT_MEMBER)`.
تست‌شده: build کامل ۴۷ handler ✓ + شبیه‌سازی ۴ سناریو ✓ + تأیید سازگاری با PTB 21.3 ✓
**اگر نسخه‌ی قبلی zip را جایگزین کرده‌اید، فقط کافی است `bot.py` این بسته را جایگزین کنید.**


برنچ: `fix/admin-panel-round-1` — ۱۹ فایل تغییر یافته + ۱ فایل جدید (migrate_round1.py)

## روش نصب
۱. فایل‌ها را با همین ساختار پوشه‌ای روی ریپو جایگزین کنید (replace).
۲. **قبل از اجرای ربات/API یک بار migration را اجرا کنید** (idempotent — چند بار اجرا بی‌خطر است):

```bash
MONGODB_URI="mongodb://..." python3 migrate_round1.py
# یا برای مشاهده‌ی خشک: python3 migrate_round1.py --dry
```

۳. ربات و API را ری‌استارت کنید (بستن اجراهای stale در startup هم خودکار انجام می‌شود).
۴. فرانت‌اند (webadmin) را rebuild کنید (npm run build داخل webadmin).

## فهرست فایل‌ها و موارد مرتبط
| فایل | موارد |
|---|---|
| db/core.py | ۱ (بلاک + notif defaults + داشبورد بدون بلاک‌کنندگان)، ۲ (close stale) |
| db/rbac.py | ۱، ۳ |
| db/content.py | ۵ (شمارنده/report_id/وضعیت/هدف)، ۴ (توضیح اختیاری) |
| utils.py | ۱ (safe_send_ex/broadcast skip) |
| bot.py | ۱، ۲ (سه job اعلان + my_chat_member + close stale در startup) |
| admin.py | ۳ (منوی دو-حالته پیش‌فرض اعلان‌ها) |
| reports.py | ۵ (جزئیات هدف + کلید یکتا + بازگشایی) |
| ai_admin.py | ۶، ۷ (کلید sanitize + مدل زنده در ربات) |
| ai_solver.py | ۶، ۷ (sanitize/guards + list_provider_models + کش TTL) |
| api/routers/ai_management.py | ۷ (کاتالوگ زنده + اعتبارسنجی ۴۲۲) |
| api/routers/content_admin.py | ۵ (لیست گزارش‌ها با هدف + برچسب فارسی + oid) |
| api/routers/web_admin.py | ۱ (فیلتر/KPI/CSV/اسکن)، ۲ (metric)، ۴ (rule/repair)، ۵ (delegate) |
| api/main.py | ۲ (close stale در lifespan) |
| webadmin/src/api.js | ۱، ۷ (helperهای اسکن و مدل زنده) |
| webadmin/src/pages/Users.jsx | ۱ (badge 🔕/فیلتر/KPI/اسکن/poll) |
| webadmin/src/pages/Dashboard.jsx | ۱ (کارت بلاک‌کنندگان) |
| webadmin/src/pages/contentTabs.jsx | ۵ (ReportsTab کامل) |
| webadmin/src/pages/Operations.jsx | ۴ (فرم prefill + نوع فارسی) |
| webadmin/src/pages/AiAdmin.jsx | ۶، ۷ (dropdown زنده + تازه‌سازی + هشدار مدل) |
| migrate_round1.py (جدید) | migration همه‌ی موارد (idempotent) |

## نکته‌های امنیتی
- هیچ API key/توکنی در لاگ/خروجی/کامیت ثبت نمی‌شود؛ کلید هرگز به فرانت برنمی‌گردد.
- migration فقط نرمال‌سازی/بک‌فیلل است؛ هیچ داده‌ای حذف نمی‌شود.

## تست‌های انجام‌شده (خلاصه)
- py_compile همه‌ی فایل‌های پایتون ✓ — import کامل زنجیره‌ی api.main ✓
- esbuild همه‌ی فایل‌های JSX ✓
- تست واحد sanitize_api_key/api_key_problem (ارقام فارسی/ZWSP/غیرASCII/فاصله) ✓
- تست زنده list_provider_models با کلید ساختگی (gemini 400 / groq 401 → پیام فارسی) ✓
- تست e2e مسیرهای خطای API گزارش‌ها ✓
- اجرای migrate_round1 روی دیتای سناریوها + اثبات idempotency (اجرای دوم: ۰ تغییر) ✓
