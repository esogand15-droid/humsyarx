import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Icon } from '../components/Icon';
import { Badge, Chip, Collapse, Dialog, Note, Progress, SectionHead } from '../components/ui';
import { PageTitle } from '../components/Shell';
import { fa, useProto } from '../lib/store';
import { tasks, upcomingExams, weekDays, weekSlots, weekStudy, progressSummary } from '../data/demo';

/* ═══════════════════════════════════════════════════════════════════
   SC-050 — برنامهٔ مطالعه و تقویم آزمون‌ها
   دادهٔ کلاس‌ها از `GET /api/schedule` می‌آید (موجود در محصول)؛
   برنامه‌ریزی دستی و همگام‌سازی تقویم خارجی «نیست» و همین‌جا گفته می‌شود.
   ═══════════════════════════════════════════════════════════════════ */
export function Plan() {
  const { toast } = useProto();
  const [view, setView] = useState<'week' | 'list'>('week');
  const [done, setDone] = useState<Record<string, boolean>>({});
  const [taskDlg, setTaskDlg] = useState(false);
  /* موبایل: یک روز در هر لحظه — پیش‌فرض «امروز» */
  const todayIdx = Math.max(0, weekDays.findIndex((d) => d.today));
  const [dayIdx, setDayIdx] = useState(todayIdx);
  const dayNav = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const btn = dayNav.current?.querySelector<HTMLElement>(`[data-day="${todayIdx}"]`);
    btn?.scrollIntoView({ block: 'nearest', inline: 'center' });
  }, [todayIdx]);

  return (
    <div className="page">
      <PageTitle
        title="برنامهٔ مطالعه"
        sub="کلاس‌های این هفته، آزمون‌های پیشِ رو و کارهای امروز"
        actions={
          <div className="row" style={{ gap: 8 }}>
            <button type="button" className="btn btn--ghost btn--sm" onClick={() => toast('خروجی تقویم (iCal) در محصول موجود است؛ در این نسخه دانلود نمی‌شود.')}>
              <Icon name="download" size={14} />
              خروجی تقویم
            </button>
            <button type="button" className="btn btn--primary btn--sm" onClick={() => setTaskDlg(true)}>
              <Icon name="plus" size={14} />
              کار تازه
            </button>
          </div>
        }
      />

      <div className="home-grid">
        <div>
          <section className="panel panel--pad">
            <div className="row" style={{ marginBottom: 16, gap: 10, flexWrap: 'wrap' }}>
              <button type="button" className="btn btn--quiet btn--icon" aria-label="هفتهٔ قبل">
                <Icon name="forward" size={16} />
              </button>
              <div>
                <b className="h3">۲۶ مهر — ۲ آبان</b>
                <div className="xs muted-2">هفتهٔ جاری · نیم‌سال دوم</div>
              </div>
              <span className="grow" />
              <div className="seg" role="group" aria-label="نمای برنامه">
                <button type="button" aria-pressed={view === 'week'} onClick={() => setView('week')}>
                  هفته
                </button>
                <button type="button" aria-pressed={view === 'list'} onClick={() => setView('list')}>
                  فهرست
                </button>
              </div>
            </div>

            {view === 'week' ? (
              <>
              <div className="week plan-week">
                {weekDays.map((d, i) => (
                  <div key={d.label} className="week__d">
                    <div className={`week__h${d.today ? ' week__h--today' : ''}`}>
                      {d.label}
                      <b className="num">{d.day}</b>
                    </div>
                    {(weekSlots[i] ?? []).map((s) => (
                      <div key={s.title} className={`slot${s.kind === 'exam' ? ' slot--exam' : s.kind === 'review' ? ' slot--review' : ''}`}>
                        <b>{s.title}</b>
                        <span className="num">{s.time}</span>
                      </div>
                    ))}
                    {(weekSlots[i] ?? []).length === 0 && <div className="slot slot--off">—</div>}
                    <div className="xs muted-2 num" style={{ textAlign: 'center' }}>
                      {fa(weekStudy[i].minutes)} د
                    </div>
                  </div>
                ))}
              </div>

              {/* در موبایل: یک روز در هر لحظه با انتخاب‌گر روز (همان داده، بدون هفت ستون باریک) */}
              <div className="plan-agenda" aria-label="برنامهٔ روزهای هفته">
                <div className="plan-daynav" role="tablist" aria-label="انتخاب روز" ref={dayNav}>
                  {weekDays.map((d, i) => {
                    const n = (weekSlots[i] ?? []).length;
                    return (
                      <button
                        key={d.label}
                        type="button"
                        role="tab"
                        data-day={i}
                        aria-selected={dayIdx === i}
                        className={`chip${dayIdx === i ? ' chip--on' : ''}${d.today ? ' is-today' : ''}`}
                        onClick={() => setDayIdx(i)}
                      >
                        {d.label}
                        <span className="num">{d.day}</span>
                        {n > 0 && <span className="plan-daynav__n num">{fa(n)}</span>}
                      </button>
                    );
                  })}
                </div>

                {(() => {
                  const d = weekDays[dayIdx];
                  const slots = weekSlots[dayIdx] ?? [];
                  return (
                    <div className="plan-agenda__day" key={d.label}>
                      <div className={`plan-agenda__d${d.today ? ' is-today' : ''}`}>
                        <b>{d.label}</b>
                        <span className="num">{d.day}</span>
                        <span className="num muted-2" style={{ display: 'block' }}>
                          {fa(weekStudy[dayIdx].minutes)} د
                        </span>
                      </div>
                      <div className="plan-agenda__items">
                        {slots.length === 0 && <span className="plan-agenda__empty">برنامه‌ای ثبت نشده</span>}
                        {slots.map((sl) => (
                          <div
                            key={sl.title}
                            className={`slot${sl.kind === 'exam' ? ' slot--exam' : sl.kind === 'review' ? ' slot--review' : ''}`}
                          >
                            <b>{sl.title}</b>
                            <span className="num">{sl.time}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })()}
                <p className="xs muted-2" style={{ paddingTop: 6 }}>
                  هر روز در یک نما؛ روزهای دیگر با انتخاب‌گر بالا ·{' '}
                  {fa(weekDays.filter((_, i) => (weekSlots[i] ?? []).length === 0).length)} روز بدون برنامه در این هفته
                </p>
              </div>
              </>
            ) : (
              <div style={{ display: 'grid', gap: 8 }}>
                {weekDays.flatMap((d, i) =>
                  (weekSlots[i] ?? []).map((s) => (
                    <div key={`${d.label}-${s.title}`} className="row" style={{ gap: 10, padding: '10px 0', borderBottom: '1px solid var(--line)' }}>
                      <span className="xs muted-2" style={{ width: 82 }}>
                        {d.label} {d.day}
                      </span>
                      <Icon
                        name={s.kind === 'exam' ? 'target' : s.kind === 'review' ? 'refresh' : 'book-open'}
                        size={15}
                        style={{ color: s.kind === 'exam' ? 'var(--danger)' : s.kind === 'review' ? 'var(--cyan-400)' : 'var(--text-3)' }}
                      />
                      <span className="sm grow">{s.title}</span>
                      <span className="xs num muted-2">{s.time}</span>
                    </div>
                  )),
                )}
              </div>
            )}

            <div className="row xs muted-2" style={{ marginTop: 14, gap: 14, flexWrap: 'wrap' }}>
              <span className="row" style={{ gap: 5 }}>
                <span className="dot" style={{ color: 'var(--brand-600)' }} /> کلاس
              </span>
              <span className="row" style={{ gap: 5 }}>
                <span className="dot" style={{ color: 'var(--cyan-400)' }} /> مرور
              </span>
              <span className="row" style={{ gap: 5 }}>
                <span className="dot" style={{ color: 'var(--danger)' }} /> آزمون
              </span>
            </div>
          </section>

          <SectionHead title="کارهای من" hint="قابل علامت‌زدن" />
          <div className="panel panel--flush plan-tasks">
            <Collapse label="کارها">
            {tasks.map((t) => {
              const isDone = done[t.id] ?? t.done;
              return (
                <div key={t.id} className="rrow" style={{ gridTemplateColumns: 'auto minmax(0,1fr) auto' }}>
                  <button
                    type="button"
                    className="avatar"
                    style={{
                      width: 24, height: 24, borderRadius: 7,
                      background: isDone ? 'var(--ok-soft)' : 'var(--surface-3)',
                      border: `1px solid ${isDone ? 'rgba(47,208,154,.4)' : 'var(--line)'}`,
                      color: isDone ? 'var(--ok)' : 'var(--text-3)',
                    }}
                    aria-pressed={isDone}
                    aria-label={`${t.title} — ${isDone ? 'انجام شده' : 'انجام نشده'}`}
                    onClick={() => {
                      setDone((d) => ({ ...d, [t.id]: !isDone }));
                      toast(!isDone ? 'کار انجام شد.' : 'علامت انجام برداشته شد.', !isDone ? 'ok' : 'info');
                    }}
                  >
                    {isDone && <Icon name="check" size={13} />}
                  </button>
                  <span style={{ minWidth: 0 }}>
                    <span
                      className="rrow__t"
                      style={{ textDecoration: isDone ? 'line-through' : 'none', color: isDone ? 'var(--text-3)' : undefined }}
                    >
                      {t.title}
                    </span>
                    <span className="rrow__m">
                      <span>{t.due}</span>
                    </span>
                  </span>
                  {t.urgent ? <Badge tone="warn">امروز</Badge> : <span />}
                </div>
              );
            })}
            </Collapse>
          </div>
        </div>

        <aside style={{ display: 'grid', gap: 16 }}>
          <section className="panel panel--pad">
            <div className="row" style={{ marginBottom: 12 }}>
              <b className="h3">آزمون‌های پیشِ رو</b>
              <span className="grow" />
              <Badge tone="warn">نزدیک‌ترین ۳ روز</Badge>
            </div>
            <div style={{ display: 'grid', gap: 10 }}>
              {upcomingExams.map((e) => (
                <div key={e.id} className="panel panel--quiet" style={{ padding: 12 }}>
                  <div className="row" style={{ gap: 10 }}>
                    <span className={`countdown${e.inDays <= 3 ? ' countdown--urgent' : ''}`}>
                      <b className="num">{fa(e.inDays)}</b>
                      <span>روز</span>
                    </span>
                    <div style={{ minWidth: 0 }}>
                      <div className="sm" style={{ fontWeight: 600 }}>
                        {e.title}
                      </div>
                      <div className="xs muted-2">
                        {e.date} · {e.scope}
                      </div>
                    </div>
                  </div>
                  <div className="row" style={{ marginTop: 10, gap: 6 }}>
                    <Link to="/exam/run" className="btn btn--ghost btn--sm grow">
                      آزمون آزمایشی از این محدوده
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section className="panel panel--pad">
            <b className="h3">توازن هفته</b>
            <p className="xs muted-2" style={{ marginTop: 4 }}>
              {fa(progressSummary.weeklyMinutes)} از {fa(progressSummary.weeklyTarget)} دقیقهٔ هدف
            </p>
            <div style={{ margin: '12px 0' }}>
              <Progress value={Math.round((progressSummary.weeklyMinutes / progressSummary.weeklyTarget) * 100)} />
            </div>
            <div className="xs muted-2" style={{ lineHeight: 1.8 }}>
              سه‌شنبه و پنج‌شنبه بیشتر از هدف بوده‌ای؛ دوشنبه و جمعه جای جبران دارند. این مقایسه از گزارش
              مطالعهٔ سرور می‌آید.
            </div>
          </section>

          <Note icon="info">
            <b>در این نسخه نیست:</b> همگام‌سازی با تقویم بیرونی، یادآور اعلانی و برنامه‌ریزی خودکار. این‌ها
            به سرویس واقعی نیاز دارند و در نقشهٔ راه بعد از تأیید طراحی قرار می‌گیرند.
          </Note>
        </aside>
      </div>

      <Dialog
        open={taskDlg}
        title="کار تازه"
        onClose={() => setTaskDlg(false)}
        actions={
          <>
            <button
              type="button"
              className="btn btn--primary btn--sm"
              onClick={() => {
                setTaskDlg(false);
                toast('کار به فهرست امروز اضافه شد.', 'ok');
              }}
            >
              افزودن
            </button>
            <button type="button" className="btn btn--ghost btn--sm" onClick={() => setTaskDlg(false)}>
              انصراف
            </button>
          </>
        }
      >
        <div style={{ display: 'grid', gap: 12, minWidth: 0 }}>
          <label className="field">
            <span className="field__l">عنوان کار</span>
            <input className="input" placeholder="مثلاً «مرور ۱۲ صفحهٔ اسیلوسکوپ قلبی»" />
          </label>
          <label className="field">
            <span className="field__l">زمان</span>
            <input className="input" placeholder="امروز، ۱۸:۰۰" />
          </label>
          <div className="filters">
            <Chip>امروز</Chip>
            <Chip>فردا</Chip>
            <Chip>این هفته</Chip>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
