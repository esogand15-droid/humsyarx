import React, { useEffect, useMemo, useRef, useState } from 'react';
import { api, errText } from '../api.js';
import { Loading, ErrorState, B, toast, Confirm, Modal, Drawer, Empty, NoPerm } from '../ui.jsx';

const TERM_ICON = '📚';
const KIND = {
  global:    { icon: '🌐', label: 'سراسری', kind: 'acc' },
  fork:      { icon: '⭐', label: 'Override', kind: 'warn' },
  exclusive: { icon: '🏷', label: 'اختصاصی', kind: 'purple' },
};
const CTYPE = { video: '🎬', ppt: '📽', pdf: '📕', note: '📝', test: '🧪', voice: '🎙' };
const EXT_MAP = { pdf: 'pdf', ppt: 'ppt', pptx: 'ppt', mp4: 'video', mov: 'video', mkv: 'video', webm: 'video', mp3: 'voice', ogg: 'voice', wav: 'voice', m4a: 'voice' };

// 📚🌊 WA2.1 — مرکز فرماندهی محتوا: درخت ترم→درس→جلسه، fork-aware،
// آپلود چندفایلی با پیشنهاد نوع، کلون/انتقال/حذف گروهی — بدون ترک صفحه.
export default function Content() {
  const [intake, setIntake] = useState('');
  const [tree, setTree] = useState(null);
  const [intakes, setIntakes] = useState([]);
  const [err, setErr] = useState('');
  const [permErr, setPermErr] = useState(false);
  const [openTerms, setOpenTerms] = useState({});
  const [openLes, setOpenLes] = useState({});
  const [q, setQ] = useState('');
  const [sel, setSel] = useState([]);                 // session ids انتخاب‌شده
  const [filesOf, setFilesOf] = useState(null);       // session برای drawer فایل‌ها
  const [editSes, setEditSes] = useState(null);       // {lesson_id, session}
  const [confirm, setConfirm] = useState(null);
  const [moveTo, setMoveTo] = useState(null);
  const [quick, setQuick] = useState(false);          // مودال آپلود سریع
  const [addLes, setAddLes] = useState(null);         // term برای درس جدید
  const [addSes, setAddSes] = useState(null);         // lesson برای جلسه جدید
  const [reports, setReports] = useState(null);

  const load = async () => {
    setErr('');
    try {
      const r = await api.contentTree(intake || undefined);
      setTree(r.tree || []);
      setIntakes(r.intakes || []);
    } catch (e) {
      if (e.status === 403) setPermErr(true);
      else setErr(errText(e));
    }
  };
  useEffect(() => { setTree(null); setSel([]); load(); }, [intake]);
  useEffect(() => {
    api.caReports('new').then(r => setReports(r.reports || [])).catch(() => setReports([]));
  }, []);

  const flatLessons = useMemo(() => {
    const out = [];
    (tree || []).forEach(t => t.lessons.forEach(l => out.push({ ...l, term: t.term })));
    return out;
  }, [tree]);

  const sessMatch = (s) => !q.trim() || (s.topic || '').includes(q.trim()) || String(s.number) === q.trim();

  const act = async (fn, okMsg = 'انجام شد') => {
    try { await fn(); toast(okMsg); load(); }
    catch (e) { toast(errText(e), 'err'); }
  };
  const bulk = async (body) => act(() => api.sessionsBulk(body).then(r => toast(`${r.done} مورد انجام شد`)));

  if (permErr) return <NoPerm text="مدیریت محتوا فقط برای مدیران محتوا (سراسری/ورودی) است" />;
  if (err) return <ErrorState error={err} onRetry={load} />;

  return (
    <>
      <div className="row">
        <div>
          <div className="h1">مرکز فرماندهی محتوا</div>
          <div className="sub">ترم → درس → جلسه → فایل · نمای مؤثر سراسری + Override ورودی</div>
        </div>
        <span className="spacer" />
        <button className="btn primary" onClick={() => setQuick(true)}>⚡ آپلود سریع</button>
      </div>

      <div className="panel panel-pad row" style={{ marginBottom: 12 }}>
        <select className="inp" value={intake} onChange={e => setIntake(e.target.value)}>
          <option value="">🌐 سراسری (پایه)</option>
          {intakes.map(i => <option key={i.code} value={i.code}>🏷 {i.label || i.code}</option>)}
        </select>
        <input className="inp" style={{ flex: 1, minWidth: 180 }} placeholder="🔎 فیلتر موضوع/شماره جلسه…"
               value={q} onChange={e => setQ(e.target.value)} />
        {sel.length > 0 && <>
          <span className="badge acc">{sel.length} جلسه انتخاب شد</span>
          <button className="btn sm" onClick={() => bulk({ action: 'duplicate', ids: sel }).then(() => setSel([]))}>📄 کلون</button>
          <button className="btn sm" onClick={() => setMoveTo({ ids: sel })}>📦 انتقال</button>
          <button className="btn sm danger" onClick={() => setConfirm({
            text: `حذف ${sel.length} جلسه (به‌همراه فایل‌ها و نسخه‌های اختصاصی وابسته)؟`,
            run: () => bulk({ action: 'delete', ids: sel }).then(() => setSel([])),
          })}>🗑 حذف</button>
        </>}
      </div>

      {!tree ? <Loading rows={5} /> : tree.map(t => (
        <div key={t.term} className="panel" style={{ marginBottom: 10 }}>
          <div className="tree-term" onClick={() => setOpenTerms(s => ({ ...s, [t.term]: !s[t.term] }))}>
            <span>{TERM_ICON}</span><b>{t.term}</b>
            <B>{t.lessons.length} درس</B>
            <B kind="acc">{t.lessons.reduce((a, l) => a + l.content_count, 0)} فایل</B>
            <span className="spacer" />
            <button className="btn sm" onClick={e => { e.stopPropagation(); setAddLes(t.term); }}>➕ درس</button>
            <span className="muted">{openTerms[t.term] ? '▾' : '◂'}</span>
          </div>
          {openTerms[t.term] && (
            <div style={{ borderTop: '1px solid var(--line)' }}>
              {t.lessons.length === 0 && <Empty icon="📭" text="درسی در این ترم نیست" />}
              {t.lessons.map(l => (
                <div key={l.id} className="lesson">
                  <div className="tree-row les-row" onClick={() => setOpenLes(s => ({ ...s, [l.id]: !s[l.id] }))}>
                    <span>{openLes[l.id] ? '📖' : '📘'}</span>
                    <b style={{ color: 'var(--txt)' }}>{l.name}</b>
                    {l.intake && <B kind="purple">🏷 {intakes.find(i => i.code === l.intake)?.label || l.intake}</B>}
                    <span className="muted">{l.teacher || ''}</span>
                    <B>{l.session_count} جلسه</B>
                    <B kind="acc">{l.content_count} فایل</B>
                    <span className="spacer" />
                    <button className="btn sm" onClick={e => { e.stopPropagation(); setAddSes(l); }}>➕ جلسه</button>
                    <button className="btn sm danger" onClick={e => { e.stopPropagation(); setConfirm({
                      text: `حذف درس «${l.name}» با همه‌ی جلسات و فایل‌هایش؟`,
                      run: () => act(() => api.caDelLesson(l.id), 'درس حذف شد'),
                    }); }}>🗑</button>
                  </div>
                  {openLes[l.id] && (
                    <div className="sess-box">
                      {l.sessions.filter(sessMatch).map(s => (
                        <div key={s.id} className={`sess-row ${sel.includes(s.id) ? 'sel' : ''}`}>
                          <input type="checkbox" checked={sel.includes(s.id)}
                                 onChange={() => setSel(x => x.includes(s.id) ? x.filter(i => i !== s.id) : [...x, s.id])} />
                          <span className="code">جلسه {s.number}</span>
                          <div style={{ flex: 1, minWidth: 0, cursor: 'pointer' }} onClick={() => setFilesOf(s)}>
                            <div style={{ color: 'var(--txt)', fontSize: 12.5 }}>{s.topic || '—'}</div>
                            <div className="muted">{s.teacher || ''}</div>
                          </div>
                          <B kind={KIND[s.kind].kind}>
                            {KIND[s.kind].icon} {s.kind === 'global' ? 'سراسری' : (s.intake_label || s.intake)}
                          </B>
                          <span className="muted" style={{ minWidth: 76, textAlign: 'center' }}>
                            {Object.entries(s.types || {}).map(([k, v]) => `${CTYPE[k] || '📎'}${v}`).join(' ') || '—'}
                          </span>
                          <div className="row" style={{ gap: 3 }}>
                            <button className="btn sm" title="فایل‌ها" onClick={() => setFilesOf(s)}>📁 {s.content_count || ''}</button>
                            {s.kind === 'global' && intake &&
                              <button className="btn sm warn" title="ساخت نسخه اختصاصی برای این ورودی"
                                      onClick={() => act(() => api.caForkSession(s.id, intake), 'نسخه‌ی اختصاصی ساخته شد ⭐')}>🍴</button>}
                            {s.kind === 'fork' &&
                              <button className="btn sm" title="حذف نسخه اختصاصی (بازگشت به سراسری)"
                                      onClick={() => act(() => api.caUnforkSession(s.id), 'به نسخه‌ی سراسری برگشت ↩️')}>↩️</button>}
                            <button className="btn sm" title="کلون"
                                    onClick={() => act(() => api.dupSession(s.id), 'کلون ساخته شد 📄')}>📄</button>
                            <button className="btn sm" title="ویرایش موضوع/استاد"
                                    onClick={() => setEditSes({ lesson_id: l.id, s })}>✏️</button>
                            <button className="btn sm danger" title="حذف"
                                    onClick={() => setConfirm({
                                      text: `حذف جلسه ${s.number} «${s.topic}» و فایل‌هایش؟`,
                                      run: () => act(() => api.caDelSession(s.id), 'جلسه حذف شد'),
                                    })}>🗑</button>
                          </div>
                        </div>
                      ))}
                      {l.sessions.filter(sessMatch).length === 0 &&
                        <div className="muted" style={{ padding: '8px 14px' }}>جلسه‌ای نیست</div>}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      ))}

      {/* 🚩 صف گزارش محتوا (WA2.7 needs-attention) */}
      {reports !== null && (
        <div className="panel panel-pad" style={{ marginTop: 14 }}>
          <div className="row"><b>🚩 گزارش‌های در انتظار محتوا/سؤال</b>
            <span className="spacer" /><B kind={reports.length ? 'warn' : 'ok'}>{reports.length}</B></div>
          {reports.length === 0 && <p className="muted" style={{ marginTop: 8 }}>موردی نیست 🎉</p>}
          {reports.slice(0, 8).map(r => (
            <div key={r.id} className="row" style={{ padding: '7px 0', borderBottom: '1px solid var(--line)' }}>
              <B kind="warn">{r.reason}</B>
              <span style={{ fontSize: 12.5 }}>{r.target_type === 'question' ? 'سؤال' : 'فایل'} <span className="code">{r.target_id?.slice?.(-6)}</span></span>
              <span className="muted">{r.reporter_name} · {r.created_at}</span>
              <span className="spacer" />
              <button className="btn sm ok" onClick={() => act(() => api.caReportStatus(r.id, 'resolved').then(() =>
                api.caReports('new').then(x => setReports(x.reports || [])), ''), 'حل‌شده ✅')}>✅</button>
              <button className="btn sm danger" onClick={() => act(() => api.caReportStatus(r.id, 'rejected').then(() =>
                api.caReports('new').then(x => setReports(x.reports || [])), ''), 'رد شد')}>✖</button>
            </div>
          ))}
        </div>
      )}

      {filesOf && <FilesDrawer session={filesOf} onClose={(ch) => { setFilesOf(null); if (ch) load(); }} />}
      {editSes && <EditSession {...editSes} onClose={(ch) => { setEditSes(null); if (ch) load(); }} />}
      {quick && <QuickUpload intakes={intakes} intake={intake} onClose={(ch) => { setQuick(false); if (ch) load(); }} />}
      {addLes && <AddLesson term={addLes} intake={intake} onClose={(ch) => { setAddLes(null); if (ch) load(); }} />}
      {addSes && <AddSession lesson={addSes} onClose={(ch) => { setAddSes(null); if (ch) load(); }} />}
      {moveTo && <MoveSessions lessons={flatLessons} sel={moveTo.ids}
                               onClose={(ch) => { setMoveTo(null); if (ch) { setSel([]); load(); } }} />}
      {confirm && <Confirm text={confirm.text} danger
                           onYes={async () => { await confirm.run(); setConfirm(null); }}
                           onNo={() => setConfirm(null)} />}
    </>
  );
}

/* ── 📁 کشوی فایل‌های جلسه (آپلود/حذف/انتقال گروهی) ─────────── */
function FilesDrawer({ session, onClose }) {
  const [items, setItems] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [form, setForm] = useState({ ctype: 'pdf', description: '', extra_info: '' });
  const [file, setFile] = useState(null);
  const [sel, setSel] = useState([]);
  const [changed, setChanged] = useState(false);
  const fileRef = useRef(null);

  const load = async () => {
    try { setItems((await api.caSessionContent(session.id)).content || []); }
    catch (e) { setErr(errText(e)); }
  };
  useEffect(() => { load(); }, [session.id]);

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
      setChanged(true); load();
    } catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };
  const del = async (cid) => {
    try { await api.caDelContent(cid); toast('حذف شد'); setChanged(true); load(); }
    catch (e) { toast(errText(e), 'err'); }
  };
  const guess = (name) => {
    const ext = (name.split('.').pop() || '').toLowerCase();
    return EXT_MAP[ext] || 'pdf';
  };

  return (
    <Drawer wide title={`📁 فایل‌های جلسه ${session.number} — ${session.topic || ''}`}
            onClose={() => onClose(changed)}>
      {err ? <ErrorState error={err} onRetry={load} /> : !items ? <Loading /> : (
        <>
          <div className="grid" style={{ gap: 6 }}>
            {items.length === 0 && <Empty icon="📭" text="فایلی نیست" />}
            {items.map(c => (
              <div key={c.id} className={`row file-row ${sel.includes(c.id) ? 'sel-row' : ''}`}>
                <input type="checkbox" checked={sel.includes(c.id)}
                       onChange={() => setSel(x => x.includes(c.id) ? x.filter(i => i !== c.id) : [...x, c.id])} />
                <span style={{ fontSize: 17 }}>{CTYPE[c.type] || '📎'}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ color: 'var(--txt)', fontSize: 12.5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {c.description || '(بدون توضیح)'}</div>
                  <div className="muted">{c.extra_info || ''}</div>
                </div>
                <B>{Number(c.downloads || 0).toLocaleString('fa')} DL</B>
                <button className="btn sm danger" onClick={() => del(c.id)}>🗑</button>
              </div>
            ))}
          </div>
          {sel.length > 0 && (
            <div className="panel panel-pad row" style={{ marginTop: 10, background: 'var(--bg)' }}>
              <span className="badge acc">{sel.length} فایل انتخاب شد</span>
              <button className="btn sm danger" onClick={async () => {
                try {
                  const r = await api.itemsBulk({ action: 'delete', ids: sel });
                  toast(`${r.done} فایل حذف شد`); setSel([]); setChanged(true); load();
                } catch (e) { toast(errText(e), 'err'); }
              }}>🗑 حذف گروهی</button>
              <MoveItemsButton sel={sel} sessionId={session.id}
                               onDone={() => { setSel([]); setChanged(true); load(); }} />
            </div>
          )}
          <div className="panel panel-pad" style={{ marginTop: 12, background: 'var(--bg)' }}>
            <b>➕ آپلود فایل جدید</b>
            <div className="grid" style={{ gap: 8, marginTop: 10 }}>
              <div className="row">
                <input ref={fileRef} type="file" className="inp" style={{ flex: 1 }}
                       onChange={e => {
                         const f = e.target.files[0] || null;
                         setFile(f);
                         if (f) setForm(x => ({ ...x, ctype: guess(f.name), description: x.description || f.name }));
                       }} />
                <select className="inp" value={form.ctype} onChange={e => setForm({ ...form, ctype: e.target.value })}>
                  {Object.entries(CTYPE).map(([k, v]) => <option key={k} value={k}>{v} {k}</option>)}
                </select>
              </div>
              <input className="inp" placeholder="توضیح (عنوان نمایشی)…"
                     value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} />
              <input className="inp" placeholder="اطلاعات تکمیلی (اختیاری)…"
                     value={form.extra_info} onChange={e => setForm({ ...form, extra_info: e.target.value })} />
              <button className="btn primary" disabled={busy || !file} onClick={upload}>
                {busy ? '⏳ در حال آپلود…' : '⬆️ آپلود (از مسیر تلگرام)'}</button>
            </div>
          </div>
        </>
      )}
    </Drawer>
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
          <p className="muted" style={{ marginBottom: 10 }}>شناسه‌ی جلسه‌ی مقصد را وارد کنید (از کشوی فایل‌ها/نشانی جلسه کپی کنید):</p>
          <input className="inp" style={{ width: '100%', direction: 'ltr' }} placeholder="session id مقصد…"
                 value={target} onChange={e => setTarget(e.target.value)} />
          <div className="row" style={{ marginTop: 12 }}>
            <button className="btn primary" disabled={!target.trim()} onClick={async () => {
              try {
                const r = await api.itemsBulk({ action: 'move', ids: sel, target_session: target.trim() });
                toast(`${r.done} فایل منتقل شد`); setOpen(false); onDone();
              } catch (e) { toast(errText(e), 'err'); }
            }}>انتقال</button>
            <button className="btn" onClick={() => setOpen(false)}>انصراف</button>
          </div>
        </Modal>
      )}
    </>
  );
}

/* ── ✏️ ویرایش/➕ جلسه ─────────────────────────────────── */
function EditSession({ lesson_id, s, onClose }) {
  const [topic, setTopic] = useState(s.topic || '');
  const [teacher, setTeacher] = useState(s.teacher || '');
  const [busy, setBusy] = useState(false);
  return (
    <Modal title={`✏️ ویرایش جلسه ${s.number}`} onClose={() => onClose(false)}>
      <div className="grid" style={{ gap: 10 }}>
        <input className="inp" placeholder="موضوع جلسه…" value={topic} onChange={e => setTopic(e.target.value)} />
        <input className="inp" placeholder="استاد…" value={teacher} onChange={e => setTeacher(e.target.value)} />
        <div className="row">
          <button className="btn primary" disabled={busy || !topic.trim()} onClick={async () => {
            setBusy(true);
            try {
              // مسیر upsert موجود (همان number ⇒ به‌روزرسانی بدون رکورد جدید)
              await api.caAddSession(lesson_id, { number: s.number, topic: topic.trim(), teacher: teacher.trim() });
              toast('ذخیره شد'); onClose(true);
            } catch (e) { toast(errText(e), 'err'); }
            setBusy(false);
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

/* ── 📦 انتقال گروهی جلسات ───────────────────────────── */
function MoveSessions({ lessons, sel, onClose }) {
  const [target, setTarget] = useState('');
  const [busy, setBusy] = useState(false);
  return (
    <Modal title={`📦 انتقال ${sel.length} جلسه به درس دیگر`} onClose={() => onClose(false)}>
      <select className="inp" style={{ width: '100%' }} value={target} onChange={e => setTarget(e.target.value)}>
        <option value="">انتخاب درس مقصد…</option>
        {lessons.map(l => <option key={l.id} value={l.id}>{l.term} — {l.name}</option>)}
      </select>
      <div className="row" style={{ marginTop: 12 }}>
        <button className="btn primary" disabled={busy || !target} onClick={async () => {
          setBusy(true);
          try {
            const r = await api.sessionsBulk({ action: 'move', ids: sel, target_lesson: target });
            toast(`${r.done} جلسه منتقل شد`); onClose(true);
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
    toast(`${ok} از ${files.length} فایل آپلود شد ✅`);
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
        {prog && <div className="muted">⏳ {prog.done}/{prog.total}</div>}
        <div className="row">
          <button className="btn primary" disabled={!guess_ok || !!prog} onClick={run}>
            ⬆️ آپلود {files.length ? `(${files.length} فایل)` : ''}
          </button>
          <button className="btn" onClick={() => onClose(false)}>انصراف</button>
        </div>
      </div>
    </Modal>
  );
}
