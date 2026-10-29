/* ─────────────────────────────────────────────────────────────
   📅 HumsYar v3 — موتور برنامهٔ هفتگی (Weekly Timetable Engine)

   چرا این فایل جدا شد؟
   ─────────────────────
   صفحهٔ قبلی «فهرست تاریخ‌ها» بود: ۲۹۹ جلسه پشت سر هم، هر جلسه یک
   کارت بزرگ ⇒ کاربر باید صدها بار اسکرول می‌کرد تا بفهمد «سه‌شنبه
   ساعت ۱۰ چه کلاسی دارم». چیزی که یک برنامهٔ درسی باید بدهد دقیقاً
   برعکس است: **یک نگاه = یک هفته**.

   این ماژول همان لایهٔ منطقی است (بدون JSX) تا هم تست‌پذیر باشد و هم
   صفحه فقط نمایش بماند:

     buildWeek(items)   → الگوی تکرارشوندهٔ هفتگی از روی تاریخ‌های واقعی
     buildStats(items)  → شمارش جلسه/درس/استاد/روز + بار هر روز
     buildLessonTable() → جدول مرتب‌شده بر اساس درس (برای نمای «جدول»)

   ⚠️ هیچ داده‌ای ساخته نمی‌شود: اگر روزی کلاس ندارد، خالی می‌ماند.
   ───────────────────────────────────────────────────────────── */

/* ترتیب هفتهٔ ایرانی: شنبه اول، جمعه آخر (Index در Date.getDay) */
export const WEEK = [
  { key: 'sat', d: 6, short: 'ش', name: 'شنبه' },
  { key: 'sun', d: 0, short: 'ی', name: 'یک‌شنبه' },
  { key: 'mon', d: 1, short: 'د', name: 'دوشنبه' },
  { key: 'tue', d: 2, short: 'س', name: 'سه‌شنبه' },
  { key: 'wed', d: 3, short: 'چ', name: 'چهارشنبه' },
  { key: 'thu', d: 4, short: 'پ', name: 'پنج‌شنبه' },
  { key: 'fri', d: 5, short: 'ج', name: 'جمعه' },
];

const WEEK_BY_JS_DAY = Object.fromEntries(WEEK.map((w) => [w.d, w]));

/* «۱۴:۳۰» یا «14:30» → ۸۷۰ دقیقه (برای مرتب‌سازی و محاسبهٔ ارتفاع) */
export function toMinutes(value) {
  const match = String(value || '').match(/(\d{1,2}):(\d{2})/);
  if (!match) return null;
  const hours = Number(match[1]);
  const minutes = Number(match[2]);
  if (hours > 23 || minutes > 59) return null;
  return hours * 60 + minutes;
}

/* دقیقه → «HH:MM» فارسی‌پسند (همان قالب دادهٔ سرور) */
export function fromMinutes(total) {
  if (total === null || total === undefined) return '';
  const h = Math.floor(total / 60);
  const m = total % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

/* روز هفتهٔ یک تاریخ ISO (YYYY-MM-DD) — بدون وابستگی به ساعت کاربر */
export function weekdayOf(iso) {
  const raw = String(iso || '').slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(raw)) return null;
  const [y, m, d] = raw.split('-').map(Number);
  const date = new Date(Date.UTC(y, m - 1, d));
  if (Number.isNaN(date.getTime())) return null;
  return WEEK_BY_JS_DAY[date.getUTCDay()] || null;
}

/* ── کلید یکتای یک «کلاس» (برای اینکه ۱۶ هفته تکرار یک درس،
      در جدول هفتگی ۱۶ بار شمرده نشود) ── */
function slotKey(item) {
  return [
    item.lesson || '',
    item.group || '',
    item.teacher || '',
    item.time || '',
    item.type || 'class',
  ].join('|');
}

/**
 * الگوی هفتگی: هر خانه = (روز، ساعت شروع) با فهرست درس‌های آن.
 *
 * @param {Array} items جلسه‌های خام سرور
 * @returns {{rows, days, totalSessions, maxPerDay, byDay}}
 */
export function buildWeek(items = []) {
  const cells = new Map();     // `${weekdayKey}|${time}` → Map(slotKey → slot)
  const byDay = Object.fromEntries(WEEK.map((w) => [w.key, []]));
  const times = new Set();
  let totalSessions = 0;

  for (const item of items) {
    const day = weekdayOf(item?.date);
    const start = toMinutes(item?.time);
    if (!day || start === null) continue;

    const end = toMinutes(item?.end_time || item?.time_end) ?? start + 60;
    times.add(start);

    const bucket = `${day.key}|${start}`;
    if (!cells.has(bucket)) cells.set(bucket, new Map());

    const slot = {
      lesson: item.lesson || 'بدون عنوان',
      teacher: item.teacher || '',
      group: item.group || '',
      location: item.location || '',
      type: item.type || 'class',
      start,
      end,
      // شمارش جلسه‌های واقعی همین درس در همین خانه (چند هفته)
      sessions: 1,
      dates: item.date ? [item.date] : [],
    };

    const key = slotKey(item);
    const existing = cells.get(bucket).get(key);

    if (existing) {
      existing.sessions += 1;
      if (item.date) existing.dates.push(item.date);
    } else {
      cells.get(bucket).set(key, slot);
      byDay[day.key].push(slot);
    }
    totalSessions += 1;
  }

  const rowTimes = [...times].sort((a, b) => a - b);
  const rows = rowTimes.map((start) => {
    const cellsRow = WEEK.map((day) => {
      const bucket = cells.get(`${day.key}|${start}`);
      return bucket ? [...bucket.values()].sort((a, b) => a.lesson.localeCompare(b.lesson, 'fa')) : [];
    });
    return { start, label: fromMinutes(start), cells: cellsRow };
  });

  const dayCounts = Object.fromEntries(
    WEEK.map((w) => [w.key, cells.size ? countSessionsFor(rows, w.key) : 0]),
  );

  return {
    rows,
    days: WEEK,
    totalSessions,
    byDay,
    daySessions: dayCounts,
    maxPerDay: Math.max(1, ...Object.values(dayCounts)),
    hasAny: rows.length > 0,
  };
}

function countSessionsFor(rows, dayKey) {
  const index = WEEK.findIndex((w) => w.key === dayKey);
  let total = 0;
  for (const row of rows) {
    for (const slot of row.cells[index] || []) total += slot.sessions;
  }
  return total;
}

/**
 * آمار کلی: برای هدر «چند کلاس، چند درس، چند استاد».
 * `totalSessions` همان عددی است که کاربر انتظار دارد (مثل ۲۹۹).
 */
export function buildStats(items = []) {
  const lessons = new Set();
  const teachers = new Set();
  const days = new Set();
  const groups = new Set();
  let withTime = 0;

  for (const item of items) {
    if (item?.lesson) lessons.add(item.lesson);
    if (item?.teacher) teachers.add(item.teacher);
    if (item?.group) groups.add(String(item.group));
    if (item?.date) days.add(String(item.date).slice(0, 10));
    if (toMinutes(item?.time) !== null) withTime += 1;
  }

  const week = buildWeek(items);

  return {
    sessions: items.length,
    lessons: lessons.size,
    teachers: teachers.size,
    activeDays: days.size,
    groups: [...groups].sort(),
    withTime,
    week,
  };
}

/**
 * جدول درس‌ها: هر درس یک ردیف، همهٔ روز/ساعت‌هایش کنار هم،
 * مرتب بر اساس اولین روز و ساعتِ هفته (نه الفبایی) — چون آدم
 * برنامه را زمانی می‌خواند، نه دیکشنری‌وار.
 */
export function buildLessonTable(items = []) {
  const map = new Map();

  for (const item of items) {
    const name = item?.lesson || 'بدون عنوان';
    const start = toMinutes(item?.time);
    const day = weekdayOf(item?.date);

    if (!map.has(name)) {
      map.set(name, {
        lesson: name,
        teacher: item?.teacher || '',
        group: item?.group || '',
        location: item?.location || '',
        slots: new Map(),
        sessions: 0,
      });
    }

    const row = map.get(name);
    row.sessions += 1;
    if (!row.teacher && item?.teacher) row.teacher = item.teacher;
    if (!row.group && item?.group) row.group = item.group;
    if (!row.location && item?.location) row.location = item.location;

    if (day && start !== null) {
      const key = `${day.d}|${start}`;
      if (!row.slots.has(key)) {
        row.slots.set(key, { dayIndex: WEEK.findIndex((w) => w.key === day.key), day, start });
      }
    }
  }

  return [...map.values()]
    .map((row) => ({
      ...row,
      slots: [...row.slots.values()].sort(
        (a, b) => a.dayIndex - b.dayIndex || a.start - b.start,
      ),
    }))
    .sort((a, b) => {
      const aFirst = a.slots[0] || { dayIndex: 9, start: 9999 };
      const bFirst = b.slots[0] || { dayIndex: 9, start: 9999 };
      return aFirst.dayIndex - bFirst.dayIndex || aFirst.start - bFirst.start
        || a.lesson.localeCompare(b.lesson, 'fa');
    });
}

/* رنگ ثابت هر درس — از نام ساخته می‌شود تا در هر رفرش یکسان بماند */
const PALETTE = [
  { bg: 'rgba(61,134,255,.18)', fg: '#9CC3FF', line: 'rgba(61,134,255,.42)' },
  { bg: 'rgba(42,218,215,.16)', fg: '#6FE6E3', line: 'rgba(42,218,215,.40)' },
  { bg: 'rgba(47,208,154,.16)', fg: '#5EDDB2', line: 'rgba(47,208,154,.40)' },
  { bg: 'rgba(242,178,75,.16)', fg: '#F5C877', line: 'rgba(242,178,75,.40)' },
  { bg: 'rgba(196,181,253,.16)', fg: '#C9BEFF', line: 'rgba(196,181,253,.40)' },
  { bg: 'rgba(255,107,122,.16)', fg: '#FF9AA4', line: 'rgba(255,107,122,.40)' },
];

export function lessonTone(lesson) {
  let hash = 0;
  const text = String(lesson || '');
  for (let i = 0; i < text.length; i += 1) {
    hash = (hash * 31 + text.charCodeAt(i)) % 100000;
  }
  return PALETTE[hash % PALETTE.length];
}

/* «زبان پیش دانشگاهی (۲)» → «زبان پیش‌دانشگاهی» برای خانه‌های باریک */
export function shortLesson(lesson, max = 14) {
  const text = String(lesson || '')
    .replace(/[()۰-۹0-9]/g, ' ')
    .replace(/[-–—]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}
