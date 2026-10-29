# جهت طراحیِ هامزیار — بر پایهٔ Skill «UI/UX Pro Max»

> این سند **خروجی واقعیِ اجراشدهٔ** Skill است، نه خلاصهٔ خواندن README.
> همهٔ دستورها با CLI نصب‌شده اجرا شد و متن پاسخ‌ها در
> `HUMSYAR_ROUND8_REPORT.md` نقل شده است.

## ۱) نصب و فعال‌سازی (اثبات)

| مورد | مقدار |
|---|---|
| بستهٔ CLI | `ui-ux-pro-max-cli` (نسخهٔ نصب‌شده: `uipro 2.15.0`) |
| روش نصب | `npm config set prefix /home/user/.local` → `npm i -g ui-ux-pro-max-cli` |
| دستور فعال‌سازی | `uipro init --ai universal --global` |
| محل نصب | `/home/user/.agents/skills/ui-ux-pro-max/` |
| فایل اصلی | `/home/user/.agents/skills/ui-ux-pro-max/SKILL.md` (۴۲۵ خط) |
| دادهٔ قابل‌جست‌وجو | `ui-ux-pro-max/data/*.csv` (styles, colors, typography, landing, product, ux, google-fonts, …) |
| اسکریپت | `ui-ux-pro-max/scripts/search.py` (Python 3، فقط stdlib) |
| مهارت‌های همراه | `brand`, `design`, `design-system`, `ui-styling`, `slides`, `banner-design` |

بررسی فعال‌بودن: `python3 scripts/search.py --help` اجرا شد و همهٔ دامنه‌ها
(`style, color, chart, landing, product, ux, typography, icons, gsap, react,
web, google-fonts`) و ۲۲ استک پاسخ دادند؛ سپس ۱۳ جست‌وجوی واقعی اجرا شد.

## ۲) توصیه‌هایی که Skill داد و **کجا** اعمال شد

| # | جست‌وجو | نتیجهٔ بازیابی‌شده | اعمال در |
|---|---|---|---|
| ۱ | `--design-system "medical education student learning platform"` | الگوی **Feature-Rich Showcase** + سبک **Claymorphism** + پالت ایندیگو/نارنجی + فونت Baloo 2 | **رد شد** — برای محصول آموزشیِ جدیِ بزرگسال و برند آبی/فیروزه‌ای نامناسب بود؛ طبق «Query Contract» خودِ اسکیل، جست‌وجو باریک‌تر شد ↓ |
| ۲ | `--domain product "medical university exam platform professional"` | **Accessible & Ethical + Minimalism & Swiss Style** · الگوی لندینگ **Trust & Authority + Conversion** · پالت *Medical Blue + Trust White + Calm Green* | مبنای لندینگ (`src/landing/Landing.jsx`) |
| ۳ | `--domain style "accessible ethical minimalism swiss style"` | فضای سفید، شبکه، بدون سایه/گرادیان تزئینی، هاور ۲۰۰–۲۵۰ms، کنتراست بالا، ریسک دسترس‌پذیری: کم | `src/landing/landing.css` |
| ۴ | `--domain landing "trust authority conversion medical"` | ترتیب بخش‌ها: **Hero (مأموریت) → Proof → Solution overview → CTA روشن**؛ لهجه فقط برای CTA | ترتیب بخش‌های لندینگ (تست `test_landing_sections_follow_trust_authority_order` قفلش کرده) |
| ۵ | `--domain color "medical blue trust calm green"` | Medical teal `#0891B2` + secondary `#22D3EE` + accent `#16A34A` + بک‌گراند روشن | **فقط ساختار نقش‌ها** گرفته شد؛ مقادیر هگز برند خودت (`--hym-brand-default: #3D86FF`، `--hym-accent-default: #2ADAD7`) نگه داشته شد — چون «حفظ هویت آبی/فیروزه‌ای هامزیار» شرط قطعی تو بود |
| ۶ | `--domain typography "persian arabic bilingual"` / `--domain google-fonts "vazirmatn arabic"` | برای RTL: خانوادهٔ Sans عربی؛ **Vazirmatn** (Saber Rastikerdar، زیرمجموعهٔ arabic/latin) | همان فونت خودمیزبانی که در مخزن بود؛ **باگ سرو شدنش اصلاح شد** (پایین) |
| ۷ | `--domain ux "focus visible keyboard navigation"` | حلقهٔ فوکوس قابل‌مشاهده روی هر کنترل، ممنوعیت `outline:none` بدون جایگزین؛ شدت: بالا | `landing.css` + تست فوکوس؛ کلید Tab روی skip-link تست شد |
| ۸ | `--domain ux "form validation error message"` | خطا با `role=alert`، متن خطا **به فیلد وصل** شود، فوکوس بعد از خطا مدیریت شود | `WebLogin.jsx`: `id="pwa-auth-error"` + `aria-invalid` + `aria-describedby` |
| ۹ | `--domain ux "reduced motion animation"` | احترام به `prefers-reduced-motion`؛ حداکثر ۱–۲ انیمیشن در هر نما | `landing.css` + تست با `reduced_motion="reduce"` |
| ۱۰ | `--domain ux "touch target size mobile"` | iOS ۴۴pt / Android ۴۸dp / وب ≥۲۴px + فاصلهٔ ۸px | همهٔ دکمه‌ها/لینک‌های لندینگ `min-height: 44px` (تست اندازه گرفت) |
| ۱۱ | `--domain ux "right to left rtl layout"` | مراقبت از عناصر fixed، واحدهای viewport (`dvh` به‌جای `vh`) | `100dvh` در لندینگ و PWA؛ تست RTL در ۴ عرض |
| ۱۲ | `--stack react "accessible focus keyboard component"` | مدیریت فوکوس در مودال، کوئری‌های دسترس‌پذیر در تست | فوکوس خودکار فیلد کد پس از خطا (از قبل بود، تثبیت شد) |

## ۳) تصمیم‌های طراحیِ نهایی هامزیار

* **الگو:** Trust & Authority + Conversion (Hero → اعتماد → امکانات → ساده‌ترین مسیر CTA)
* **سبک:** Minimax دسترس‌پذیر — فضای سفید، شبکهٔ ۱/۲/۳ ستونه، سایه‌های کم، یک لهجهٔ رنگی
* **رنگ:** آبی برند `#3D86FF` برای CTA، فیروزه‌ای `#2ADAD7` برای تأکید، سطوح `#060B16`/`#0C1526`
* **تایپوگرافی:** Vazirmatn · بدنه ۱۶px / line-height 1.85 (فارسی) · h1 `clamp(28px,5.2vw,52px)`
* **حرکت:** ترنزیشن ۲۰۰ms، بدون انیمیشن ورودی سنگین، با `prefers-reduced-motion` خنثی
* **RTL:** `dir="rtl"` + ویژگی‌های منطقی (`inset-inline-start`, `border-inline-start`)
* **دسترس‌پذیری:** skip-link، یک `h1`، فوکوس رسم‌دار، هدف لمسی ۴۴px، alt روی تصاویر تزئینی
* **آنچه عمداً انجام نشد:** هیچ کتابخانهٔ UI/فونت/CDN تازه‌ای اضافه نشد؛ هیچ کامپوننت اپ بازنویسی نشد.

## ۴) محدودیت‌های همین اجرا

* Skill در محیط **Arena** نصب شد (Universal Agent Skills → `~/.agents/skills/`)؛
  Arena فهرست مهارت‌ها را به‌صورت خودکار «کشف» نمی‌کند، پس فعال‌سازی در این
  جلسه با **اجرای واقعی اسکریپت‌های همان Skill** و اعمال خروجی‌شان انجام شد،
  نه با auto-activation.
* خروجی Skill «راهنمای طراحی» است، نه کد؛ بازنویسی کامپوننت‌ها دستی و با
  توکن‌های موجود مخزن انجام شد.
