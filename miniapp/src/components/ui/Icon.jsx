/* ─────────────────────────────────────────────────────────────
   🎨 HumsYar v3 — مجموعهٔ آیکون خطی (Design System یکپارچه)

   چرا SVG و نه ایموجی؟
   ایموجی‌ها بین اندروید/iOS/دسکتاپ شکل و اندازهٔ متفاوت دارند،
   در RTL جابه‌جا می‌شوند و رنگ برند را نمی‌گیرند. پروتوتایپ آبی
   سراسر از آیکون‌های خطی ۲۴×۲۴ با ضخامت ۱.۷ استفاده می‌کند؛
   همین زبان بصری در وب‌اپ و مینی‌اپ بازتولید می‌شود.

   قرارداد:
   • اندازه پیش‌فرض ۲۰px، رنگ = currentColor (پس خودکار با متن
     هم‌رنگ می‌شود: فعال/غیرفعال/هشدار).
   • `stroke-linecap="round"` + `stroke-linejoin="round"` = نفسِ
     بصری پروتوتایپ.
   • هیچ آیکونی از کتابخانهٔ بیرونی نیامده — سبک و بدون وابستگی
     جدید (الزام پروژه).
   ───────────────────────────────────────────────────────────── */

const PATHS = {
  home: 'M3.6 10.4 12 3.8l8.4 6.6V20a.9.9 0 0 1-.9.9h-5v-5.6h-4.9V21h-5a.9.9 0 0 1-.9-.9z',
  book: 'M4 4.8A1.8 1.8 0 0 1 5.8 3h5.4a2.8 2.8 0 0 1 2.8 2.8V21H6.6A2.6 2.6 0 0 0 4 23.6zM20 4.8A1.8 1.8 0 0 0 18.2 3h-5.4A2.8 2.8 0 0 0 10 5.8V21h7.4A2.6 2.6 0 0 1 20 23.6z',
  calendar: 'M4 8.4h16M7.5 3v3M16.5 3v3M4.9 5.4h14.2A1.9 1.9 0 0 1 21 7.3v12.4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7.3a1.9 1.9 0 0 1 1.9-1.9z',
  chart: 'M4 20V9.6M9.4 20V4.6M14.8 20v-7.2M20.2 20v-4.4',
  chartBars: 'M4.4 14.6h3v6.2h-3zM10.6 8.2h3v12.6h-3zM16.8 11.4h3v9.4h-3z',
  user: 'M12 11.6a4.1 4.1 0 1 0 0-8.2 4.1 4.1 0 0 0 0 8.2zM4.6 21c.5-3.7 3.6-6 7.4-6s6.9 2.3 7.4 6',
  sparkle: 'M12 3.2 13.7 8l4.8 1.7-4.8 1.9L12 16.4 10.3 11.6 5.5 9.7 10.3 8zM18.4 15.2l.9 2.4 2.4.9-2.4.9-.9 2.4-.9-2.4-2.4-.9 2.4-.9z',
  bell: 'M18 15.2V10a6 6 0 1 0-12 0v5.2L4.4 18h15.2zM9.6 20.6a2.6 2.6 0 0 0 4.8 0',
  moon: 'M20 14.2A8.4 8.4 0 0 1 9.8 4a8.6 8.6 0 1 0 10.2 10.2z',
  sun: 'M12 16.4a4.4 4.4 0 1 0 0-8.8 4.4 4.4 0 0 0 0 8.8zM12 2.6v2.2M12 19.2v2.2M4.3 12H2.1M21.9 12h-2.2M6.5 6.5 5 5M19 19l-1.5-1.5M6.5 17.5 5 19M19 5l-1.5 1.5',
  search: 'M11 18.2a7.2 7.2 0 1 0 0-14.4 7.2 7.2 0 0 0 0 14.4zM16.4 16.4 21 21',
  doc: 'M6.4 3.4h7.2L19 8.8v11.8H6.4zM13.4 3.6V9h5.2M9 13h7M9 16.6h7',
  clock: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7.6V12l3.2 2',
  arrowLeft: 'M19.4 12H5M11 5.6 4.6 12l6.4 6.4',
  arrowRight: 'M4.6 12h14.4M13 5.6 19.4 12 13 18.4',
  arrowUp: 'M12 5v14M6 11l6-6 6 6',
  chevronLeft: 'M14.6 6 8.6 12l6 6',
  plus: 'M12 5.4v13.2M5.4 12h13.2',
  play: 'M8.6 5.6 18 12l-9.4 6.4z',
  quiz: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM9.7 9.3a2.4 2.4 0 1 1 3.4 2.2c-.7.4-1 .9-1 1.7M12 17h.01',
  wallet: 'M4 8.4h14.4a1.6 1.6 0 0 1 1.6 1.6v7.6a2 2 0 0 1-2 2H5.6a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h11.2M16.4 13.6h.01',
  ticket: 'M4 9.4V7.6A1.6 1.6 0 0 1 5.6 6h12.8A1.6 1.6 0 0 1 20 7.6v1.8a2.6 2.6 0 0 0 0 5.2v1.8a1.6 1.6 0 0 1-1.6 1.6H5.6A1.6 1.6 0 0 1 4 18.2v-1.8a2.6 2.6 0 0 0 0-5.2zM12 9v6',
  shield: 'M12 3 5.4 5.6v5.6c0 4.2 2.8 7.5 6.6 9 3.8-1.5 6.6-4.8 6.6-9V5.6z',
  target: 'M12 20.6a8.6 8.6 0 1 0 0-17.2 8.6 8.6 0 0 0 0 17.2zM12 16.4a4.4 4.4 0 1 0 0-8.8 4.4 4.4 0 0 0 0 8.8zM12 13.4a1.4 1.4 0 1 0 0-2.8 1.4 1.4 0 0 0 0 2.8z',
  flame: 'M12 21c3.4 0 6-2.4 6-5.6 0-4.4-4.2-6-4.2-9.6-2 .6-3.4 2.6-3.4 4.6 0 1-.7 1.7-1.4 1.7-.9 0-1.5-.8-1.5-1.9C6.4 12 6 13.4 6 15.4 6 18.6 8.6 21 12 21z',
  download: 'M12 4v10.4M7.6 10.4 12 14.8l4.4-4.4M5 19.4h14',
  menu: 'M4 7h16M4 12h16M4 17h16',
  layers: 'M12 3.6 3.6 8.2 12 12.8l8.4-4.6zM3.6 12.6 12 17.2l8.4-4.6M3.6 17 12 21.6l8.4-4.6',
  refresh: 'M20 12a8 8 0 1 1-2.6-5.9M20 4v4.2h-4.2',
  info: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 11v5.4M12 7.6h.01',
  check: 'M5 12.6 10 17.4 19 7.4',
  close: 'M6.4 6.4 17.6 17.6M17.6 6.4 6.4 17.6',
  logout: 'M15 8V5.6H5v12.8h10V16M11.6 12h9M17.6 8.6 21 12l-3.4 3.4',
  image: 'M4.6 5.4h14.8v13.2H4.6zM4.8 15.6 9.4 11l3 3 2.4-2.4 3.8 3.8M9 9.6h.01',
  settings: 'M12 15.2a3.2 3.2 0 1 0 0-6.4 3.2 3.2 0 0 0 0 6.4zM19.2 12c0 .5 0 .9-.1 1.4l2 1.5-1.9 3.3-2.4-1a7.8 7.8 0 0 1-2.4 1.4l-.4 2.5h-3.8l-.4-2.5A7.8 7.8 0 0 1 7.3 17l-2.4 1-1.9-3.3 2-1.5a8.6 8.6 0 0 1 0-2.8l-2-1.5L5 5.6l2.4 1A7.8 7.8 0 0 1 9.8 5.2l.4-2.5h3.8l.4 2.5a7.8 7.8 0 0 1 2.4 1.4l2.4-1 1.9 3.3-2 1.5c.1.5.1 1 .1 1.6z',
};

export default function Icon({
  name,
  size = 20,
  strokeWidth = 1.7,
  filled = false,
  className,
  style,
  ...rest
}) {
  const d = PATHS[name];

  if (!d) {
    // آیکون ناشناس = بی‌صدا خالی، نه کرش (اصل «هیچ صفحهٔ تاریک»)
    return null;
  }

  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      className={className}
      style={{ display: 'block', flex: 'none', ...style }}
      fill={filled ? 'currentColor' : 'none'}
      stroke="currentColor"
      strokeWidth={filled ? 0 : strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...rest}
    >
      <path d={d} />
    </svg>
  );
}

export const ICON_NAMES = Object.keys(PATHS);


/* ─────────────────────────────────────────────────────────────
   GLYPH MAP — پل مهاجرت از ایموجی به آیکون خطی

   چرا؟ ۱۳۰۰ ایموجی در ۷۰ فایل نمی‌شود یک‌شبه پاک کرد بدون اینکه
   چیزی بشکند. این نقشه همان معنای ایموجی را به آیکون خطی تبدیل
   می‌کند و کامپوننت `<Glyph>` هرجا داده‌ای مثل `icon: '📚'` هست
   آیکون می‌کشد — بدون تغییر شکل دادهٔ صفحه‌ها. هر ایموجی‌ای که
   نگاشت نداشته باشد، خودش رندر می‌شود (پس هیچ‌جا خالی نمی‌شود).
   ───────────────────────────────────────────────────────────── */
const GLYPHS = {
  '⚡': 'flame', '🎯': 'target', '📝': 'doc', '✏️': 'doc', '✍️': 'doc',
  '📗': 'book', '📘': 'book', '📚': 'book', '📄': 'doc', '🎓': 'book',
  '📅': 'calendar', '🕘': 'clock', '⏰': 'clock', '⏳': 'clock',
  '📊': 'chartBars', '📈': 'chart', '🧪': 'quiz', '❓': 'quiz',
  '💳': 'wallet', '💰': 'wallet', '🎫': 'ticket', '🎟️': 'ticket',
  '🔔': 'bell', '📨': 'bell', '🔍': 'search', '👤': 'user', '👥': 'user',
  '🛡️': 'shield', '🔒': 'shield', '🚩': 'shield', '⚠️': 'info',
  'ℹ️': 'info', '✅': 'check', '✓': 'check', '❌': 'close', '✕': 'close',
  '🗑️': 'close', '🚫': 'shield', '🔄': 'refresh', '↻': 'refresh',
  '📥': 'download', '🤖': 'sparkle', '✨': 'sparkle', '🧠': 'sparkle',
  '📌': 'layers', '🎨': 'image', '🖼️': 'image', '🗂️': 'layers',
  '🏆': 'target', '⭐': 'target', '💎': 'target', '👑': 'target',
  '🌱': 'chart', '🔥': 'flame', '🌊': 'layers', '🌐': 'layers',
  '⚙️': 'settings', '🔧': 'settings', '💾': 'download',
  '→': 'arrowRight', '←': 'arrowLeft', '⇒': 'arrowRight',
};

export function glyphName(value) {
  const raw = String(value || '').trim();
  if (!raw) return null;
  // اگر خودِ مقدار یک نام آیکون معتبر است (مثل 'target')، همان را بکش
  if (PATHS[raw]) return raw;
  if (GLYPHS[raw]) return GLYPHS[raw];
  // ایموجی با Variation Selector (U+FE0F) — بدون آن هم امتحان کن
  const stripped = raw.replace(/\uFE0F/g, '');
  return GLYPHS[stripped] || null;
}

/**
 * اگر ایموجی نگاشت داشته باشد آیکون خطی می‌کشد، وگرنه خودِ متن.
 * در RTL اندازه و تراز عمودی هماهنگ است.
 */
export function Glyph({ value, size = 18, style, className }) {
  const name = glyphName(value);

  if (!name) {
    return (
      <span className={className} style={{ lineHeight: 1, ...style }} aria-hidden="true">
        {value}
      </span>
    );
  }

  return (
    <Icon
      name={name}
      size={size}
      className={className}
      style={{ display: 'inline-block', verticalAlign: '-3px', ...style }}
    />
  );
}
