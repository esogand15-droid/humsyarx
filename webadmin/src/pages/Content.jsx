import React, { useEffect, useMemo, useRef, useState } from 'react';
import { api, errText } from '../api.js';
import { Loading, ErrorState, B, toast, Confirm, Modal, Empty, NoPerm } from '../ui.jsx';

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

export default function Content() {
  const [tab, setTab] = useState('bs');
  return (
    <>
      <div className="tabs" style={{ marginBottom: 14 }}>
        {CCONTENT_TABS.map(([k, label]) => (
          <button key={k} className={`tab ${tab === k ? 'on' : ''}`} onClick={() => setTab(k)}>{label}</button>
        ))}
      </div>
      {tab === 'bs' && <BsTab />}
      {tab === 'refs' && <RefsTab />}
      {tab === 'schedule' && <ScheduleTab />}
      {tab === 'qbank' && <QbankTab />}
      {tab === 'faq' && <FaqTab />}
      {tab === 'reports' && <ReportsTab />}
    </>
  );
}

/* ═══ تب علوم پایه — Split View سه‌ستونه ═══ */
function BsTab() {
  const [intake, setIntake] = useState('');
  const [scopeKind, setScopeKind] = useState('global');
  const [tree, setTree] = useState(null);
  const [intakes, setIntakes] = useState([]);
  const [err, setErr] = useState('');
  const [permErr, setPermErr] = useState(false);
  const [openTerms, setOpenTerms] = useState({});
  const [q, setQ] = useState('');
  const [sel, setSel] = useState([]);            // session ids برای عملیات گروهی
  const [lesId, setLesId] = useState(null);      // درس منتخب (ستون دوم)
  const [sesId, setSesId] = useState(null);      // جلسه‌ی منتخب (بازرس)
  const [editLes, setEditLes] = useState(null);  // lesson
  const [editSes, setEditSes] = useState(null);  // {lesson_id, s}
  const [confirm, setConfirm] = useState(null);
  const [moveTo, setMoveTo] = useState(null);    // {ids:[…]}
  const [quick, setQuick] = useState(false);
  const [addLes, setAddLes] = useState(null);    // term برای درس جدید
  const [addSes, setAddSes] = useState(null);    // lesson برای جلسه جدید

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
  useEffect(() => { setTree(null); setSel([]); setLesId(null); setSesId(null); load(); }, [intake]);

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

  const delLesson = (l) => setConfirm({
    text: `حذف درس «${l.name}» با همه‌ی جلسات و فایل‌هایش؟`,
    run: () => act(() => api.caDelLesson(l.id), 'درس حذف شد'),
  });
  const delSession = (s) => setConfirm({
    text: `حذف جلسه ${s.number} «${s.topic}» و فایل‌هایش؟`,
    run: async () => { await act(() => api.caDelSession(s.id), 'جلسه حذف شد'); setSesId(null); },
  });

  if (permErr) return <NoPerm text="مدیریت محتوا فقط برای مدیران محتوا (سراسری/ورودی) است" />;
  if (err) return <ErrorState error={err} onRetry={load} />;

  const visSessions = selLesson ? selLesson.sessions.filter(sesMatch) : [];

  return (
    <>
      <div className="row">
        <div>
          <div className="h1">مرکز فرماندهی محتوا</div>
          <div className="sub">درس‌ها ← جلسات ← بازرس فایل · نمای مؤثر سراسری + Override ورودی</div>
        </div>
        <span className="spacer" />
        <B>{fa(totals.lessons)} درس</B>
        <B kind="acc">{fa(totals.sessions)} جلسه</B>
        <B kind="ok">{fa(totals.files)} فایل</B>
        <button className="btn primary" onClick={() => setQuick(true)}>⚡ آپلود سریع</button>
      </div>

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
                    <button className="btn sm" title="افزودن درس به این ترم"
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
                                  <button className="btn sm" title="بالا" disabled={idx <= 0}
                                          onClick={e => { e.stopPropagation(); reorder(() => api.waReorderLesson(l.id, 'up'), 'درس مرتب شد ↑'); }}>↑</button>
                                  <button className="btn sm" title="پایین" disabled={idx >= t.lessons.length - 1}
                                          onClick={e => { e.stopPropagation(); reorder(() => api.waReorderLesson(l.id, 'down'), 'درس مرتب شد ↓'); }}>↓</button>
                                  <button className="btn sm" title="ویرایش نام و استاد"
                                          onClick={e => { e.stopPropagation(); setEditLes(l); }}>✏️</button>
                                  <button className="btn sm" title="جلسه‌ی جدید"
                                          onClick={e => { e.stopPropagation(); setAddSes(l); }}>➕</button>
                                  <button className="btn sm danger" title="حذف درس"
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
                      <button className="btn sm warn" title="ساخت نسخه اختصاصی برای این ورودی"
                              onClick={e => { e.stopPropagation(); act(() => api.caForkSession(s.id, intake), 'نسخه‌ی اختصاصی ساخته شد ⭐'); }}>🍴</button>}
                    {!s.readonly && <>
                      <button className="btn sm" title="بالا" disabled={idx <= 0}
                              onClick={e => { e.stopPropagation(); reorder(() => api.waReorderSession(s.id, 'up'), 'مرتب شد ↑'); }}>↑</button>
                      <button className="btn sm" title="پایین" disabled={idx >= selLesson.sessions.length - 1}
                              onClick={e => { e.stopPropagation(); reorder(() => api.waReorderSession(s.id, 'down'), 'مرتب شد ↓'); }}>↓</button>
                      {s.kind === 'fork' &&
                        <button className="btn sm" title="حذف نسخه اختصاصی (بازگشت به سراسری)"
                                onClick={e => { e.stopPropagation(); act(() => api.caUnforkSession(s.id), 'به نسخه‌ی سراسری برگشت ↩️'); }}>↩️</button>}
                      <button className="btn sm" title="کلون"
                              onClick={e => { e.stopPropagation(); act(() => api.dupSession(s.id), 'کلون ساخته شد 📄'); }}>📄</button>
                      <button className="btn sm" title="ویرایش شماره/موضوع/استاد"
                              onClick={e => { e.stopPropagation(); setEditSes({ lesson_id: selLesson.id, s }); }}>✏️</button>
                      <button className="btn sm danger" title="حذف"
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
                  {selLesson.intake ? <B kind="purple">🏷 {intakeLabel(selLesson.intake)}</B> : <B kind="acc">🌐 سراسری</B>}
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
        <B kind={KIND[session.kind].kind}>
          {KIND[session.kind].icon} {session.kind === 'global' ? 'سراسری' : (session.intake_label || session.intake)}
        </B>
      </div>
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
      <SessionFiles session={session} onTreeChanged={onTreeChanged} />
    </>
  );
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
                  <button className="btn sm" title="بالا" disabled={i <= 0} onClick={() => reorderItem(c.id, 'up')}>↑</button>
                  <button className="btn sm" title="پایین" disabled={i >= items.length - 1} onClick={() => reorderItem(c.id, 'down')}>↓</button>
                  <button className="btn sm danger" title="حذف فایل" onClick={() => del(c.id)}>🗑</button>
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
  const [files, setFiles] = useState([]);       // {file, ctype, description}
  const [prog, setProg] = useState(null);       // {done,total}

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
    for (const f of fl) {
      const ext = (f.name.split('.').pop() || '').toLowerCase();
      next.push({ file: f, ctype: EXT_MAP[ext] || 'pdf', description: f.name.replace(/\.[^.]+$/, '') });
    }
    setFiles(next.slice(0, 30));
  };
  const guess_ok = files.length > 0 && lessonId && sessionId;

  const run = async () => {
    setProg({ done: 0, total: files.length });
    let ok = 0;
    for (const it of files) {
      try {
        const fd = new FormData();
        fd.append('ctype', it.ctype);
        fd.append('description', it.description || it.file.name);
        fd.append('extra_info', '');
        fd.append('file', it.file);
        await api.caAddContent(sessionId, fd);
        ok++;
      } catch (e) { toast(`خطا در ${it.file.name}: ${errText(e)}`, 'err'); }
      setProg(p => ({ ...p, done: (p.done || 0) + 1 }));
    }
    toast(`${fa(ok)} از ${fa(files.length)} فایل آپلود شد ✅`);
    setProg(null); onClose(ok > 0);
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
        <input type="file" multiple className="inp" onChange={e => addFiles(e.target.files)} />
        {files.map((f, i) => (
          <div key={i} className="row file-row">
            <span>{CTYPE[f.ctype] || '📎'}</span>
            <input className="inp" style={{ flex: 1 }} value={f.description}
                   onChange={e => setFiles(x => x.map((y, j) => j === i ? { ...y, description: e.target.value } : y))} />
            <select className="inp" value={f.ctype}
                    onChange={e => setFiles(x => x.map((y, j) => j === i ? { ...y, ctype: e.target.value } : y))}>
              {Object.entries(CTYPE).map(([k, v]) => <option key={k} value={k}>{k}</option>)}
            </select>
            <button className="btn sm danger" onClick={() => setFiles(x => x.filter((_, j) => j !== i))}>✕</button>
          </div>
        ))}
        {prog && <div className="muted">⏳ {fa(prog.done)}/{fa(prog.total)}</div>}
        <div className="row">
          <button className="btn primary" disabled={!guess_ok || !!prog} onClick={run}>
            ⬆️ آپلود {files.length ? `(${fa(files.length)} فایل)` : ''}
          </button>
          <button className="btn" onClick={() => onClose(false)}>انصراف</button>
        </div>
      </div>
    </Modal>
  );
}
