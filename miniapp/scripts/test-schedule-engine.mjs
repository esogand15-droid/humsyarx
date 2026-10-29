#!/usr/bin/env node
/**
 * 🧪 تست موتور برنامهٔ هفتگی (بدون وابستگی به بستهٔ تست اضافه)
 *
 * چرا Node؟ منطق `scheduleEngine.js` خالص است و همان چیزی است که
 * صفحه از آن استفاده می‌کند؛ پس همین‌جا با دادهٔ واقعی‌شکل تست می‌شود
 * تا اشتباهی مثل «۲۹۹ جلسه = ۲۹۹ کارت» برنگردد.
 *
 * اجرا:  node scripts/test-schedule-engine.mjs
 */
import { readFileSync, writeFileSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';

const here = dirname(fileURLToPath(import.meta.url));
const src = join(here, '..', 'src', 'lib', 'scheduleEngine.js');

// ماژول ESM است ولی پروژه "type": "module" ندارد ⇒ یک کپی .mjs موقت
const dir = mkdtempSync(join(tmpdir(), 'hy-engine-'));
const tmp = join(dir, 'scheduleEngine.mjs');
writeFileSync(tmp, readFileSync(src, 'utf8'));

const E = await import(tmp);

let passed = 0;
const ok = (name, fn) => {
  fn();
  passed += 1;
  console.log(`  ✅ ${name}`);
};

console.log('scheduleEngine — تست واحد');

/* ── دادهٔ نمونه: ۸ درس، ۴ بازهٔ زمانی، ۱۴ هفته ── */
const LESSONS = [
  ['زبان پیش دانشگاهی (۲)', 'دکتر محمدی', '1'],
  ['فیزیولوژی پزشکی', 'دکتر نیکومنش', '1'],
  ['بیوشیمی ساختاری', 'دکتر صادقی', '2'],
  ['میکروب‌شناسی پزشکی', 'دکتر امیدی', '1'],
];
const TIMES = [['08:00', '10:00'], ['10:00', '12:00'], ['13:00', '15:00']];

const items = [];
let n = 0;
const start = Date.UTC(2026, 9, 24); // شنبه ۲۴ اکتبر ۲۰۲۶
for (let week = 0; week < 14; week += 1) {
  for (let wd = 0; wd < 6; wd += 1) {
    LESSONS.forEach(([lesson, teacher, group], i) => {
      if ((i + wd) % 2) return;
      const day = new Date(start + ((week * 7 + wd) * 86400000));
      const [time, end] = TIMES[(i + wd) % TIMES.length];
      n += 1;
      items.push({
        id: `s${n}`,
        lesson,
        teacher,
        group,
        date: day.toISOString().slice(0, 10),
        time,
        end_time: end,
        type: 'class',
      });
    });
  }
}

ok('toMinutes / fromMinutes رفت‌وبرگشت درست دارند', () => {
  assert.equal(E.toMinutes('08:30'), 510);
  assert.equal(E.fromMinutes(510), '08:30');
  assert.equal(E.toMinutes('۱۴:۳۰'), null); // ارقام فارسی پذیرفته نمی‌شود ⇒ صریح
  assert.equal(E.toMinutes(''), null);
});

ok('weekdayOf روز هفته را مستقل از منطقهٔ زمانی می‌دهد', () => {
  assert.equal(E.weekdayOf('2026-10-24').key, 'sat');
  assert.equal(E.weekdayOf('2026-10-29').key, 'thu');
  assert.equal(E.weekdayOf('nonsense'), null);
});

ok('هفتهٔ هفت‌روزه و ترتیب ایرانی (شنبه اول)', () => {
  assert.equal(E.WEEK.length, 7);
  assert.equal(E.WEEK[0].key, 'sat');
  assert.equal(E.WEEK[6].key, 'fri');
});

const week = E.buildWeek(items);
ok('همهٔ جلسه‌ها در جدول هفتگی حساب می‌شوند (نه بیشتر، نه کمتر)', () => {
  const sum = Object.values(week.daySessions).reduce((a, b) => a + b, 0);
  assert.equal(sum, week.totalSessions);
  assert.equal(week.totalSessions, items.length);
});

ok('جدول هفتگی کمتر از تعداد جلسه‌ها سلول دارد (ادغام تکرار)', () => {
  const cells = week.rows.reduce((acc, row) => acc + row.cells.flat().length, 0);
  assert.ok(cells < items.length, `سلول‌ها (${cells}) باید از جلسه‌ها (${items.length}) کمتر باشند`);
  assert.ok(cells > 0);
});

ok('ساعت‌های ردیف‌ها صعودی و بدون تکرارند', () => {
  const times = week.rows.map((r) => r.start);
  assert.deepEqual(times, [...new Set(times)].sort((a, b) => a - b));
});

ok('شمارندهٔ تکرار در هر خانه با تعداد تاریخ‌های همان خانه یکی است', () => {
  for (const row of week.rows) {
    for (const cell of row.cells) {
      for (const slot of cell) {
        assert.equal(slot.sessions, slot.dates.length);
      }
    }
  }
});

const stats = E.buildStats(items);
ok('آمار: جلسه/درس/استاد درست شمارش می‌شود', () => {
  assert.equal(stats.sessions, items.length);
  assert.equal(stats.lessons, LESSONS.length);
  assert.equal(stats.teachers, new Set(LESSONS.map((l) => l[1])).size);
  assert.ok(stats.activeDays > 0);
});

ok('جلسهٔ بدون ساعت در جدول هفتگی نمی‌نشیند ولی در آمار می‌ماند', () => {
  const withBad = [...items, { lesson: 'بدون ساعت', date: '2026-10-24', time: '' }];
  const w2 = E.buildWeek(withBad);
  assert.equal(w2.totalSessions, week.totalSessions);
  assert.equal(E.buildStats(withBad).sessions, items.length + 1);
});

const table = E.buildLessonTable(items);
ok('جدول درس‌ها: هر درس یک ردیف (نه یک ردیف برای هر جلسه)', () => {
  assert.equal(table.length, LESSONS.length);
  assert.ok(table.every((r) => r.sessions > 0));
});

ok('جدول درس‌ها بر اساس اولین روز/ساعت مرتب است', () => {
  const keys = table.map((r) => (r.slots[0] ? r.slots[0].dayIndex * 10000 + r.slots[0].start : 999999));
  assert.deepEqual(keys, [...keys].sort((a, b) => a - b));
});

ok('رنگ هر درس پایدار است (همان ورودی ⇒ همان خروجی)', () => {
  assert.deepEqual(E.lessonTone('فیزیولوژی پزشکی'), E.lessonTone('فیزیولوژی پزشکی'));
  assert.notEqual(E.lessonTone('فیزیولوژی پزشکی').fg, E.lessonTone('زبان').fg);
});

ok('shortLesson نام‌های بلند را کوتاه می‌کند ولی کوتاه‌ها را دست نمی‌زند', () => {
  const short = E.shortLesson('زبان پیش دانشگاهی (۲)', 11);
  assert.ok(short.length <= 11);
  assert.equal(E.shortLesson('ریاضی', 11), 'ریاضی');
});

ok('ورودی خالی ⇒ جدول خالی و بدون کرش', () => {
  const empty = E.buildWeek([]);
  assert.equal(empty.hasAny, false);
  assert.equal(empty.totalSessions, 0);
  assert.deepEqual(E.buildLessonTable([]), []);
});

console.log(`\nنتیجه: ${passed} تست موتور برنامه — همه سبز ✅`);
