// ── lib/format — موج W2 Design Refactor
// تک‌منبع مشترک قالب‌بندی/امنیت مقدار برای کل مینی‌اپ.
// تا امروز این هلپرها در ۱۵+ فایل کپی شده بودند
// (faNum×۷، number×۱۳، percent×۳، errorText×۷، faDate×۲).
// قرارداد: پیاده‌سازی عیناً همان قبلی — رفتار صفر تغییر.


/* عدد امن نامنفی — برای شمارنده‌ها */
export const number = (value) => {
  const parsed = Number(value);

  return Number.isFinite(parsed)
    ? Math.max(0, parsed)
    : 0;
};


/* درصد امن ۰ تا ۱۰۰ */
export const percent = (value) =>
  Math.min(
    100,
    number(value)
  );


/* رقم‌های فارسی — نمایش هر مقدار */
export const faNum = (value) =>
  String(value ?? '').replace(
    /\d/g,
    (digit) => '۰۱۲۳۴۵۶۷۸۹'[digit]
  );


/* متن امن خطای سرور برای Toast */
export const errorText = (error, fallback) => {
  const detail =
    error?.response?.data?.detail;

  return typeof detail === 'string'
    ? detail
    : fallback;
};


/* تاریخ شمسی کوتاه — fallback قابل‌تنظیم
   (Roles: «—» / Profile: «») */
export const faDate = (iso, empty = '—') => {
  if (!iso) {
    return empty;
  }

  const time = new Date(iso).getTime();

  if (!Number.isFinite(time)) {
    return empty;
  }

  try {
    return new Date(
      time
    ).toLocaleDateString('fa-IR');
  } catch {
    return empty;
  }
};
