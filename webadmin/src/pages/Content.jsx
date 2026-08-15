import React, { useEffect, useMemo, useRef, useState } from 'react';
import { api, errText } from '../api.js';
import { Loading, ErrorState, B, PageHeader, ScopeBadge, Timeline, toast, Confirm, Modal, Empty, NoPerm } from '../ui.jsx';
import { writeHashQuery } from '../urlState.js';
import SavedViews from '../SavedViews.jsx';

const TERM_ICON = '📚';
const KIND = {
  global:    { icon: '🌐', label: 'سراسری', kind: 'acc' },
  fork:      { icon: '⭐', label: 'Override', kind: 'warn' },
  exclusive: { icon: '🏷', label: 'اختصاصی', kind: 'purple' },
};
const CTYPE = { video: '🎬', ppt: '📽', pdf: '📕', note: '📝', test: '🧪', voice: '🎙' };
const EXT_MAP = { pdf: 'pdf', ppt: 'ppt', pptx: 'ppt', mp4: 'video', mov: 'video', mkv: 'video', webm: 'video', mp3: 'voice', ogg: 'voice', wav: 'voice', m4a: 'voice' };
const fa = (n) => Number(n ?? 0).toLocaleString('fa-IR');

// 📚🌊 WA2.1 — مرکز فرماندهی محتوا · 🌊 موج Content-Split:
// چیدمان سه‌ستونه‌ی دسکتاپ‌محور «درخت درس‌ها | جلسات | بازرس» روی همان APIهای
// موجود (بدون هیچ تغییر بک‌اندی) — همه‌ی اکشن‌های قبلی (fork/کلون/انتقال/حذف
// گروهی/reorder/آپلود چندفایلی/گزارش‌ها) حفظ شده‌اند.
import { RefsTab, ScheduleTab, QbankTab, FaqTab, ReportsTab } from './contentTabs.jsx';

const CCONTENT_TABS = [
  ['bs', '📚 علوم پایه'],
  ['refs', '📖 رفرنس‌ها'],
  ['schedule', '🗓 کلاس‌ها/برنامه'],
  ['qbank', '🧪 بانک سؤال'],
  ['faq', '❓ راهنما/FAQ'],
  ['reports', '🚩 گزارش‌ها'],
];

export default function Content({ route = '' }) {
  const params = new URLSearchParams(route.split('?')[1] || '');
  const requested = params.get('tab');
  const [tab, setTab] = useState(CCONTENT_TABS.some(([k]) => k === requested) ? requested : 'bs');
  useEffect(() => { if (CCONTENT_TABS.some(([k]) => k === requested)) setTab(requested); }, [requested]);
  const changeTab = value => { setTab(value); writeHashQuery('/content', { tab: value !== 'bs' ? value : '' }); };
  return (
    <>
      <div className="tabs" style={{ marginBottom: 14 }} role="tablist" aria-label="بخش‌های مدیریت محتوا">
        {CCONTENT_TABS.map(([k, label]) => (
          <button key={k} type="button" role="tab" aria-selected={tab === k} className={`tab ${tab === k ? 'on' : ''}`} onClick={() => changeTab(k)}>{label}</button>
        ))}
      </div>
      {tab === 'bs' && <BsTab initial={{ intake: params.get('intake') || '', q: params.get('q') || '', lesson: params.get('lesson') || null, session: params.get('session') || null }} />}
      {tab === 'refs' && <RefsTab />}
      {tab === 'schedule' && <ScheduleTab />}
      {tab === 'qbank' && <QbankTab />}
      {tab === 'faq' && <FaqTab />}
      {tab === 'reports' && <ReportsTab />}
    </>
  );
}

/* ═══ تب علوم پایه — Split View سه‌ستونه ═══ */
function BsTab({ initial = {} }) {
  const [intake, setIntake] = useState(initial.intake || '');
  const [scopeKind, setScopeKind] = useState('global');
  const [tree, setTree] = useState(null);
  const [intakes, setIntakes] = useState([]);
  const [err, setErr] = useState('');
  const [permErr, setPermErr] = useState(false);
  const [openTerms, setOpenTerms] = useState({});
  const [q, setQ] = useState(initial.q || '');
  const [sel, setSel] = useState([]);            // session ids برای عملیات گروهی
  const [lesId, setLesId] = useState(initial.lesson);      // درس منتخب (ستون دوم)
  const [sesId, setSesId] = useState(initial.session);      // جلسه‌ی منتخب (بازرس)
  const [editLes, setEditLes] = useState(null);  // lesson
  const [editSes, setEditSes] = useState(null);  // {lesson_id, s}
  const [confirm, setConfirm] = useState(null);
  const [moveTo, setMoveTo] = useState(null);    // {ids:[…]}
  const [quick, setQuick] = useState(false);
  const [addLes, setAddLes] = useState(null);    // term برای درس جدید
  const [addSes, setAddSes] = useState(null);    // lesson برای جلسه جدید
  const [studentPreview, setStudentPreview] = useState(false);
  const firstLoad = useRef(true);
  const preserveSelection = useRef(false);

  const load = async () => {
    setErr('');
    try {
      const r = await api.contentTree(intake || undefined);
      setTree(r.tree || []);
      setIntakes(r.intakes || []); setScopeKind(r.scope_kind || 'global');
      if (!intake && r.intake) setIntake(r.intake);
    } catch (e) {
      if (e.status === 403) setPermErr(true);
      else setErr(errText(e));
    }
  };
  useEffect(() => {
    setTree(null); setSel([]);
    if (!firstLoad.current && !preserveSelection.current) { setLesId(null); setSesId(null); }
    firstLoad.current = false; preserveSelection.current = false; load();
  }, [intake]);
  useEffect(() => { writeHashQuery('/content', { intake, q, lesson: lesId || '', session: sesId || '' }); }, [intake, q, lesId, sesId]);

  // انتخاب‌ها به‌صورت مشتق از درخت — بعد از هر reload همیشه تازه‌اند
  const selLesson = useMemo(() => {
    for (const t of (tree || [])) {
      const l = t.lessons.find(x => x.id === lesId);
      if (l) return { ...l, term: t.term, _tLessons: t.lessons };
    }
    return null;
  }, [tree, lesId]);
  const selSession = useMemo(
    () => (selLesson ? (selLesson.sessions.find(s => s.id === sesId) || null) : null),
    [selLesson, sesId]);
  // اگر درس/جلسه‌ی منتخب بعد از reload دیگر وجود نداشت، انتخاب پاک شود
  useEffect(() => { if (tree && lesId && !selLesson) { setLesId(null); setSesId(null); } }, [tree, lesId, selLesson]);
  useEffect(() => { if (selLesson && sesId && !selSession) setSesId(null); }, [selLesson, sesId, selSession]);

  const flatLessons = useMemo(() => {
    const out = [];
    (tree || []).forEach(t => t.lessons.forEach(l => out.push({ ...l, term: t.term })));
    return out;
  }, [tree]);
  const totals = useMemo(() => ({
    lessons: flatLessons.length,
    sessions: flatLessons.reduce((a, l) => a + (l.session_count || 0), 0),
    files: flatLessons.reduce((a, l) => a + (l.content_count || 0), 0),
  }), [flatLessons]);

  const intakeLabel = (code) => intakes.find(i => i.code === code)?.label || code;
  const lesMatch = (l) => !q.trim() || (l.name || '').includes(q.trim()) || (l.teacher || '').includes(q.trim());
  const sesMatch = (s) => !q.trim() || (s.topic || '').includes(q.trim()) || (s.teacher || '').includes(q.trim()) || String(s.number) === q.trim();

  const act = async (fn, okMsg = 'انجام شد') => {
    try { await fn(); toast(okMsg); load(); }
    catch (e) { toast(errText(e), 'err'); }
  };
  // 🌊 WA3 — reorder: پاسخ {ok:false} یعنی به مرز لیست رسیده‌ایم (خطا نیست)
  const reorder = async (fn, okMsg) => {
    try {
      const r = await fn();
      if (r && r.ok === false) return toast('به ابتدا/انتهای لیست رسیده‌اید', 'err');
      toast(okMsg); load();
    } catch (e) { toast(errText(e), 'err'); }
  };
  const bulk = async (body) => act(() => api.sessionsBulk(body).then(r => toast(`${fa(r.done)} مورد انجام شد`)));
  const toggleSel = (id) => setSel(x => x.includes(id) ? x.filter(i => i !== id) : [...x, id]);

  const delLesson = async (l) => {
    let impact = null; try { impact = await api.contentImpact('lesson', l.id); } catch {}
    setConfirm({ text: `حذف درس «${l.name}» با همه‌ی جلسات و فایل‌هایش؟${impact ? ` اثر بالقوه: ${fa(impact.affected_users)} کاربر، ${fa(impact.affected_sessions)} جلسه و ${fa(impact.affected_files)} فایل.` : ''}`,
      run: () => act(() => api.caDelLesson(l.id), 'درس حذف شد') });
  };
  const delSession = async (s) => {
    let impact = null; try { impact = await api.contentImpact('session', s.id); } catch {}
    setConfirm({ text: `حذف جلسه ${s.number} «${s.topic}» و فایل‌هایش؟${impact ? ` اثر بالقوه: ${fa(impact.affected_users)} کاربر و ${fa(impact.affected_files)} فایل.` : ''}`,
      run: async () => { await act(() => api.caDelSession(s.id), 'جلسه حذف شد'); setSesId(null); } });
  };

  if (permErr) return <NoPerm text="مدیریت محتوا فقط برای مدیران محتوا (سراسری/ورودی) است" />;
  if (err) return <ErrorState error={err} onRetry={load} />;

  const visSessions = selLesson ? selLesson.sessions.filter(sesMatch) : [];

  return (
    <>
      <PageHeader title="مرکز فرماندهی محتوا" description="درس‌ها ← جلسات ← بازرس فایل · نمای مؤثر سراسری و Override ورودی"
        actions={<><B>{fa(totals.lessons)} درس</B><B kind="acc">{fa(totals.sessions)} جلسه</B>
          <B kind="ok">{fa(totals.files)} فایل</B><button className="btn" onClick={() => setStudentPreview(true)}>👁 مشاهده به‌عنوان دانشجو</button><button className="btn primary" onClick={() => setQuick(true)}>⚡ آپلود سریع</button></>} />
      <SavedViews scope="content" filters={{ intake, q, lesson: lesId || '', session: sesId || '' }} onApply={f => {
        preserveSelection.current = (f.intake || '') !== intake; setIntake(f.intake || ''); setQ(f.q || ''); setLesId(f.lesson || null); setSesId(f.session || null);
      }} label="نماهای محتوایی" />

      {!tree ? <Loading rows={5} /> : (
        <div className="ct3-grid">
          {/* ── ستون ۱: درخت درس‌ها ─────────────────────── */}
          <div className="ct3-pane">
            <div className="ct3-ph">
              <span className="ct3-pt">📚 درس‌ها</span>
              <B>{fa(totals.lessons)}</B>
            </div>
            <select className="inp" value={intake} disabled={scopeKind === 'scoped'} onChange={e => setIntake(e.target.value)}>
              {scopeKind === 'global' && <option value="">🌐 سراسری (پایه)</option>}
              {intakes.map(i => <option key={i.code} value={i.code}>🏷 {i.label || i.code}</option>)}
            </select>
            <input className="inp" placeholder="🔎 نام درس/استاد/موضوع جلسه…"
                   value={q} onChange={e => setQ(e.target.value)} />
            {tree.map(t => {
              const visLes = t.lessons.filter(lesMatch);
              if (q.trim() && visLes.length === 0) return null;
              return (
                <div key={t.term} className="ct3-term">
                  <div className="ct3-term-head" onClick={() => setOpenTerms(s => ({ ...s, [t.term]: !s[t.term] }))}>
                    <span>{TERM_ICON}</span><b>{t.term}</b>
                    <B>{fa(t.lessons.length)}</B>
                    <span className="spacer" />
                    <button className="btn sm" title="افزودن درس به این ترم" aria-label="افزودن درس به این ترم"
                            onClick={e => { e.stopPropagation(); setAddLes(t.term); }}>➕</button>
                    <span className="muted">{openTerms[t.term] === false ? '◂' : '▾'}</span>
                  </div>
                  {openTerms[t.term] !== false && (
                    visLes.length === 0
                      ? <div className="ct3-none muted">درسی نیست</div>
                      : visLes.map(l => {
                          const idx = t.lessons.findIndex(x => x.id === l.id);
                          return (
                            <div key={l.id} className={`ct3-les ${lesId === l.id ? 'on' : ''}`}
                                 onClick={() => { setLesId(l.id); setSesId(null); setSel([]); }}>
                              <div className="ct3-r1">
                                <span className="ct3-ic">{lesId === l.id ? '📖' : '📘'}</span>
                                <div className="ct3-main">
                                  <div className="ct3-t1">{l.name}</div>
                                  <div className="ct3-t2">{l.teacher || '—'}</div>
                                </div>
                                {l.intake && <B kind="purple">🏷 {intakeLabel(l.intake)}</B>}
                              </div>
                              <div className="ct3-r2">
                                <B>{fa(l.session_count)} جلسه</B>
                                <B kind="acc">{fa(l.content_count)} فایل</B>
                                <span className="spacer" />
                                {l.readonly ? <B>🔒 فقط‌خواندنی</B> : <>
                                  <button className="btn sm" title="بالا" aria-label="بالا" disabled={idx <= 0}
                                          onClick={e => { e.stopPropagation(); reorder(() => api.waReorderLesson(l.id, 'up'), 'درس مرتب شد ↑'); }}>↑</button>
                                  <button className="btn sm" title="پایین" aria-label="پایین" disabled={idx >= t.lessons.length - 1}
                                          onClick={e => { e.stopPropagation(); reorder(() => api.waReorderLesson(l.id, 'down'), 'درس مرتب شد ↓'); }}>↓</button>
                                  <button className="btn sm" title="ویرایش نام و استاد" aria-label="ویرایش نام و استاد"
                                          onClick={e => { e.stopPropagation(); setEditLes(l); }}>✏️</button>
                                  <button className="btn sm" title="جلسه‌ی جدید" aria-label="جلسه‌ی جدید"
                                          onClick={e => { e.stopPropagation(); setAddSes(l); }}>➕</button>
                                  <button className="btn sm danger" title="حذف درس" aria-label="حذف درس"
                                          onClick={e => { e.stopPropagation(); delLesson(l); }}>🗑</button>
                                </>}
                              </div>
                            </div>
                          );
                        })
                  )}
                </div>
              );
            })}
            {tree.length === 0 && (
              <Empty icon="🌱" text="هنوز ساختار محتوایی نیست">
                <span className="muted">با دکمه‌ی ➕ کنار هر ترم نخستین درس را بسازید</span>
              </Empty>
            )}
          </div>

          {/* ── ستون ۲: جلسات درس منتخب ─────────────────── */}
          <div className="ct3-pane">
            <div className="ct3-ph">
              <span className="ct3-pt">🗂 جلسات</span>
              {selLesson && <B kind="acc">{selLesson.name}</B>}
              {selLesson && <B>{fa(selLesson.sessions.length)}</B>}
              <span className="spacer" />
              {selLesson && !selLesson.readonly && <button className="btn sm primary" onClick={() => setAddSes(selLesson)}>➕ جلسه</button>}
            </div>
            {sel.length > 0 && (
              <div className="ct3-bulk">
                <B kind="acc">{fa(sel.length)} انتخاب</B>
                <button className="btn sm" onClick={() => bulk({ action: 'duplicate', ids: sel }).then(() => setSel([]))}>📄 کلون</button>
                <button className="btn sm" onClick={() => setMoveTo({ ids: sel })}>📦 انتقال</button>
                <button className="btn sm danger" onClick={() => setConfirm({
                  text: `حذف ${fa(sel.length)} جلسه (به‌همراه فایل‌ها و نسخه‌های اختصاصی وابسته)؟`,
                  run: () => bulk({ action: 'delete', ids: sel }).then(() => { setSel([]); setSesId(null); }),
                })}>🗑 حذف</button>
                <span className="spacer" />
                <button className="btn sm" onClick={() => setSel([])}>لغو</button>
              </div>
            )}
            {!selLesson ? (
              <Empty icon="📚" text="نخست از ستون درس‌ها یک درس برگزینید" />
            ) : visSessions.length === 0 ? (
              <Empty icon="📭" text={q.trim() ? 'جلسه‌ای با این جست‌وجو نیست' : 'این درس هنوز جلسه‌ای ندارد'}>
                {!q.trim() && !selLesson.readonly && <button className="btn primary" onClick={() => setAddSes(selLesson)}>➕ نخستین جلسه</button>}
              </Empty>
            ) : visSessions.map(s => {
              const idx = selLesson.sessions.findIndex(x => x.id === s.id);
              return (
                <div key={s.id}
                     className={`ct3-ses ${sesId === s.id ? 'on' : ''} ${sel.includes(s.id) ? 'sel' : ''}`}
                     onClick={() => setSesId(s.id)}>
                  <div className="ct3-r1">
                    {!s.readonly && <input type="checkbox" checked={sel.includes(s.id)}
                           onClick={e => e.stopPropagation()} onChange={() => toggleSel(s.id)}
                           aria-label="انتخاب جلسه" />}
                    <span className="ct3-num">{fa(s.number)}</span>
                    <div className="ct3-main">
                      <div className="ct3-t1">{s.topic || '—'}</div>
                      <div className="ct3-t2">{s.teacher || ''}</div>
                    </div>
                    <B kind={KIND[s.kind].kind}>
                      {KIND[s.kind].icon} {s.kind === 'global' ? 'سراسری' : (s.intake_label || s.intake)}
                    </B>
                  </div>
                  <div className="ct3-r2">
                    <span className="muted">
                      {Object.entries(s.types || {}).map(([k, v]) => `${CTYPE[k] || '📎'}${fa(v)}`).join(' ') || 'بدون فایل'}
                    </span>
                    <span className="spacer" />
                    {s.readonly && <B>🔒 فقط‌خواندنی</B>}
                    {s.kind === 'global' && intake &&
                      <button className="btn sm warn" title="ساخت نسخه اختصاصی برای این ورودی" aria-label="ساخت نسخه اختصاصی برای این ورودی"
                              onClick={e => { e.stopPropagation(); act(() => api.caForkSession(s.id, intake), 'نسخه‌ی اختصاصی ساخته شد ⭐'); }}>🍴</button>}
                    {!s.readonly && <>
                      <button className="btn sm" title="بالا" aria-label="بالا" disabled={idx <= 0}
                              onClick={e => { e.stopPropagation(); reorder(() => api.waReorderSession(s.id, 'up'), 'مرتب شد ↑'); }}>↑</button>
                      <button className="btn sm" title="پایین" aria-label="پایین" disabled={idx >= selLesson.sessions.length - 1}
                              onClick={e => { e.stopPropagation(); reorder(() => api.waReorderSession(s.id, 'down'), 'مرتب شد ↓'); }}>↓</button>
                      {s.kind === 'fork' &&
                        <button className="btn sm" title="حذف نسخه اختصاصی (بازگشت به سراسری)" aria-label="حذف نسخه اختصاصی (بازگشت به سراسری)"
                                onClick={e => { e.stopPropagation(); act(() => api.caUnforkSession(s.id), 'به نسخه‌ی سراسری برگشت ↩️'); }}>↩️</button>}
                      <button className="btn sm" title="کلون" aria-label="کلون"
                              onClick={e => { e.stopPropagation(); act(() => api.dupSession(s.id), 'کلون ساخته شد 📄'); }}>📄</button>
                      <button className="btn sm" title="ویرایش شماره/موضوع/استاد" aria-label="ویرایش شماره/موضوع/استاد"
                              onClick={e => { e.stopPropagation(); setEditSes({ lesson_id: selLesson.id, s }); }}>✏️</button>
                      <button className="btn sm danger" title="حذف" aria-label="حذف"
                              onClick={e => { e.stopPropagation(); delSession(s); }}>🗑</button>
                    </>}
                  </div>
                </div>
              );
            })}
          </div>

          {/* ── ستون ۳: بازرس ──────────────────────────── */}
          <div className="ct3-pane ct3-insp">
            <div className="ct3-ph">
              <span className="ct3-pt">🔎 بازرس</span>
              {selSession && <B kind={KIND[selSession.kind].kind}>{KIND[selSession.kind].icon} {KIND[selSession.kind].label}</B>}
            </div>
            {!selLesson ? (
              <Empty icon="🧭" text="برای بازبینی، نخست یک درس و سپس یک جلسه را برگزینید" />
            ) : !selSession ? (
              <>
                <div className="ct3-kv"><span className="muted">درس</span><b>{selLesson.name}</b></div>
                <div className="ct3-kv"><span className="muted">ترم</span><span>{selLesson.term}</span></div>
                <div className="ct3-kv"><span className="muted">استاد</span><span>{selLesson.teacher || '—'}</span></div>
                <div className="ct3-kv"><span className="muted">دامنه</span>
                  <ScopeBadge scope={selLesson.intake || 'global'} label={selLesson.intake ? intakeLabel(selLesson.intake) : 'سراسری'} />
                </div>
                <div className="ct3-stats">
                  <div className="ct3-stat"><b>{fa(selLesson.session_count)}</b><span>جلسه</span></div>
                  <div className="ct3-stat"><b>{fa(selLesson.content_count)}</b><span>فایل</span></div>
                  <div className="ct3-stat"><b>
                    {fa(selLesson.sessions.filter(s => s.kind !== 'global').length)}
                  </b><span>نسخه‌ی خاص</span></div>
                </div>
                <div className="row">
                  {selLesson.readonly ? <B>🔒 این درس سراسری برای scope شما فقط‌خواندنی است</B> : <>
                    <button className="btn" onClick={() => setEditLes(selLesson)}>✏️ ویرایش درس</button>
                    <button className="btn primary" style={{ flex: 1 }} onClick={() => setAddSes(selLesson)}>➕ جلسه‌ی جدید</button>
                    <button className="btn danger" onClick={() => delLesson(selLesson)}>🗑 حذف درس</button>
                  </>}
                </div>
                <ContentHistory targetType="lesson" targetId={selLesson.id} />
                <p className="muted" style={{ margin: '4px 2px' }}>💡 برای دیدن و مدیریت فایل‌ها، از ستون میانی یک جلسه را برگزینید.</p>
              </>
            ) : (
              <SessionInspector lesson={selLesson} session={selSession} intake={intake}
                onTreeChanged={load}
                onEdit={(s) => setEditSes({ lesson_id: selLesson.id, s })}
                onFork={(s) => act(() => api.caForkSession(s.id, intake), 'نسخه‌ی اختصاصی ساخته شد ⭐')}
                onUnfork={(s) => act(() => api.caUnforkSession(s.id), 'به نسخه‌ی سراسری برگشت ↩️')}
                onClone={(s) => act(() => api.dupSession(s.id), 'کلون ساخته شد 📄')}
                onMove={(s) => setMoveTo({ ids: [s.id] })}
                onDelete={delSession} />
            )}
          </div>
        </div>
      )}

      {editLes && <EditLesson lesson={editLes} onClose={(ch) => { setEditLes(null); if (ch) load(); }} />}
      {editSes && <EditSession {...editSes} onClose={(ch) => { setEditSes(null); if (ch) load(); }} />}
      {quick && <QuickUpload intakes={intakes} intake={intake} onClose={(ch) => { setQuick(false); if (ch) load(); }} />}
      {addLes && <AddLesson term={addLes} intake={intake} onClose={(ch) => { setAddLes(null); if (ch) load(); }} />}
      {addSes && <AddSession lesson={addSes} onClose={(ch) => { setAddSes(null); if (ch) { load(); setLesId(addSes.id); } }} />}
      {moveTo && <MoveSessions lessons={flatLessons} sel={moveTo.ids}
                               onClose={(ch) => {
                                 setMoveTo(null);
                                 if (ch) {
                                   setSel([]);
                                   setSesId(prev => (moveTo.ids.includes(prev) ? null : prev));
                                   load();
                                 }
                               }} />}
      {confirm && <Confirm text={confirm.text} danger
                           onYes={async () => { await confirm.run(); setConfirm(null); }}
                           onNo={() => setConfirm(null)} />}
      {studentPreview && <StudentPreview onClose={() => setStudentPreview(false)} />}
    </>
  );
}

/* ── 🔎 بازرس جلسه: مشخصات + اکشن‌ها + مدیریت کامل فایل‌ها ── */
function SessionInspector({ lesson, session, intake, onTreeChanged, onEdit, onFork, onUnfork, onClone, onMove, onDelete }) {
  return (
    <>
      <div className="ct3-kv"><span className="muted">جلسه</span><b className="num">{fa(session.number)}</b></div>
      <div className="ct3-kv"><span className="muted">موضوع</span><span>{session.topic || '—'}</span></div>
      <div className="ct3-kv"><span className="muted">درس</span><span>{lesson.name} <span className="muted">· {lesson.term}</span></span></div>
      <div className="ct3-kv"><span className="muted">استاد</span><span>{session.teacher || lesson.teacher || '—'}</span></div>
      <div className="ct3-kv"><span className="muted">وضعیت</span>
        <ScopeBadge scope={session.kind} label={session.kind === 'global' ? 'سراسری' : (session.intake_label || session.intake)} />
      </div>
      <div className="ct3-kv"><span className="muted">مالکیت و ویرایش</span><span>{session.kind === 'global' ? 'مالک سراسری محتوا' : `ورودی ${session.intake_label || session.intake}`} · {session.readonly ? 'فقط مشاهده' : 'قابل ویرایش در scope فعلی'}</span></div>
      <div className="ct3-acts">
        {session.readonly && <B>🔒 فقط‌خواندنی</B>}
        {session.kind === 'global' && intake &&
          <button className="btn sm warn" onClick={() => onFork(session)}>🍴 نسخه‌ی اختصاصی</button>}
        {!session.readonly && <>
          <button className="btn sm" onClick={() => onEdit(session)}>✏️ ویرایش</button>
          {session.kind === 'fork' &&
            <button className="btn sm" onClick={() => onUnfork(session)}>↩️ بازگشت به سراسری</button>}
          <button className="btn sm" onClick={() => onClone(session)}>📄 کلون</button>
          <button className="btn sm" onClick={() => onMove(session)}>📦 انتقال</button>
          <button className="btn sm danger" onClick={() => onDelete(session)}>🗑 حذف</button>
        </>}
      </div>
      <ImpactPanel targetType="session" targetId={session.id} />
      <ContentHistory targetType="session" targetId={session.id} />
      <SessionFiles session={session} onTreeChanged={onTreeChanged} />
    </>
  );
}

function ImpactPanel({ targetType, targetId }) {
  const [data, setData] = useState(null);
  useEffect(() => { let active = true; setData(null); api.contentImpact(targetType, targetId).then(r => active && setData(r)).catch(() => active && setData(false)); return () => { active = false; }; }, [targetType, targetId]);
  if (data === false) return null;
  return <div className="surface-inset" style={{ padding: 10 }}>
    <div className="muted">🎯 تحلیل اثر واقعی</div>
    {!data ? <Loading rows={1} variant="tree" /> : <><div className="row" style={{ marginTop: 6 }}>
      <B kind="acc">{fa(data.affected_users)} کاربر بالقوه</B><B>{fa(data.affected_sessions)} جلسه</B><B>{fa(data.affected_files)} فایل</B>
      <ScopeBadge scope={data.intake ? 'exclusive' : 'global'} label={data.intake || 'سراسری'} />
    </div><div className="muted" style={{ marginTop: 5 }}>{data.explanation}</div></>}
  </div>;
}

function StudentPreview({ onClose }) {
  const [q, setQ] = useState(''); const [hits, setHits] = useState(null); const [student, setStudent] = useState(null);
  const [root, setRoot] = useState(null); const [lessons, setLessons] = useState([]); const [sessions, setSessions] = useState([]); const [files, setFiles] = useState([]);
  const [term, setTerm] = useState(''); const [lesson, setLesson] = useState(''); const [session, setSession] = useState(''); const [busy, setBusy] = useState(false); const [err, setErr] = useState('');
  const search = async () => { if (q.trim().length < 2) return; setBusy(true); setErr(''); try { const r = await api.studentPreviewStudents(q.trim()); setHits(r.students || []); } catch (e) { setErr(errText(e)); } setBusy(false); };
  const choose = async user => { setBusy(true); setErr(''); try { const r = await api.studentPreview(user.id); setStudent(user); setRoot(r); setHits(null); } catch (e) { setErr(errText(e)); } setBusy(false); };
  const chooseTerm = async value => { setTerm(value); setLesson(''); setSession(''); setSessions([]); setFiles([]); setBusy(true); try { setLessons((await api.studentPreviewLessons(student.id, value)).lessons || []); } catch (e) { setErr(errText(e)); } setBusy(false); };
  const chooseLesson = async value => { setLesson(value); setSession(''); setFiles([]); setBusy(true); try { setSessions((await api.studentPreviewSessions(student.id, value)).sessions || []); } catch (e) { setErr(errText(e)); } setBusy(false); };
  const chooseSession = async value => { setSession(value); setBusy(true); try { setFiles((await api.studentPreviewFiles(student.id, value)).files || []); } catch (e) { setErr(errText(e)); } setBusy(false); };
  return <Modal wide title="👁 مشاهده محتوا به‌عنوان دانشجو" onClose={onClose}>
    <div className="panel panel-pad" style={{ background: 'var(--bg)' }}><B kind="acc">Resolver مشترک Mini App</B><span className="muted" style={{ marginInlineStart: 8 }}>این نما مستقیماً همان توابع terms/lessons/sessions/files دانشجو را اجرا می‌کند.</span></div>
    {!student ? <><div className="row" style={{ marginTop: 10 }}><input className="inp" style={{ flex: 1 }} value={q} onChange={e => setQ(e.target.value)} onKeyDown={e => e.key === 'Enter' && search()} placeholder="نام، شماره دانشجویی، یوزرنیم یا Telegram ID…" /><button className="btn" disabled={busy} onClick={search}>جست‌وجو</button></div>
      <div className="grid" style={{ gap: 6, marginTop: 8 }}>{(hits || []).map(user => <button key={user.id} className="pick" onClick={() => choose(user)}><b>{user.display_name || user.name}</b><span className="muted">{user.student_id || `#${user.id}`} · {user.intake || 'بدون ورودی'}</span></button>)}</div></> : <>
      <div className="row" style={{ marginTop: 10 }}><B kind="purple">{root?.student?.name}</B><B>{root?.student?.intake || 'بدون ورودی'}</B><B>گروه {root?.student?.group || '—'}</B><button className="btn sm" onClick={() => { setStudent(null); setRoot(null); }}>تغییر دانشجو</button></div>
      <div className="student-preview-grid">
        <div><b>ترم‌ها</b>{(root?.terms || []).map(item => <button key={item.name} className={`pick ${term === item.name ? 'on' : ''}`} onClick={() => chooseTerm(item.name)}>{item.name}<B>{fa(item.lesson_count)}</B></button>)}</div>
        <div><b>درس‌ها</b>{lessons.map(item => <button key={item._id} className={`pick ${lesson === item._id ? 'on' : ''}`} onClick={() => chooseLesson(item._id)}>{item.name}<span className="muted">{item.teacher}</span></button>)}</div>
        <div><b>جلسات</b>{sessions.map(item => <button key={item._id} className={`pick ${session === item._id ? 'on' : ''}`} onClick={() => chooseSession(item._id)}>جلسه {fa(item.number)} · {item.topic}<B>{fa(item.file_count)}</B></button>)}</div>
        <div><b>فایل‌های قابل مشاهده</b>{files.map(item => <div className="panel panel-pad" key={item.id}><b>{item.name}</b><div className="muted">{item.type} · {fa(item.downloads)} دریافت</div></div>)}</div>
      </div></>}
    {busy && <Loading rows={2} />}{err && <ErrorState error={err} onRetry={() => setErr('')} />}
  </Modal>;
}

function ContentHistory({ targetType, targetId }) {
  const [items, setItems] = useState(null);
  const [err, setErr] = useState('');
  const requestSeq = useRef(0);

  const load = async () => {
    const seq = ++requestSeq.current;
    setItems(null); setErr('');
    try {
      const r = await api.contentHistory(targetType, targetId);
      if (seq === requestSeq.current) setItems(r.items || []);
    } catch (e) {
      if (seq === requestSeq.current) setErr(errText(e));
    }
  };

  useEffect(() => {
    load();
    return () => { requestSeq.current += 1; };
  }, [targetType, targetId]);

  return <div className="surface-inset" style={{ padding: 10 }}>
    <div className="muted" style={{ marginBottom: 7 }}>🕓 تاریخچه تغییرات</div>
    {err ? <ErrorState error={err} onRetry={load} />
      : !items ? <Loading rows={2} variant="tree" />
        : <Timeline items={items.slice(0, 6)} empty="هنوز رویدادی برای این مورد ثبت نشده" />}
  </div>;
}

/* ── 📁 فایل‌های جلسه (داخل بازرس): لیست + آپلود + گروهی ── */
function SessionFiles({ session, onTreeChanged }) {
  const [items, setItems] = useState(null);
  const [readonly, setReadonly] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [showUp, setShowUp] = useState(false);
  const [form, setForm] = useState({ ctype: 'pdf', description: '', extra_info: '' });
  const [file, setFile] = useState(null);
  const [sel, setSel] = useState([]);
  const fileRef = useRef(null);

  const load = async () => {
    setErr('');
    try {
      const r = await api.caSessionContent(session.id);
      setItems(r.content || []); setReadonly(!!r.readonly);
    } catch (e) { setErr(errText(e)); }
  };
  useEffect(() => { setItems(null); setSel([]); setShowUp(false); load(); }, [session.id]);

  const changed = () => { load(); onTreeChanged(); };
  const upload = async () => {
    if (!file) return toast('ابتدا فایل را انتخاب کنید', 'err');
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append('ctype', form.ctype);
      fd.append('description', form.description || file.name);
      fd.append('extra_info', form.extra_info);
      fd.append('file', file);
      await api.caAddContent(session.id, fd);
      toast('آپلود شد ✅'); setFile(null); setForm({ ctype: 'pdf', description: '', extra_info: '' });
      if (fileRef.current) fileRef.current.value = '';
      setShowUp(false); changed();
    } catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };
  const del = async (cid) => {
    try { await api.caDelContent(cid); toast('حذف شد'); changed(); }
    catch (e) { toast(errText(e), 'err'); }
  };
  const reorderItem = async (cid, direction) => {
    try {
      const r = await api.waReorderItem(cid, direction);
      if (r && r.ok === false) return toast('به ابتدا/انتهای لیست رسیده‌اید', 'err');
      changed();
    } catch (e) { toast(errText(e), 'err'); }
  };
  const guess = (name) => EXT_MAP[(name.split('.').pop() || '').toLowerCase()] || 'pdf';
  const toggleSel = (id) => setSel(x => x.includes(id) ? x.filter(i => i !== id) : [...x, id]);

  return (
    <div className="ct3-files">
      <div className="ct3-ph" style={{ marginTop: 2 }}>
        <b style={{ fontSize: 'var(--fs-card)' }}>📁 فایل‌ها</b>
        {items && <B>{fa(items.length)}</B>}
        <span className="spacer" />
        {readonly ? <B>🔒 فقط‌خواندنی</B> :
          <button className="btn sm primary" onClick={() => setShowUp(x => !x)}>{showUp ? '✕ بستن' : '➕ افزودن فایل'}</button>}
      </div>
      {showUp && (
        <div className="ct3-up">
          <input ref={fileRef} type="file" className="inp"
                 onChange={e => {
                   const f = e.target.files[0] || null;
                   setFile(f);
                   if (f) setForm(x => ({ ...x, ctype: guess(f.name), description: x.description || f.name }));
                 }} />
          <div className="row">
            <select className="inp" value={form.ctype} onChange={e => setForm({ ...form, ctype: e.target.value })}>
              {Object.entries(CTYPE).map(([k, v]) => <option key={k} value={k}>{v} {k}</option>)}
            </select>
            <input className="inp" style={{ flex: 1 }} placeholder="توضیح (عنوان نمایشی)…"
                   value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} />
          </div>
          <input className="inp" placeholder="اطلاعات تکمیلی (اختیاری)…"
                 value={form.extra_info} onChange={e => setForm({ ...form, extra_info: e.target.value })} />
          <button className="btn primary" disabled={busy || !file} onClick={upload}>
            {busy ? '⏳ در حال آپلود…' : '⬆️ آپلود (از مسیر تلگرام)'}</button>
        </div>
      )}
      {err ? <ErrorState error={err} onRetry={load} /> : !items ? <Loading rows={3} /> : (
        <>
          {sel.length > 0 && (
            <div className="ct3-bulk">
              <B kind="acc">{fa(sel.length)} انتخاب</B>
              <button className="btn sm danger" onClick={async () => {
                try {
                  const r = await api.itemsBulk({ action: 'delete', ids: sel });
                  toast(`${fa(r.done)} فایل حذف شد`); setSel([]); changed();
                } catch (e) { toast(errText(e), 'err'); }
              }}>🗑 حذف گروهی</button>
              <MoveItemsButton sel={sel} sessionId={session.id}
                               onDone={() => { setSel([]); changed(); }} />
              <span className="spacer" />
              <button className="btn sm" onClick={() => setSel([])}>لغو</button>
            </div>
          )}
          {items.length === 0 && <Empty icon="📭" text="فایلی برای این جلسه نیست" />}
          {items.map((c, i) => (
            <div key={c.id} className={`ct3-file ${sel.includes(c.id) ? 'sel' : ''}`}>
              <div className="ct3-r1">
                {!readonly && <input type="checkbox" checked={sel.includes(c.id)} onChange={() => toggleSel(c.id)} aria-label="انتخاب فایل" />}
                <span style={{ fontSize: 16 }}>{CTYPE[c.type] || '📎'}</span>
                <div className="ct3-main">
                  <div className="ct3-t1">{c.description || '(بدون توضیح)'}</div>
                  {c.extra_info && <div className="ct3-t2">{c.extra_info}</div>}
                </div>
                <B>{fa(c.downloads)} DL</B>
              </div>
              <div className="ct3-r2">
                <span className="muted">{c.type}</span>
                <span className="spacer" />
                {!readonly && <>
                  <button className="btn sm" title="بالا" aria-label="بالا" disabled={i <= 0} onClick={() => reorderItem(c.id, 'up')}>↑</button>
                  <button className="btn sm" title="پایین" aria-label="پایین" disabled={i >= items.length - 1} onClick={() => reorderItem(c.id, 'down')}>↓</button>
                  <button className="btn sm danger" title="حذف فایل" aria-label="حذف فایل" onClick={() => del(c.id)}>🗑</button>
                </>}
              </div>
            </div>
          ))}
        </>
      )}
    </div>
  );
}

function MoveItemsButton({ sel, sessionId, onDone }) {
  const [target, setTarget] = useState('');
  const [open, setOpen] = useState(false);
  return (
    <>
      <button className="btn sm" onClick={() => setOpen(true)}>📦 انتقال به جلسه…</button>
      {open && (
        <Modal title="انتقال فایل‌ها به جلسه‌ی دیگر" onClose={() => setOpen(false)}>
          <p className="muted" style={{ marginBottom: 10 }}>شناسه‌ی جلسه‌ی مقصد را وارد کنید (از نشانی/کارت جلسه کپی کنید):</p>
          <input className="inp" style={{ width: '100%', direction: 'ltr' }} placeholder="session id مقصد…"
                 value={target} onChange={e => setTarget(e.target.value)} />
          <div className="row" style={{ marginTop: 12 }}>
            <button className="btn primary" disabled={!target.trim()} onClick={async () => {
              try {
                const r = await api.itemsBulk({ action: 'move', ids: sel, target_session: target.trim() });
                toast(`${fa(r.done)} فایل منتقل شد`); setOpen(false); onDone();
              } catch (e) { toast(errText(e), 'err'); }
            }}>انتقال</button>
            <button className="btn" onClick={() => setOpen(false)}>انصراف</button>
          </div>
        </Modal>
      )}
    </>
  );
}

/* ── ✏️ ویرایش درس/جلسه ───────────────────────────────── */
function EditLesson({ lesson, onClose }) {
  const [name, setName] = useState(lesson.name || '');
  const [teacher, setTeacher] = useState(lesson.teacher || '');
  const [busy, setBusy] = useState(false);
  return <Modal title={`✏️ ویرایش درس — ${lesson.name}`} onClose={() => onClose(false)}>
    <div className="grid" style={{ gap: 10 }}>
      <label className="fld"><span>نام درس</span><input className="inp" value={name} onChange={e => setName(e.target.value)} /></label>
      <label className="fld"><span>استاد</span><input className="inp" value={teacher} onChange={e => setTeacher(e.target.value)} /></label>
      <div className="row"><button className="btn primary" disabled={busy || !name.trim()} onClick={async () => {
        setBusy(true);
        try { await api.caEditLesson(lesson.id, { name: name.trim(), teacher: teacher.trim() }); toast('درس ویرایش شد ✅'); onClose(true); }
        catch (e) { toast(errText(e), 'err'); setBusy(false); }
      }}>ذخیره</button><button className="btn" onClick={() => onClose(false)}>انصراف</button></div>
    </div>
  </Modal>;
}


function EditSession({ s, onClose }) {
  const [number, setNumber] = useState(s.number || 1);
  const [topic, setTopic] = useState(s.topic || '');
  const [teacher, setTeacher] = useState(s.teacher || '');
  const [busy, setBusy] = useState(false);
  return (
    <Modal title={`✏️ ویرایش جلسه ${fa(s.number)}`} onClose={() => onClose(false)}>
      <div className="grid" style={{ gap: 10 }}>
        <label className="fld"><span>شماره جلسه</span><input className="inp" type="number" min="1" value={number} onChange={e => setNumber(e.target.value)} /></label>
        <input className="inp" placeholder="موضوع جلسه…" value={topic} onChange={e => setTopic(e.target.value)} />
        <input className="inp" placeholder="استاد…" value={teacher} onChange={e => setTeacher(e.target.value)} />
        <div className="row">
          <button className="btn primary" disabled={busy || Number(number) < 1 || !topic.trim()} onClick={async () => {
            setBusy(true);
            try {
              await api.caEditSession(s.id, { number: Number(number), topic: topic.trim(), teacher: teacher.trim() });
              toast('شماره و اطلاعات جلسه ذخیره شد ✅'); onClose(true);
            } catch (e) { toast(errText(e), 'err'); setBusy(false); }
          }}>ذخیره</button>
          <button className="btn" onClick={() => onClose(false)}>انصراف</button>
        </div>
      </div>
    </Modal>
  );
}

function AddSession({ lesson, onClose }) {
  const [number, setNumber] = useState((lesson.sessions?.length ? Math.max(...lesson.sessions.map(x => x.number || 0)) : 0) + 1);
  const [topic, setTopic] = useState('');
  const [teacher, setTeacher] = useState('');
  const [busy, setBusy] = useState(false);
  return (
    <Modal title={`➕ جلسه‌ی جدید — ${lesson.name}`} onClose={() => onClose(false)}>
      <div className="grid" style={{ gap: 10 }}>
        <input className="inp" type="number" min="1" value={number} onChange={e => setNumber(+e.target.value)} />
        <input className="inp" placeholder="موضوع جلسه…" value={topic} onChange={e => setTopic(e.target.value)} />
        <input className="inp" placeholder="استاد…" value={teacher} onChange={e => setTeacher(e.target.value)} />
        <div className="row">
          <button className="btn primary" disabled={busy || !topic.trim()} onClick={async () => {
            setBusy(true);
            try {
              await api.caAddSession(lesson.id, { number, topic: topic.trim(), teacher: teacher.trim() });
              toast('جلسه ساخته شد'); onClose(true);
            } catch (e) { toast(errText(e), 'err'); }
            setBusy(false);
          }}>ایجاد</button>
          <button className="btn" onClick={() => onClose(false)}>انصراف</button>
        </div>
      </div>
    </Modal>
  );
}

/* ── ➕ درس ─────────────────────────────────────────── */
function AddLesson({ term, intake, onClose }) {
  const [name, setName] = useState('');
  const [teacher, setTeacher] = useState('');
  const [busy, setBusy] = useState(false);
  return (
    <Modal title={`➕ درس جدید — ${term}${intake ? ' · مختص ورودی' : ' · سراسری'}`} onClose={() => onClose(false)}>
      <div className="grid" style={{ gap: 10 }}>
        <input className="inp" placeholder="نام درس…" value={name} onChange={e => setName(e.target.value)} />
        <input className="inp" placeholder="استاد…" value={teacher} onChange={e => setTeacher(e.target.value)} />
        <div className="row">
          <button className="btn primary" disabled={busy || !name.trim()} onClick={async () => {
            setBusy(true);
            try {
              await api.caAddLesson({ term, name: name.trim(), teacher: teacher.trim(), intake: intake || '' });
              toast('درس ساخته شد'); onClose(true);
            } catch (e) { toast(errText(e), 'err'); }
            setBusy(false);
          }}>ایجاد</button>
          <button className="btn" onClick={() => onClose(false)}>انصراف</button>
        </div>
      </div>
    </Modal>
  );
}

/* ── 📦 انتقال گروهی/تکی جلسات ─────────────────────── */
function MoveSessions({ lessons, sel, onClose }) {
  const [target, setTarget] = useState('');
  const [busy, setBusy] = useState(false);
  return (
    <Modal title={`📦 انتقال ${fa(sel.length)} جلسه به درس دیگر`} onClose={() => onClose(false)}>
      <select className="inp" style={{ width: '100%' }} value={target} onChange={e => setTarget(e.target.value)}>
        <option value="">انتخاب درس مقصد…</option>
        {lessons.map(l => <option key={l.id} value={l.id}>{l.term} — {l.name}</option>)}
      </select>
      <div className="row" style={{ marginTop: 12 }}>
        <button className="btn primary" disabled={busy || !target} onClick={async () => {
          setBusy(true);
          try {
            const r = await api.sessionsBulk({ action: 'move', ids: sel, target_lesson: target });
            toast(`${fa(r.done)} جلسه منتقل شد`); onClose(true);
          } catch (e) { toast(errText(e), 'err'); }
          setBusy(false);
        }}>انتقال</button>
        <button className="btn" onClick={() => onClose(false)}>انصراف</button>
      </div>
    </Modal>
  );
}

/* ── ⚡ آپلود سریع چندفایلی — پیشنهاد خودکار نوع از پسوند ─ */
function QuickUpload({ intakes, intake, onClose }) {
  const [scIntake, setScIntake] = useState(intake || '');
  const [tree, setTree] = useState(null);
  const [lessonId, setLessonId] = useState('');
  const [sessionId, setSessionId] = useState('');
  const [files, setFiles] = useState([]);       // {file, ctype, description, status, error}
  const [prog, setProg] = useState(null);       // {done,total,ok,failed}
  const [dragging, setDragging] = useState(false);
  const pickerRef = useRef(null);

  useEffect(() => {
    setTree(null);
    api.contentTree(scIntake || undefined).then(r => setTree(r.tree || [])).catch(e => toast(errText(e), 'err'));
  }, [scIntake]);

  const lessons = useMemo(() => {
    const out = [];
    (tree || []).forEach(t => t.lessons.forEach(l => out.push({ ...l, term: t.term })));
    return out;
  }, [tree]);
  const lesson = lessons.find(l => l.id === lessonId);
  const sessions = lesson ? lesson.sessions : [];

  const addFiles = (fl) => {
    const next = [...files];
    const seen = new Set(next.map(x => `${x.file.name}:${x.file.size}`));
    for (const f of Array.from(fl || [])) {
      const signature = `${f.name}:${f.size}`;
      if (seen.has(signature)) continue;
      seen.add(signature);
      const ext = (f.name.split('.').pop() || '').toLowerCase();
      const ctype = EXT_MAP[ext];
      let error = '';
      if (!ctype) error = 'پسوند این فایل در Content Typeهای فعلی پشتیبانی نمی‌شود';
      else if (f.size > 45 * 1024 * 1024) error = 'حجم بیشتر از سقف ۴۵MB است';
      next.push({
        file: f, ctype: ctype || 'pdf', description: f.name.replace(/\.[^.]+$/, ''),
        status: error ? 'invalid' : 'pending', error,
      });
    }
    setFiles(next.slice(0, 30));
  };
  const ready = files.filter(x => ['pending', 'error'].includes(x.status) && !x.error.includes('پشتیبانی') && !x.error.includes('۴۵MB'));
  const guess_ok = ready.length > 0 && lessonId && sessionId;

  const run = async (retryOnly = false) => {
    const indexes = files.map((it, i) => ({ it, i })).filter(({ it }) =>
      retryOnly ? it.status === 'error' : ['pending', 'error'].includes(it.status) && !it.error.includes('پشتیبانی') && !it.error.includes('۴۵MB'));
    if (!indexes.length) return;
    setProg({ done: 0, total: indexes.length, ok: 0, failed: 0 });
    for (const { it, i } of indexes) {
      setFiles(xs => xs.map((x, j) => j === i ? { ...x, status: 'uploading', error: '' } : x));
      try {
        const fd = new FormData();
        fd.append('ctype', it.ctype);
        fd.append('description', it.description || it.file.name);
        fd.append('extra_info', '');
        fd.append('file', it.file);
        await api.caAddContent(sessionId, fd);
        setFiles(xs => xs.map((x, j) => j === i ? { ...x, status: 'success', error: '' } : x));
        setProg(p => ({ ...p, done: p.done + 1, ok: p.ok + 1 }));
      } catch (e) {
        const error = errText(e);
        setFiles(xs => xs.map((x, j) => j === i ? { ...x, status: 'error', error } : x));
        setProg(p => ({ ...p, done: p.done + 1, failed: p.failed + 1 }));
      }
    }
  };

  return (
    <Modal title="⚡ آپلود سریع به جلسه (چندفایلی)" onClose={() => onClose(false)}>
      <div className="grid" style={{ gap: 10 }}>
        <div className="row">
          <select className="inp" value={scIntake} onChange={e => { setScIntake(e.target.value); setLessonId(''); setSessionId(''); }}>
            <option value="">🌐 سراسری</option>
            {intakes.map(i => <option key={i.code} value={i.code}>🏷 {i.label || i.code}</option>)}
          </select>
          <select className="inp" style={{ flex: 1 }} value={lessonId} onChange={e => { setLessonId(e.target.value); setSessionId(''); }}>
            <option value="">{tree ? 'درس…' : '…'}</option>
            {lessons.map(l => <option key={l.id} value={l.id}>{l.term} — {l.name}</option>)}
          </select>
        </div>
        <select className="inp" value={sessionId} onChange={e => setSessionId(e.target.value)} disabled={!lessonId}>
          <option value="">جلسه…</option>
          {sessions.map(s => (
            <option key={s.id} value={s.id}>
              جلسه {s.number} — {s.topic || '—'} {s.kind === 'fork' ? '⭐' : ''}
            </option>
          ))}
        </select>
        <input ref={pickerRef} type="file" multiple hidden accept=".pdf,.ppt,.pptx,.mp4,.mov,.mkv,.webm,.mp3,.ogg,.wav,.m4a"
          onChange={e => { addFiles(e.target.files); e.target.value = ''; }} />
        <div className={`upload-dropzone ${dragging ? 'on' : ''}`} role="button" tabIndex={0}
          onClick={() => pickerRef.current?.click()}
          onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pickerRef.current?.click(); } }}
          onDragEnter={e => { e.preventDefault(); setDragging(true); }} onDragOver={e => e.preventDefault()}
          onDragLeave={e => { e.preventDefault(); setDragging(false); }}
          onDrop={e => { e.preventDefault(); setDragging(false); addFiles(e.dataTransfer.files); }}>
          <b>فایل‌ها را اینجا رها کنید یا برای انتخاب کلیک کنید</b>
          <div className="muted">PDF، PowerPoint، Video و Voice · حداکثر ۳۰ فایل · سقف هر فایل ۴۵MB</div>
        </div>
        {files.map((f, i) => (
          <div key={`${f.file.name}-${f.file.size}`} className={`row file-row upload-${f.status}`}>
            <span>{f.status === 'success' ? '✅' : f.status === 'error' || f.status === 'invalid' ? '⚠️' : f.status === 'uploading' ? '⏳' : CTYPE[f.ctype] || '📎'}</span>
            <div style={{ minWidth: 120 }}><b className="text-truncate">{f.file.name}</b><div className="muted">{(f.file.size / 1024 / 1024).toFixed(2)} MB</div></div>
            <input className="inp" style={{ flex: 1 }} value={f.description} disabled={f.status === 'uploading' || f.status === 'success'}
                   onChange={e => setFiles(x => x.map((y, j) => j === i ? { ...y, description: e.target.value } : y))} />
            <select className="inp" value={f.ctype} disabled={f.status === 'uploading' || f.status === 'success' || f.status === 'invalid'}
                    onChange={e => setFiles(x => x.map((y, j) => j === i ? { ...y, ctype: e.target.value } : y))}>
              {Object.entries(CTYPE).map(([k]) => <option key={k} value={k}>{k}</option>)}
            </select>
            {f.error && <span className="field-error" title={f.error}>{f.error}</span>}
            <button className="btn sm danger" disabled={f.status === 'uploading'} onClick={() => setFiles(x => x.filter((_, j) => j !== i))} aria-label={`حذف فایل ${i + 1} از صف`}>✕</button>
          </div>
        ))}
        {prog && <div className="panel panel-pad">
          <div className="row"><span>پیشرفت {fa(prog.done)} از {fa(prog.total)}</span><span className="spacer" />
            <B kind="ok">موفق {fa(prog.ok)}</B><B kind={prog.failed ? 'bad' : ''}>ناموفق {fa(prog.failed)}</B></div>
          <div className="minibar-track" style={{ marginTop: 8 }}><div className="minibar-fill" style={{ width: `${prog.total ? Math.round(prog.done * 100 / prog.total) : 0}%` }} /></div>
        </div>}
        <div className="row">
          <button className="btn primary" disabled={!guess_ok || (prog && prog.done < prog.total)} onClick={() => run(false)}>
            ⬆️ آپلود {ready.length ? `(${fa(ready.length)} فایل آماده)` : ''}
          </button>
          {files.some(x => x.status === 'error') && <button className="btn" disabled={prog && prog.done < prog.total} onClick={() => run(true)}>↻ تلاش مجدد ناموفق‌ها</button>}
          {files.some(x => x.status === 'success') && <button className="btn ok" onClick={() => onClose(true)}>پایان و تازه‌سازی</button>}
          <button className="btn" onClick={() => onClose(false)}>بستن</button>
        </div>
      </div>
    </Modal>
  );
}
