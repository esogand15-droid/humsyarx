import { Glyph } from '../../components/ui/Icon';
/* ─────────────────────────────────────────────────────────────
   📅 HumsYar v3 — نمای «هفته در یک نگاه»

   سه تکهٔ چسبیده:
   ۱) نمودار بار هفته (۷ ستون، تعداد جلسه در هر روز)
   ۲) جدول هفتگی (روز × ساعت) — بدون اسکرول صفحه
   ۳) جدول درس‌ها (هر درس یک ردیف، همهٔ زمان‌هایش)

   اصل طراحی: هر چیزی که «هفتهٔ ثابت» است یک بار دیده شود، نه
   ۲۹۹ بار. تکرار ۱۶ هفته‌ای در همان خانه با شمارندهٔ کوچک نشان
   داده می‌شود، نه با ۱۶ کارت جدا.
   ───────────────────────────────────────────────────────────── */

import { useMemo, useState } from 'react';

import Icon from '../../components/ui/Icon';
import { faNum } from '../../lib/format';
import { haptic } from '../../lib/telegram';
import {
  WEEK,
  buildWeek,
  buildStats,
  buildLessonTable,
  lessonTone,
  shortLesson,
} from '../../lib/scheduleEngine';

/* ── ۱) نمودار بار هفته ── */
export function WeekLoadChart({ week, activeDay, onPickDay }) {
  const total = week.totalSessions || 1;

  return (
    <div className="v3-load" role="img"
      aria-label={`پخش جلسه‌ها در هفته: ${WEEK.map(
        (d) => `${d.name} ${week.daySessions[d.key] || 0}`,
      ).join('، ')}`}
    >
      {WEEK.map((day) => {
        const count = week.daySessions[day.key] || 0;
        const height = Math.max(6, Math.round((count / week.maxPerDay) * 100));
        const isActive = activeDay === day.key;

        return (
          <button
            type="button"
            key={day.key}
            className={`v3-load__col${isActive ? ' is-active' : ''}`}
            onClick={() => {
              haptic('light');
              onPickDay?.(isActive ? null : day.key);
            }}
            aria-label={`${day.name}: ${count} جلسه`}
          >
            <span className="v3-load__num">{count ? faNum(count) : ''}</span>
            <span className="v3-load__track">
              <span
                className="v3-load__bar"
                style={{ height: `${count ? height : 4}%` }}
              />
            </span>
            <span className="v3-load__day">{day.short}</span>
          </button>
        );
      })}
      <span className="v3-load__total">{faNum(total)} جلسه در ترم</span>
    </div>
  );
}

/* ── ۲) جدول هفتگی ── */
export function WeeklyGrid({ week, dayFilter, onOpenLesson }) {
  const days = dayFilter
    ? week.days.filter((d) => d.key === dayFilter)
    : week.days;

  const dayIndexes = days.map((d) => WEEK.findIndex((w) => w.key === d.key));

  return (
    <div className={`v3-grid${dayFilter ? ' v3-grid--single' : ''}`}>
      {/* سرستون‌ها */}
      <div className="v3-grid__head" style={{ gridTemplateColumns: `38px repeat(${days.length}, minmax(0,1fr))` }}>
        <span className="v3-grid__corner">
          <Icon name="clock" size={13} />
        </span>

        {days.map((day) => (
          <span
            key={day.key}
            className={`v3-grid__day${week.daySessions[day.key] ? '' : ' is-empty'}`}
          >
            <b>{day.short}</b>
            <i>{faNum(week.daySessions[day.key] || 0)}</i>
          </span>
        ))}
      </div>

      {/* ردیف‌های ساعت */}
      <div className="v3-grid__body">
        {week.rows.map((row) => (
          <div
            key={row.start}
            className="v3-grid__row"
            style={{ gridTemplateColumns: `38px repeat(${days.length}, minmax(0,1fr))` }}
          >
            <span className="v3-grid__time">{faNum(row.label)}</span>

            {dayIndexes.map((dayIdx) => {
              const slots = row.cells[dayIdx] || [];

              if (!slots.length) {
                return <span key={`${row.start}-${dayIdx}`} className="v3-grid__cell is-empty" />;
              }

              return (
                <span key={`${row.start}-${dayIdx}`} className="v3-grid__cell">
                  {slots.map((slot, index) => {
                    const tone = lessonTone(slot.lesson);

                    return (
                      <button
                        type="button"
                        key={`${slot.lesson}-${index}`}
                        className={`v3-chip-lesson${slot.type === 'exam' ? ' is-exam' : ''}${slot.type === 'makeup' ? ' is-makeup' : ''}`}
                        style={{ background: tone.bg, color: tone.fg, borderColor: tone.line }}
                        title={`${slot.lesson} · ${slot.teacher || 'استاد نامشخص'} · ${slot.start ? `${slot.start} تا ${slot.end} دقیقه` : ''} · ${slot.sessions} جلسه`}
                        onClick={() => onOpenLesson?.(slot)}
                      >
                        <b>{shortLesson(slot.lesson, 11)}</b>
                        {slot.sessions > 1 && (
                          <i className="v3-chip-lesson__n">{faNum(slot.sessions)}×</i>
                        )}
                      </button>
                    );
                  })}
                </span>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── ۳) جدول درس‌ها ── */
export function LessonTable({ items, onOpenLesson }) {
  const rows = useMemo(() => buildLessonTable(items), [items]);

  return (
    <div className="v3-ltable" role="table" aria-label="جدول درس‌های ترم">
      <div className="v3-ltable__head" role="row">
        <span role="columnheader">درس</span>
        <span role="columnheader">روز و ساعت</span>
        <span role="columnheader">جلسه</span>
      </div>

      {rows.map((row) => {
        const tone = lessonTone(row.lesson);

        return (
          <button
            type="button"
            role="row"
            key={row.lesson}
            className="v3-ltable__row"
            onClick={() => onOpenLesson?.(row)}
          >
            <span className="v3-ltable__name" role="cell">
              <b
                className="v3-ltable__dot"
                style={{ background: tone.fg }}
                aria-hidden="true"
              />
              <span>
                {row.lesson}
                {row.group && <i>{`گروه ${faNum(row.group)}`}</i>}
              </span>
            </span>

            <span className="v3-ltable__slots" role="cell">
              {row.slots.length ? (
                row.slots.map((slot) => (
                  <i key={`${slot.day.key}-${slot.start}`}>
                    {slot.day.short} {faNum(`${Math.floor(slot.start / 60)}:${String(slot.start % 60).padStart(2, '0')}`)}
                  </i>
                ))
              ) : (
                <i className="is-muted">بدون ساعت</i>
              )}
            </span>

            <span className="v3-ltable__count" role="cell">
              {faNum(row.sessions)}
            </span>
          </button>
        );
      })}
    </div>
  );
}

/* ── ۴) فهرست فشردهٔ جلسه‌ها (برای یافتن یک تاریخ مشخص) ── */
export function SessionList({ items }) {
  const rows = useMemo(() => {
    return [...items]
      .filter((it) => it.date)
      .sort((a, b) => String(a.date).localeCompare(String(b.date))
        || String(a.time || '').localeCompare(String(b.time || '')))
      .slice(0, 120);
  }, [items]);

  if (!rows.length) {
    return (
      <div className="v3-empty">
        <Icon name="calendar" size={24} />
        <b>تاریخی ثبت نشده</b>
      </div>
    );
  }

  return (
    <div className="v3-ltable" role="table" aria-label="فهرست جلسه‌ها">
      {rows.map((it, index) => (
        <div className="v3-ltable__row" role="row" key={it.id || `${it.lesson}-${index}`} style={{ cursor: 'default' }}>
          <span className="v3-ltable__name" role="cell">
            <b className="v3-ltable__dot" style={{ background: lessonTone(it.lesson).fg }} />
            <span>{it.lesson || 'بدون عنوان'}</span>
          </span>
          <span className="v3-ltable__slots" role="cell">
            <i>{faDate(it.date, '—')}</i>
            {it.time && <i>{faNum(it.time)}</i>}
          </span>
          <span className="v3-ltable__count" role="cell">—</span>
        </div>
      ))}

      {items.length > rows.length && (
        <div className="v3-panel__hint" style={{ textAlign: 'center' }}>
          {faNum(items.length - rows.length)} جلسهٔ بعدی نمایش داده نشد — از نمای هفتگی استفاده کن.
        </div>
      )}
    </div>
  );
}

/* ── کارت نمای کلی (بدون اسکرول) ── */
export default function ScheduleOverview({
  items,
  activeDay,
  onPickDay,
  mode,
}) {
  const stats = useMemo(() => buildStats(items), [items]);

  /* نمای داخلی: پیش‌فرض «هفته» است تا کل صفحه در یک صفحهٔ گوشی جا شود
     (خواستهٔ صریح: بدون اسکرول برای دیدن جدول). «درس‌ها» و «لیست»
     فقط با یک کلیک باز می‌شوند. */
  const [view, setView] = useState('week');

  if (!items.length) {
    return (
      <div className="v3-empty">
        <Icon name="calendar" size={28} />
        <b>برای این بخش جلسه‌ای ثبت نشده</b>
        <span>با انتخاب واحد یا پس از انتشار برنامهٔ ترم، همین‌جا نمایش داده می‌شود.</span>
      </div>
    );
  }

  return (
    <>
      <div className="v3-seg" role="tablist" aria-label="نوع نمایش برنامه">
        {[
          { key: 'week', label: 'هفتگی', icon: 'calendar' },
          { key: 'lessons', label: 'درس‌ها', icon: 'layers' },
          { key: 'list', label: 'لیست جلسه‌ها', icon: 'menu' },
        ].map((tab) => (
          <button
            type="button"
            key={tab.key}
            role="tab"
            aria-selected={view === tab.key}
            className={`v3-seg__btn${view === tab.key ? ' is-on' : ''}`}
            onClick={() => {
              haptic('light');
              setView(tab.key);
            }}
          >
            <Icon name={tab.icon} size={14} />
            {tab.label}
          </button>
        ))}
      </div>

      {!stats.week.hasAny && (
        <div className="v3-note">
          <Icon name="info" size={16} />
          ساعت این جلسه‌ها در سامانه ثبت نشده، پس در جدول هفتگی جای نمی‌گیرند؛
          فهرست کامل پایین آمده است.
        </div>
      )}

      {stats.week.hasAny && view === 'week' && (
        <section className="v3-panel v3-panel--grid">
          <header className="v3-panel__head">
            <span className="v3-panel__title">
              <Icon name={mode === 'exams' ? 'quiz' : 'calendar'} size={15} />
              {mode === 'exams' ? 'تقویم آزمون‌ها' : 'هفته در یک نگاه'}
            </span>
            <span className="v3-panel__hint">
              {faNum(stats.week.totalSessions)} جلسه · {faNum(stats.lessons)} درس
            </span>
          </header>

          <WeekLoadChart
            week={stats.week}
            activeDay={activeDay}
            onPickDay={onPickDay}
          />

          <WeeklyGrid
            week={stats.week}
            dayFilter={activeDay}
          />
        </section>
      )}

      {view === 'lessons' && (
        <section className="v3-panel">
          <header className="v3-panel__head">
            <span className="v3-panel__title">
              <Icon name="layers" size={15} />
              جدول درس‌ها
            </span>
            <span className="v3-panel__hint">
              {faNum(stats.lessons)} درس · {faNum(stats.teachers)} استاد
            </span>
          </header>

          <LessonTable items={items} />
        </section>
      )}

      {view === 'list' && (
        <section className="v3-panel">
          <header className="v3-panel__head">
            <span className="v3-panel__title">
              <Icon name="menu" size={15} />
              جلسه‌های ثبت‌شده
            </span>
            <span className="v3-panel__hint">{faNum(items.length)} جلسه</span>
          </header>

          <SessionList items={items} />
        </section>
      )}
    </>
  );
}
