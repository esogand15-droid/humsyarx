/* ═══════════════════════════════════════════════════════
   اسپرایت آیکون‌ها — ۳۴ آیکون اختصاصی + نشانهٔ برند
   شبکهٔ ۲۴×۲۴ · استروک ۱.۷ · fill:none · currentColor
   منبع: نمونهٔ تأییدشدهٔ «مرکب» (design-system/03-components)
   ═══════════════════════════════════════════════════════ */

export const ICON_NAMES = [
  'logo-mark',
  'i-arch',
  'i-home',
  'i-book',
  'i-flask',
  'i-calendar',
  'i-user',
  'i-bell',
  'i-chat',
  'i-card',
  'i-search',
  'i-headphones',
  'i-video',
  'i-doc',
  'i-download',
  'i-upload',
  'i-bookmark',
  'i-pen',
  'i-highlighter',
  'i-eraser',
  'i-chevron',
  'i-chevron-r',
  'i-check',
  'i-lock',
  'i-settings',
  'i-clock',
  'i-play',
  'i-grid',
  'i-logout',
  'i-trend',
  'i-layers',
  'i-code',
  'i-copy',
  'i-moon',
  'i-sun',
] as const;

export type IconName = (typeof ICON_NAMES)[number];

/** یک‌بار در ریشهٔ اپ رندر می‌شود؛ همهٔ آیکون‌ها با <use href="#id"> از آن می‌آیند. */
export function IconSprite() {
  return (
    <svg width="0" height="0" aria-hidden="true" focusable="false" style={{ position: 'absolute' }}>
      <symbol id="logo-mark" viewBox="0 0 24 24">
      <path d="M12 12.4c-2.3-1.3-5-1.6-7.7-.8v7.1c2.7-.8 5.4-.5 7.7.8 2.3-1.3 5-1.6 7.7-.8V11.6c-2.7-.8-5.4-.5-7.7.8z"
      fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinejoin="round"/>
      <path d="M12 4.2v9" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
      <circle cx="12" cy="3.3" r="1.4" fill="none" stroke="currentColor" strokeWidth="1.7"/>
      <path d="M9.2 7.4c1.7-1 3.9-1 5.6 0" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
      </symbol>
      <symbol id="i-arch" viewBox="0 0 24 24"><path d="M5.2 19V10.7a6.8 6.8 0 0 1 13.6 0V19"/><path d="M3.2 19h17.6"/><path d="M10.2 14.6h3.6"/></symbol>
      <symbol id="i-home" viewBox="0 0 24 24"><path d="M4.6 19.4V11a7.4 7.4 0 0 1 14.8 0v8.4"/><path d="M3 19.4h18"/><path d="M9.6 19.4v-4.2a2.4 2.4 0 0 1 4.8 0v4.2"/></symbol>
      <symbol id="i-book" viewBox="0 0 24 24"><path d="M4 5.4h5.4A2.6 2.6 0 0 1 12 8v12a2.4 2.4 0 0 0-2.4-2.4H4z"/><path d="M20 5.4h-5.4A2.6 2.6 0 0 0 12 8v12a2.4 2.4 0 0 1 2.4-2.4H20z"/></symbol>
      <symbol id="i-flask" viewBox="0 0 24 24"><path d="M9.2 3.2h5.6"/><path d="M10.1 3.2v6.1L5.7 17a3 3 0 0 0 2.6 4.4h7.4a3 3 0 0 0 2.6-4.4l-4.4-7.7V3.2"/><path d="M7.6 14.6h8.8"/></symbol>
      <symbol id="i-calendar" viewBox="0 0 24 24"><rect x="3.4" y="5.4" width="17.2" height="15.2" rx="3"/><path d="M3.4 10.4h17.2"/><path d="M8.2 3.4v4M15.8 3.4v4"/><path d="M7.6 14.2h2.2M14.2 14.2h2.2M7.6 17.4h2.2"/></symbol>
      <symbol id="i-user" viewBox="0 0 24 24"><circle cx="12" cy="8.4" r="3.8"/><path d="M4.8 20.2c.8-3.6 3.7-5.6 7.2-5.6s6.4 2 7.2 5.6"/></symbol>
      <symbol id="i-bell" viewBox="0 0 24 24"><path d="M6.6 16.6V11a5.4 5.4 0 0 1 10.8 0v5.6"/><path d="M4.4 16.6h15.2"/><path d="M9.9 19.9a2.1 2.1 0 0 0 4.2 0"/></symbol>
      <symbol id="i-chat" viewBox="0 0 24 24"><path d="M4 6.6a3 3 0 0 1 3-3h10a3 3 0 0 1 3 3v6.8a3 3 0 0 1-3 3h-4.6L7.2 20.5v-4.1H7a3 3 0 0 1-3-3z"/></symbol>
      <symbol id="i-card" viewBox="0 0 24 24"><rect x="3" y="6" width="18" height="12" rx="3"/><path d="M3 10.4h18"/><path d="M6.4 15h3.2"/></symbol>
      <symbol id="i-search" viewBox="0 0 24 24"><circle cx="11" cy="11" r="6.2"/><path d="M15.6 15.6 20.2 20.2"/></symbol>
      <symbol id="i-headphones" viewBox="0 0 24 24"><path d="M4.6 15.2v-3.4a7.4 7.4 0 0 1 14.8 0v3.4"/><rect x="2.8" y="14" width="4" height="6.2" rx="2"/><rect x="17.2" y="14" width="4" height="6.2" rx="2"/></symbol>
      <symbol id="i-video" viewBox="0 0 24 24"><rect x="3" y="6.6" width="12.4" height="10.8" rx="2.6"/><path d="m15.4 11.6 5.6-2.9v6.6l-5.6-2.9z"/></symbol>
      <symbol id="i-doc" viewBox="0 0 24 24"><path d="M6.2 4.6a2 2 0 0 1 2-2h5.4L19 8v11.4a2 2 0 0 1-2 2H8.2a2 2 0 0 1-2-2z"/><path d="M13.6 2.7V8H19"/><path d="M9 12.4h6M9 15.9h4"/></symbol>
      <symbol id="i-download" viewBox="0 0 24 24"><path d="M12 3.6v10"/><path d="m8 9.8 4 4 4-4"/><path d="M4.6 16.8v1.6a2 2 0 0 0 2 2h10.8a2 2 0 0 0 2-2v-1.6"/></symbol>
      <symbol id="i-upload" viewBox="0 0 24 24"><path d="M12 20.4V10.4"/><path d="m8 14.2 4-4 4 4"/><path d="M4.6 7.2V5.6a2 2 0 0 1 2-2h10.8a2 2 0 0 1 2 2v1.6"/></symbol>
      <symbol id="i-bookmark" viewBox="0 0 24 24"><path d="M7 3.6h10a1.4 1.4 0 0 1 1.4 1.4v16L12 16.9 5.6 21V5A1.4 1.4 0 0 1 7 3.6z"/></symbol>
      <symbol id="i-pen" viewBox="0 0 24 24"><path d="M15.6 3.9a2 2 0 0 1 2.85 0l1.65 1.65a2 2 0 0 1 0 2.85L9.5 19.1l-4.6 1.4 1.4-4.6z"/><path d="m14.1 5.4 4.5 4.5"/></symbol>
      <symbol id="i-highlighter" viewBox="0 0 24 24"><path d="m6 14.4 8.8-8.8a2 2 0 0 1 2.8 0l.8.8a2 2 0 0 1 0 2.8L9.6 18"/><path d="M4 21h8"/><path d="m6 14.4 3.6 3.6"/></symbol>
      <symbol id="i-eraser" viewBox="0 0 24 24"><path d="M8.4 19.6 3.9 15.1a2 2 0 0 1 0-2.8l7-7a2 2 0 0 1 2.8 0l4.4 4.4a2 2 0 0 1 0 2.8l-7.2 7.1z"/><path d="m8.1 9.6 6.4 6.4"/><path d="M8.4 19.6H20"/></symbol>
      <symbol id="i-chevron" viewBox="0 0 24 24"><path d="M14.4 5.6 8 12l6.4 6.4"/></symbol>
      <symbol id="i-chevron-r" viewBox="0 0 24 24"><path d="M9.6 5.6 16 12l-6.4 6.4"/></symbol>
      <symbol id="i-check" viewBox="0 0 24 24"><path d="m4.6 12.4 5 5 9.8-10.8"/></symbol>
      <symbol id="i-lock" viewBox="0 0 24 24"><rect x="4.6" y="10" width="14.8" height="10.4" rx="3"/><path d="M8.1 10V7.9a3.9 3.9 0 0 1 7.8 0V10"/></symbol>
      <symbol id="i-settings" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3.1"/><path d="M12 2.8v2.5M12 18.7v2.5M21.2 12h-2.5M5.3 12H2.8M18.5 5.5l-1.8 1.8M7.3 16.7l-1.8 1.8M18.5 18.5l-1.8-1.8M7.3 7.3 5.5 5.5"/></symbol>
      <symbol id="i-clock" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.2"/><path d="M12 7.6V12l3 2"/></symbol>
      <symbol id="i-play" viewBox="0 0 24 24"><path d="M8 5.4v13.2l10-6.6z"/></symbol>
      <symbol id="i-grid" viewBox="0 0 24 24"><rect x="4" y="4" width="7" height="7" rx="2"/><rect x="13" y="4" width="7" height="7" rx="2"/><rect x="4" y="13" width="7" height="7" rx="2"/><rect x="13" y="13" width="7" height="7" rx="2"/></symbol>
      <symbol id="i-logout" viewBox="0 0 24 24"><path d="M13.6 20.4H6.6a2 2 0 0 1-2-2V5.6a2 2 0 0 1 2-2h7"/><path d="M10 12h10"/><path d="m16.6 8.4 3.6 3.6-3.6 3.6"/></symbol>
      <symbol id="i-trend" viewBox="0 0 24 24"><path d="M3.6 16.4 9 11l3.6 3.4 7.2-7.4"/><path d="M15.6 7h4.4v4.4"/></symbol>
      <symbol id="i-layers" viewBox="0 0 24 24"><path d="M12 3.4 3.8 7.6 12 11.8l8.2-4.2z"/><path d="m3.8 12.4 8.2 4.2 8.2-4.2"/><path d="m3.8 16.8 8.2 4.2 8.2-4.2"/></symbol>
      <symbol id="i-code" viewBox="0 0 24 24"><path d="m8.6 8-4 4 4 4"/><path d="m15.4 8 4 4-4 4"/></symbol>
      <symbol id="i-copy" viewBox="0 0 24 24"><rect x="8.4" y="8.4" width="12" height="12" rx="2.6"/><path d="M15.6 5.6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v7.6a2 2 0 0 0 2 2"/></symbol>
      <symbol id="i-moon" viewBox="0 0 24 24"><path d="M20 14.4A8 8 0 0 1 9.6 4 8.2 8.2 0 1 0 20 14.4z"/></symbol>
      <symbol id="i-sun" viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"/><path d="M12 2.8v2.4M12 18.8v2.4M21.2 12h-2.4M5.2 12H2.8M18.5 5.5l-1.7 1.7M7.2 16.8l-1.7 1.7M18.5 18.5l-1.7-1.7M7.2 7.2 5.5 5.5"/></symbol>
    </svg>
  );
}
