import PageError from '../../components/shared/PageError';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';

import api from '../../lib/api';
import Header from '../../components/layout/Header';
import { ScheduleSkeleton } from '../../components/shared/skeletons';
import Icon from '../../components/ui/Icon';

import { haptic } from '../../lib/telegram';
import { useUIStore } from '../../stores/uiStore';
import { useAuthStore } from '../../stores/authStore';
import { faNum, faDate } from '../../lib/format';

import ScheduleOverview from './ScheduleOverview';
import { buildStats, lessonTone, shortLesson } from '../../lib/scheduleEngine';
import { Glyph } from '../../components/ui/Icon';

/* ─────────────────────────────────────────────────────────────
   📅 برنامهٔ درسی — بازسازی v3

   چه چیزی عوض شد و چرا؟
   ─────────────────────
   نسخهٔ قبل «فهرست تاریخ‌ها» بود: ۲۹۹ جلسه × یک کارت بزرگ ⇒ کاربر
   باید صدها پیکسل اسکرول می‌کرد تا فقط بفهمد هفته‌اش چه شکلی است.
   حالا:
     • «هفته در یک نگاه» = جدول ۷ ستونه (روز × ساعت) بدون اسکرول
     • نمودار بار هر روز (کلیک = فیلتر همان روز)
     • جدول درس‌ها: هر درس یک ردیف با همهٔ زمان‌هایش
     • شمارش صریح: «۲۹۹ جلسه · ۱۲ درس» در همان نوار بالا
   همه‌ی منطق قبلی (انتخاب واحد درس‌به‌درس، گروه اکثریت، هشدار
   تداخل، گروه آموزشی، خروجی ics، دیپ‌لینک) حفظ شده است.
   ───────────────────────────────────────────────────────────── */

const SECTIONS = [
  { key: 'class', label: 'کلاس‌ها', icon: 'calendar', type: 'class' },
  { key: 'exam', label: 'آزمون‌ها', icon: 'quiz', type: 'exam' },
  { key: 'makeup', label: 'جبرانی', icon: 'refresh', type: 'makeup' },
];

const groupName = (value) => {
  if (!value || value === '0') return '';
  if (value === 'هر دو') return 'هر دو گروه';
  return `گروه ${faNum(value)}`;
};

export default function Schedule() {
  const toast = useUIStore((s) => s.toast);
  const queryClient = useQueryClient();
  const userGroup = useAuthStore((state) => state.user?.group || '');

  const [section, setSection] = useState('class');
  const [activeDay, setActiveDay] = useState(null);
  const [openLesson, setOpenLesson] = useState(null);

  const [calBusy, setCalBusy] = useState(false);
  const [selectOpen, setSelectOpen] = useState(false);
  const [selDraft, setSelDraft] = useState({});
  const [savingSel, setSavingSel] = useState(false);
  const [eduBusy, setEduBusy] = useState(false);

  const [searchParams, setSearchParams] = useSearchParams();

  /* ── داده ── */
  const { data, isLoading, isError, refetch, isRefetching } = useQuery({
    queryKey: ['schedule', userGroup],
    queryFn: () => api.get('/api/schedule').then((r) => r.data),
    staleTime: 5 * 60 * 1000,
    refetchOnMount: 'always',
  });

  const { data: selData, refetch: refetchSel } = useQuery({
    queryKey: ['course-selections'],
    queryFn: () => api.get('/api/schedule/course-selections').then((r) => r.data),
    staleTime: 2 * 60 * 1000,
    refetchOnMount: 'always',
  });

  const schedule = Array.isArray(data?.schedule) ? data.schedule : [];

  const bySection = useMemo(() => {
    const map = { class: [], exam: [], makeup: [] };
    for (const item of schedule) {
      const type = item?.type || 'class';
      (map[type] ||= []).push(item);
    }
    return map;
  }, [schedule]);

  const items = bySection[section] || [];
  const overview = useMemo(() => buildStats(bySection.class), [bySection.class]);

  const offerings = selData?.offerings || [];
  const conflicts = data?.conflicts || [];
  const mismatched = data?.mismatched_selections || selData?.mismatched_selections || [];
  const needsEduGroup =
    Boolean(selData?.needs_educational_group_confirmation)
    || Boolean(data?.needs_educational_group_confirmation);
  const currentEdu = selData?.educational_group || data?.educational_group || 'unknown';
  const aiEdu =
    selData?.educational_group_info?.ai_suggested_group
    || data?.educational_group_info?.ai_suggested_group
    || 'unknown';
  const hasCustom = Boolean(data?.has_custom_selection || selData?.has_selections);
  const unselected = data?.unselected_lessons || [];

  /* ── پیش‌نویس انتخاب واحد ── */
  useEffect(() => {
    if (!selData) return;
    const map = { ...(selData.selections_map || {}) };
    for (const off of selData.offerings || []) {
      if (off.single_group && off.auto_selected_group && !map[off.lesson]) {
        map[off.lesson] = off.auto_selected_group;
      }
    }
    setSelDraft(map);
  }, [selData]);

  /* ── دیپ‌لینک‌ها: ?select=1 و ?hl=<درس> ── */
  const hlDone = useRef(false);
  useEffect(() => {
    if (searchParams.get('select') === '1') setSelectOpen(true);
  }, [searchParams]);

  useEffect(() => {
    const hl = searchParams.get('hl');
    if (!hl || hlDone.current) return;
    const found = items.find(
      (it) => it.id === hl || (it.lesson || '') === hl || (it.lesson || '').includes(hl),
    );
    if (!found) return;
    hlDone.current = true;
    setOpenLesson(found);
  }, [items, searchParams]);

  /* ── خروجی تقویم ── */
  const downloadCal = async () => {
    if (calBusy) return;
    setCalBusy(true);
    try {
      const r = await api.get('/api/schedule/ical', { responseType: 'blob' });
      const url = URL.createObjectURL(new Blob([r.data], { type: 'text/calendar' }));
      const a = document.createElement('a');
      a.href = url;
      a.download = 'humsyar-schedule.ics';
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 4000);
      toast('فایل تقویم دانلود شد');
    } catch {
      toast('دانلود تقویم ناموفق بود', 'err');
    }
    setCalBusy(false);
  };

  const confirmEduGroup = async (value) => {
    if (eduBusy) return;
    haptic();
    setEduBusy(true);
    try {
      await api.patch('/api/profile/educational-group', { educational_group: value });
      await Promise.all([
        refetchSel(),
        refetch(),
        queryClient.invalidateQueries({ queryKey: ['profile'] }),
      ]);
      toast(value === 'male' ? 'گروه آموزشی: کلاس‌های آقایان ثبت شد' : 'گروه آموزشی: کلاس‌های بانوان ثبت شد');
    } catch {
      toast('ثبت گروه آموزشی ناموفق بود', 'err');
    }
    setEduBusy(false);
  };

  const liveMajority = useMemo(() => {
    const fallback = selData?.registered_group || data?.registered_group || userGroup || '1';
    let c1 = 0;
    let c2 = 0;
    let u1 = 0;
    let u2 = 0;
    for (const off of offerings) {
      const g = selDraft[off.lesson];
      const credit = Number(off.credit || 1) || 1;
      if (g === '1') { c1 += 1; u1 += credit; }
      else if (g === '2') { c2 += 1; u2 += credit; }
    }
    let group = fallback;
    if (c1 > c2) group = '1';
    else if (c2 > c1) group = '2';

    else if (c1 > 0) group = u1 > u2 ? '1' : u2 > u1 ? '2' : fallback;
    return { group, c1, c2, total: c1 + c2 };
  }, [offerings, selDraft, selData, data, userGroup]);

  const toggleCourseGroup = (lesson, group, single) => {
    if (single) return;
    haptic();
    setSelDraft((prev) => {
      const next = { ...prev };
      if (next[lesson] === group) delete next[lesson];
      else next[lesson] = group;
      return next;
    });
  };

  const saveSelections = async () => {
    setSavingSel(true);
    try {
      const selections = Object.entries(selDraft)
        .filter(([, g]) => ['1', '2', '3', '4'].includes(g))
        .map(([lesson, group]) => ({ lesson, group }));

      const r = await api.post('/api/schedule/course-selections', {
        selections,
        term: selData?.term,
      });

      await Promise.all([
        refetch(),
        refetchSel(),
        queryClient.invalidateQueries({ queryKey: ['profile'] }),
      ]);

      setSelectOpen(false);
      if (searchParams.get('select')) {
        searchParams.delete('select');
        setSearchParams(searchParams, { replace: true });
      }
      toast(`برنامهٔ شخصی ذخیره شد · گروه اکثریت: ${groupName(r.data?.computed_group || liveMajority.group)}`);
    } catch {
      toast('ذخیرهٔ انتخاب واحد ناموفق بود', 'err');
    }
    setSavingSel(false);
  };

  const counts = {
    class: bySection.class.length,
    exam: bySection.exam.length,
    makeup: bySection.makeup.length,
  };

  return (
    <>
      <Header
        title="برنامه درسی"
        subtitle={
          [
            data?.term ? `ترم ${faNum(data.term)}` : '',
            groupName(data?.computed_group || data?.group || userGroup),
          ].filter(Boolean).join(' · ')
        }
        back={false}
        onRefresh={refetch}
        refreshing={isRefetching}
      />

      <main className="page fade-up" style={{ display: 'grid', gap: 8 }}>
        {/* ── نوار خلاصه: عددهایی که کاربر می‌خواهد اول ببیند ── */}
        <section className="v3-sumband">
          <span className="v3-sumband__icon">
            <Icon name="calendar" size={18} />
          </span>

          <div className="v3-sumband__main">
            <b>{hasCustom ? 'برنامهٔ شخصی ترم' : 'برنامهٔ ترم جاری'}</b>
            <span>
              {groupName(data?.computed_group || data?.group || userGroup) || 'گروه نامشخص'}
              {overview.activeDays ? ` · ${faNum(overview.activeDays)} روز فعال` : ''}
            </span>
          </div>

          <div className="v3-sumband__stats">
            <span className="v3-stat">
              <b>{faNum(counts.class)}</b> کلاس
            </span>

            {counts.exam > 0 && (
              <span className="v3-stat v3-stat--warn">
                <b>{faNum(counts.exam)}</b> آزمون
              </span>
            )}

            {overview.lessons > 0 && (
              <span className="v3-stat v3-stat--ok">
                <b>{faNum(overview.lessons)}</b> درس
              </span>
            )}
          </div>
        </section>

        {/* ── تب بخش‌ها ── */}
        <div className="v3-seg" role="tablist" aria-label="بخش برنامه">
          {SECTIONS.map((s) => (
            <button
              type="button"
              key={s.key}
              role="tab"
              aria-selected={section === s.key}
              className={`v3-seg__btn${section === s.key ? ' is-on' : ''}`}
              onClick={() => {
                haptic('light');
                setSection(s.key);
                setActiveDay(null);
              }}
            >
              <Icon name={s.icon} size={14} />
              {s.label}
              <i>{faNum(counts[s.key] || 0)}</i>
            </button>
          ))}
        </div>

        {/* ── انتخاب واحد / گروه ── */}
        {(needsEduGroup || hasCustom || offerings.length > 0) && (
          <section className="v3-panel">
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <div style={{ flex: 1, minWidth: 150 }}>
                <b style={{ fontSize: 12.5, display: 'flex', alignItems: 'center', gap: 5 }}>
                  <Icon name="sparkle" size={14} />
                  {hasCustom ? 'انتخاب واحد ثبت شده' : 'انتخاب واحد درس‌به‌درس'}
                </b>

                <div style={{ color: 'var(--tx2)', fontSize: 10.5, marginTop: 3, lineHeight: 1.7 }}>
                  {hasCustom
                    ? `${faNum(data?.selected_count || 0)} درس · گروه اکثریت: ${groupName(data?.computed_group || data?.group)}`
                    : 'برای هر درس مشخص کن با کدام گروه برداشتی تا برنامه دقیق خودت را ببینی.'}
                </div>
              </div>

              <button
                type="button"
                className="btn btn-p sm"
                onClick={() => {
                  haptic();
                  setSelectOpen(true);
                }}
              >
                <Icon name={hasCustom ? 'settings' : 'plus'} size={14} />
                {hasCustom ? 'ویرایش' : 'شروع'}
              </button>
            </div>

            {needsEduGroup && (
              <div style={{ display: 'grid', gap: 6, marginTop: 2 }}>
                <span style={{ fontSize: 10.5, color: 'var(--tx2)' }}>
                  گروه آموزشی کلاس‌ها را انتخاب کن
                  {aiEdu === 'male' ? ' (پیشنهاد: آقایان)' : ''}
                  {aiEdu === 'female' ? ' (پیشنهاد: بانوان)' : ''}
                </span>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
                  {[
                    { v: 'male', label: 'کلاس‌های آقایان' },
                    { v: 'female', label: 'کلاس‌های بانوان' },
                  ].map((opt) => (
                    <button
                      type="button"
                      key={opt.v}
                      className="btn sm"
                      disabled={eduBusy}
                      onClick={() => confirmEduGroup(opt.v)}
                      style={{
                        fontWeight: 700,
                        borderColor: aiEdu === opt.v ? 'var(--acc)' : undefined,
                        color: currentEdu === opt.v ? 'var(--t-acc)' : undefined,
                      }}
                    >
                      {opt.label}
                      {currentEdu === opt.v ? ' ✓' : ''}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {hasCustom && unselected.length > 0 && (
              <div style={{ fontSize: 10.5, color: 'var(--warn)' }}>
                {faNum(unselected.length)} درس ارائه‌شده انتخاب نشده است.
              </div>
            )}
          </section>
        )}

        {/* ── هشدارها ── */}
        {conflicts.length > 0 && (
          <section
            className="v3-note"
            style={{ borderColor: 'rgba(255,107,122,.3)', background: 'rgba(255,107,122,.1)' }}
          >
            <Icon name="shield" size={16} />
            <span>
              <b style={{ color: 'var(--err)' }}>تداخل زمانی ({faNum(conflicts.length)}): </b>
              {conflicts.slice(0, 2).map((c) => c.message).join(' · ')}
            </span>
          </section>
        )}

        {mismatched.length > 0 && (
          <section className="v3-note">
            <Icon name="info" size={16} />
            <span>
              <b>{faNum(mismatched.length)} انتخاب </b>
              با گروه آموزشی فعلی مغایرت دارد؛ از «ویرایش» اصلاحش کن.
            </span>
          </section>
        )}

        {/* ── بدنه ── */}
        {isLoading ? (
          <ScheduleSkeleton />
        ) : isError ? (
          <PageError
            text="دریافت برنامه انجام نشد."
            onRetry={() => refetch()}
            pending={isRefetching}
          />
        ) : (
          <ScheduleOverview
            items={items}
            mode={section}
            activeDay={activeDay}
            onPickDay={setActiveDay}
          />
        )}

        {/* ── اکشن‌های پایین ── */}
        <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
          <button type="button" className="btn sm" disabled={calBusy} onClick={downloadCal}>
            <Icon name="download" size={14} />
            {calBusy ? 'در حال ساخت…' : 'افزودن به تقویم'}
          </button>

          <button type="button" className="btn sm" onClick={() => refetch()}>
            <Icon name="refresh" size={14} />
            بازآوری
          </button>
        </div>
      </main>

      {/* ── شیت جزئیات جلسه ── */}
      {openLesson && (
        <div className="v3-sheet" role="dialog" aria-modal="true" onClick={() => setOpenLesson(null)}>
          <div className="v3-sheet__panel" onClick={(e) => e.stopPropagation()}>
            <div className="v3-sheet__title">
              <b>{openLesson.lesson || 'بدون عنوان'}</b>
              <button type="button" className="btn sm" onClick={() => setOpenLesson(null)}>
                <Icon name="close" size={14} />
              </button>
            </div>

            <div className="v3-sheet__rows">
              {openLesson.teacher && (
                <div className="v3-sheet__row">
                  <Icon name="user" size={15} />
                  استاد
                  <b>{openLesson.teacher}</b>
                </div>
              )}

              {openLesson.date && (
                <div className="v3-sheet__row">
                  <Icon name="calendar" size={15} />
                  تاریخ
                  <b>{faDate(openLesson.date, '—')}</b>
                </div>
              )}

              {openLesson.time && (
                <div className="v3-sheet__row">
                  <Icon name="clock" size={15} />
                  ساعت
                  <b>
                    {faNum(openLesson.time)}
                    {openLesson.end_time ? ` تا ${faNum(openLesson.end_time)}` : ''}
                  </b>
                </div>
              )}

              {openLesson.location && (
                <div className="v3-sheet__row">
                  <Icon name="target" size={15} />
                  محل
                  <b>{openLesson.location}</b>
                </div>
              )}

              {openLesson.sessions > 1 && (
                <div className="v3-sheet__row">
                  <Icon name="layers" size={15} />
                  تکرار در ترم
                  <b>{faNum(openLesson.sessions)} جلسه</b>
                </div>
              )}

              {groupName(openLesson.group) && (
                <div className="v3-sheet__row">
                  <Icon name="shield" size={15} />
                  گروه
                  <b>{groupName(openLesson.group)}</b>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── شیت انتخاب واحد ── */}
      {selectOpen && (
        <div className="v3-sheet" role="dialog" aria-modal="true" onClick={() => setSelectOpen(false)}>
          <div
            className="v3-sheet__panel"
            onClick={(e) => e.stopPropagation()}
            style={{ maxHeight: '86vh', display: 'grid', gridTemplateRows: 'auto 1fr auto' }}
          >
            <div className="v3-sheet__title">
              <div>
                <b>انتخاب گروه درس‌ها</b>
                <div style={{ fontSize: 10.5, color: 'var(--tx2)', marginTop: 2 }}>
                  هر درس را با کدام گروه و استاد برداشته‌ای؟
                </div>
              </div>

              <button type="button" className="btn sm" onClick={() => setSelectOpen(false)}>
                <Icon name="close" size={14} />
              </button>
            </div>

            <div style={{ overflowY: 'auto', display: 'grid', gap: 7, paddingInline: 2 }}>
              {offerings.length === 0 && (
                <div className="v3-empty">
                  <Icon name="layers" size={24} />
                  <b>کاتالوگ درسی برای این ترم ثبت نشده</b>
                  <span>مدیر باید دروس ارائه‌شدهٔ ترم را وارد کند.</span>
                </div>
              )}

              {offerings.map((off) => {
                const tone = lessonTone(off.lesson);
                const chosen = selDraft[off.lesson];
                const groups = off.groups || [];

                return (
                  <div key={off.lesson} className="v3-ltable__row" style={{ cursor: 'default', display: 'grid', gap: 6 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span className="v3-ltable__dot" style={{ background: tone.fg }} />
                      <b style={{ fontSize: 12 }}>{off.lesson}</b>
                      {off.credit ? (
                        <span className="v3-stat" style={{ marginInlineStart: 'auto' }}>
                          <b>{faNum(off.credit)}</b> واحد
                        </span>
                      ) : null}
                    </div>

                    <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
                      {off.single_group && off.auto_selected_group && (
                        <span className="v3-stat">
                          فقط گروه {faNum(off.auto_selected_group)} ارائه شده
                        </span>
                      )}

                      {!off.single_group && groups.length === 0 && (
                        <span className="v3-stat">گروه‌ها ثبت نشده</span>
                      )}

                      {!off.single_group && groups.map((g) => (
                        <button
                          type="button"
                          key={g.group}
                          className="btn sm"
                          onClick={() => toggleCourseGroup(off.lesson, g.group, false)}
                          style={{
                            fontSize: 11,
                            padding: '4px 9px',
                            borderColor: chosen === g.group ? 'var(--acc)' : undefined,
                            color: chosen === g.group ? 'var(--t-acc)' : undefined,
                            fontWeight: 700,
                          }}
                          title={g.teacher || ''}
                        >
                          گروه {faNum(g.group)}
                          {g.teacher ? ` · ${shortLesson(g.teacher, 12)}` : ''}
                        </button>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>

            <div style={{ display: 'grid', gap: 6, paddingTop: 4 }}>
              <div style={{ fontSize: 10.5, color: 'var(--tx2)', textAlign: 'center' }}>
                گروه اکثریت: {groupName(liveMajority.group)} · {faNum(liveMajority.total)} درس
              </div>

              <button
                type="button"
                className="btn btn-p btn-full"
                disabled={savingSel}
                onClick={saveSelections}
              >
                <Icon name="check" size={15} />
                {savingSel ? 'در حال ذخیره…' : 'ذخیرهٔ انتخاب واحد'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
