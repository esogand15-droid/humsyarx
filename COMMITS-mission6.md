# ماموریت ۶ — رفع باگ «کلون ⭐ با کلیک» و نظام محدوده محتوا (CoW)

برنچ `fix/content-scope-override` · بازه: `086343b..e8fa5a4` (۱۰ کامیت)

| کامیت | لایه | خلاصه |
|---|---|---|
| 9d64da2 | docs | تحلیل ریشه‌ها R1–R7 + طراحی CoW |
| c46d70c | DAL | ensure_override اتمیک/ایدمپوتنت (bs+ref) + احیای آرشیو، ایندکس‌های یکتای جزئی، سایه‌اندازی archived-aware، override-count/divergence، حذف pycache از index |
| d0557af | ربات | CoW در لحظه‌ی ذخیره در همه‌ی مسیرهای نوشتن، صفحه‌ی انتخاب scope (R4)، سطل سراسری جمع‌شده (R2)، نشان/سربرگ یکدست (R7)، unfork با تأیید، merge واگرایی (R5)، حذف کلون-با-کلیک (R1) |
| d1b3573 | API | edit_scope روی همه‌ی endpointهای نوشتن + _cow_* helpers، قاعده‌ی مشترک effective-view، logical_id، گارد 409 حذف base (بدون cascade)، شمارش منطقی داشبورد، حذف full-scan |
| 25abef7 | API | ویرایش سراسری برای ادمین ورودی از طریق CoW (readonly درست)، فیلتر مشترک درخت + نشان override_count |
| 98e8d85 | پنل وب | حذف 🍴، دیالوگ انتخاب محدوده (ویرایش/آپلود/حذف)، نشان «⭐n»، راهنمای CoW |
| 1040d7a | مینی‌اپ | حذف ✂️ جلسه؛ آپلود/حذف روی 🌐 در حالت ورودی ⇒ override با راهنمای روشن |
| f89f09e | تست | ۴۳ تست: ماتریس تصمیم CoW، اتمیسیتی/ایدمپوتنسی، سایه/آرشیو، merge افزودنی، احیا، جعل edit_scope دور نمی‌زند، قراردادهای static، بودجه‌ی callback، طبقه‌بندی migration |
| d6294f6 | docs | گزارش تحویل CONTENT_SCOPING_REPORT.md |
| e8fa5a4 | ربات/fix | رفع دو باگ bu: گم‌شدن state مکالمه در آپلود/جایگزینی جلد کتاب پس از صفحه‌ی انتخاب scope |

## فایل‌های این بسته
- `db/content.py`, `db/core.py` — DAL
- `content_admin.py`, `basic_science.py` — ربات
- `api/routers/content_admin.py`, `api/routers/web_admin.py`, `api/routers/resources.py` — API
- `webadmin/src/api.js`, `webadmin/src/pages/Content.jsx` — پنل وب
- `miniapp/src/pages/Admin/ContentLibrary.jsx` — مینی‌اپ
- `tools/migration/content_forks.py` (+ rollback) — migration فاز ۵ (dry-run پیش‌فرض)
- `tests/test_content_scope.py` — ۴۳ تست (همه سبز)
- `docs/CONTENT_SCOPING_ANALYSIS.md`, `docs/CONTENT_SCOPE_DESIGN.md`, `docs/CONTENT_SCOPING_REPORT.md`

## وضعیت تست
`tests.test_content_scope`: 43/43 OK · کل suite: مجموعه‌ی خطاهای ازپیش‌موجود بیت‌به‌بیت یکسان با پایه‌ی `086343b` (صفر رگرسیون؛ ۳۴ مورد نیازمند Mongo/محیط زنده).

## اجرای migration در production
1) `python3 tools/migration/content_forks.py` (dry-run + بازبینی گزارش)
2) `python3 tools/migration/content_forks.py --apply` (پشتیبان خودکار در `backups/content_forks/<ts>/`)
3) در صورت نیاز: `python3 tools/migration/content_forks_rollback.py --latest`
