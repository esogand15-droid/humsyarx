# آپلود روی گیت‌هاب

این پوشه یک مخزن کامل و مستقل است: پس از آپلود، برای دیدن نسخهٔ اجرایی فقط `npm ci && npm run build` لازم است.

## الف) مخزن تازه (پیشنهادی)

```bash
unzip humsyar-prototype-v1.5.0-github.zip -d humsyar-proto
cd humsyar-proto

git init
git add .
git commit -m "هامزیار — پروتوتایپ v1.5.0"
git branch -M main
git remote add origin https://github.com/<username>/<repo>.git
git push -u origin main
```

`node_modules/`، `dist/` و `*.zip` در `.gitignore` هستند. فایل `humsyar-prototype.html` نسخهٔ تک‌فایلی و بدون هیچ درخواست بیرونی است (مناسب باز کردن با دوبار کلیک یا آپلود در هر دامنه).

## ب) شاخه‌ای در مخزن موجود

```bash
git checkout -b design/prototype-v1.5
git add .
git commit -m "prototype: mobile density pass v1.5"
git push -u origin design/prototype-v1.5
```

## ج) GitHub Pages (اختیاری، بدون سرور)

1. `npm run build` — مسیرها نسبی‌اند (`base: './'`)، پس در زیرمسیر گیت‌هاب هم درست کار می‌کنند.
2. پوشهٔ `dist/` را روی شاخهٔ `gh-pages` بگذارید.
3. Settings → Pages → Branch: `gh-pages` / root.

سرویس‌ورکر (`public/sw.js`) فقط در حالت production ثبت می‌شود و کشش نسبی است؛ برای اطمینان یک‌بار DevTools → Application → Service Workers را چک کنید.

## د) به‌روزرسانی وب‌اپ واقعی (دامنهٔ Railway)

این بسته پروتوتایپ طراحی است، نه خود وب‌اپ محصول. وب‌اپ زنده از مخزن بک‌اند سرو می‌شود؛ در `api/main.py` دو SPA mount می‌شود: `/app` از `miniapp/dist` و `/admin` از `webadmin/dist` (مسیر `/student` در کد فعلی mount نشده است). برای دیده‌شدن تغییرات روی دامنه:

1. کد این بسته را در مسیر فرانت‌اند همان مخزن (مثلاً `miniapp/`) قرار بدهید.
2. `npm ci && npm run build` در همان پوشه، و خروجی `dist/` را کامیت کنید (یا در مرحلهٔ build داکر اجرا شود).
3. `railway up` یا push به شاخهٔ متصل به Railway؛ سپس `GET /api/health` باید برای آن SPA مقدار `built: true` برگرداند.

بدون دسترسی push به آن مخزن این مرحله از سمت من انجام‌شدنی نیست؛ مراحل بالا دقیقاً همان کاری است که در دیپلوی اجرا می‌شود.
