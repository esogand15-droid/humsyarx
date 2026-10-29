/* ─────────────────────────────────────────────────────────────
   📲 حالت اجرا — «داخل تلگرام» یا «نسخهٔ نصب‌شدنی وب (PWA)»

   یک کد، دو بیلد:
     npm run build       → VITE_APP_MODE=miniapp → /app/    (تلگرام)
     npm run build:pwa   → VITE_APP_MODE=pwa     → /pwa/    (iOS/Android/Windows)

   تفاوت‌ها فقط در همین پرچم است، نه در صفحات: هر صفحه و هر منطق
   تجاری یکی است؛ فقط «چطور وارد شویم» و «چطور نصب کنیم» فرق می‌کند.
   ───────────────────────────────────────────────────────────── */

export const APP_MODE = import.meta.env.VITE_APP_MODE || 'miniapp';

export const IS_PWA = APP_MODE === 'pwa';

/** آدرس manifest همین بیلد (در index.html هم استفاده می‌شود). */
export const MANIFEST_HREF = './manifest.webmanifest';

/** آدرس عمومی ربات — برای دکمهٔ «باز کردن در تلگرام». */
export const BOT_URL = (import.meta.env.VITE_BOT_URL || 'https://t.me/').trim();

/** آیا اپ نصب‌شده (standalone) اجرا می‌شود؟ */
export function isStandalone() {
  if (typeof window === 'undefined') return false;
  try {
    return (
      window.matchMedia?.('(display-mode: standalone)').matches ||
      window.navigator.standalone === true ||
      window.matchMedia?.('(display-mode: window-controls-overlay)').matches ||
      window.matchMedia?.('(display-mode: minimal-ui)').matches
    );
  } catch (_) {
    return false;
  }
}

/** تشخیص سکو — فقط برای متن راهنمای نصب، نه برای تغییر رفتار. */
export function platform() {
  if (typeof navigator === 'undefined') return 'web';
  const ua = navigator.userAgent || '';
  const iOS = /iPad|iPhone|iPod/.test(ua) ||
    (navigator.platform === 'MacIntel' && (navigator.maxTouchPoints || 0) > 1);
  if (iOS) return 'ios';
  if (/Android/i.test(ua)) return 'android';
  if (/Windows/i.test(ua)) return 'windows';
  if (/Macintosh|Mac OS X/i.test(ua)) return 'mac';
  return 'web';
}
