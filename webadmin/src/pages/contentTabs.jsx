import React, { useEffect, useRef, useState } from 'react';
import { api, errText } from '../api.js';
import { Loading, ErrorState, Empty, B, toast, Confirm, Modal, NoPerm } from '../ui.jsx';

// ════════════════════════════════════════════════════════════════════
// 🌊 WA3 — تب‌های پریتی «مرکز فرماندهی محتوا» (همه روی API موجود، scope-aware)
// ════════════════════════════════════════════════════════════════════

export function useIntakes() {
  const [intakes, setIntakes] = useState([]);
  useEffect(() => { api.caIntakes().then(r => setIntakes(r.intakes || [])).catch(() => {}); }, []);
  return intakes;
}

function IntakeSelect({ intakes, value, onChange }) {
  return (
    <select className="inp" value={value} onChange={e => onChange(e.target.value)}>
      <option value="">🌐 سراسری (پایه)</option>
      {intakes.map(i => <option key={i.code || i} value={i.code || i}>🏷 {i.label || i.code || i}</option>)}
    </select>
  );
}

// ── 📖 رفرنس‌ها: موضوع → کتاب → فایل (سه‌ستونه‌ی فرماندهی) ──────────
export function RefsTab() {
  const intakes = useIntakes();
  const [intake, setIntake] = useState('');
  const [subjects, setSubjects] = useState(null);
  const [err, setErr] = useState('');
  const [permErr, setPermErr] = useState(false);
  const [sub, setSub] = useState(null);
  const [books, setBooks] = useState(null);
  const [book, setBook] = useState(null);
  const [files, setFiles] = useState(null);
  const [addModal, setAddModal] = useState(null);   // {kind:'subject'|'book'|'file'}
  const [confirm, setConfirm] = useState(null);     // {text, run}

  const loadSubjects = async () => {
    setErr('');
    try { setSubjects((await api.refSubjects(intake || undefined)).subjects || []); }
    catch (e) { if (e.status === 403) setPermErr(true); else setErr(errText(e)); }
  };
  useEffect(() => { setSub(null); setBook(null); loadSubjects(); }, [intake]);
  const loadBooks = async (s) => {
    setSub(s); setBook(null); setBooks(null);
    try { setBooks((await api.refBooks(s.id)).books || []); } catch (e) { toast(errText(e), 'err'); }
  };
  const loadFiles = async (b) => {
    setBook(b); setFiles(null);
    try { setFiles((await api.refFiles(b.id)).files || []); } catch (e) { toast(errText(e), 'err'); }
  };
  const after = (fn, okMsg) => async () => {
    try { await fn(); toast(okMsg || 'انجام شد'); }
    catch (e) { toast(errText(e), 'err'); }
  };

  if (permErr) return <NoPerm text="مدیریت رفرنس‌ها فقط برای مدیر محتواست" />;
  if (err) return <ErrorState error={err} onRetry={loadSubjects} />;

  return (
    <>
      <div className="row" style={{ marginBottom: 12 }}>
        <IntakeSelect intakes={intakes} value={intake} onChange={setIntake} />
        <span className="spacer" />
        <button className="btn sm primary" onClick={() => setAddModal({ kind: 'subject' })}>➕ موضوع</button>
      </div>
      <div className="grid" style={{ gridTemplateColumns: '240px 260px 1fr', alignItems: 'start' }}>
        {/* موضوع‌ها */}
        <div className="panel" style={{ maxHeight: '72vh', overflowY: 'auto' }}>
          {!subjects ? <div className="panel-pad"><Loading /></div> :
           subjects.length === 0 ? <Empty icon="📖" text="موضوعی نیست" /> :
           subjects.map(s => (
            <div key={s.id} className={`tree-row ${sub?.id === s.id ? 'on' : ''}`} style={{ cursor: 'pointer' }}
                 onClick={() => loadBooks(s)}>
              <span>📖</span>
              <span style={{ flex: 1, color: 'var(--txt)' }}>{s.name}</span>
              {s.readonly && <B>🔒</B>}
              {!s.readonly && (
                <button className="btn sm danger" onClick={e => { e.stopPropagation(); setConfirm({
                  text: `حذف موضوع «${s.name}» با همه‌ی کتاب‌ها و فایل‌هایش؟`,
                  run: async () => { await api.refSubjectDel(s.id); toast('حذف شد'); setSub(null); loadSubjects(); },
                }); }}>🗑</button>)}
            </div>
          ))}
        </div>
        {/* کتاب‌ها */}
        <div className="panel" style={{ maxHeight: '72vh', overflowY: 'auto' }}>
          {!sub && <Empty icon="📚" text="یک موضوع را انتخاب کنید" />}
          {sub && !books && <div className="panel-pad"><Loading /></div>}
          {sub && books && (
            <>
              <div className="panel-pad row" style={{ borderBottom: '1px solid var(--line)', padding: '10px 12px' }}>
                <b style={{ fontSize: 12.5 }}>{sub.name}</b><span className="spacer" />
                {!sub.readonly && <button className="btn sm primary" onClick={() => setAddModal({ kind: 'book' })}>➕</button>}
              </div>
              {books.length === 0 && <Empty icon="📕" text="کتابی نیست" />}
              {books.map(b => (
                <div key={b.id} className={`tree-row ${book?.id === b.id ? 'on' : ''}`} style={{ cursor: 'pointer' }}
                     onClick={() => loadFiles(b)}>
                  <span>{b.is_fork ? '⭐' : b.intake ? '🏷' : '📕'}</span>
                  <span style={{ flex: 1, color: 'var(--txt)' }}>{b.name}</span>
                  {!b.is_fork && !b.intake && intake &&
                    <button className="btn sm warn" title="نسخه‌ی اختصاصی برای این ورودی"
                            onClick={(e) => { e.stopPropagation(); (async () => {
                              try { await api.refBookFork(b.id, intake); toast('Fork ساخته شد ⭐'); loadBooks(sub); }
                              catch (err) { toast(errText(err), 'err'); }
                            })(); }}>🍴</button>}
                  {b.is_fork &&
                    <button className="btn sm" title="بازگشت به نسخه‌ی سراسری"
                            onClick={(e) => { e.stopPropagation(); (async () => {
                              try { await api.refBookUnfork(b.id); toast('↩️ بازگشت به نسخه‌ی سراسری'); loadBooks(sub); }
                              catch (err) { toast(errText(err), 'err'); }
                            })(); }}>↩️</button>}
                  <button className="btn sm danger" onClick={e => { e.stopPropagation(); setConfirm({
                    text: `حذف کتاب «${b.name}» و فایل‌هایش؟`,
                    run: async () => { await api.refBookDel(b.id); toast('حذف شد'); setBook(null); loadBooks(sub); },
                  }); }}>🗑</button>
                </div>
              ))}
            </>
          )}
        </div>
        {/* فایل‌ها */}
        <div className="panel" style={{ maxHeight: '72vh', overflowY: 'auto' }}>
          {!book && <Empty icon="📁" text="یک کتاب را انتخاب کنید" />}
          {book && !files && <div className="panel-pad"><Loading /></div>}
          {book && files && (
            <>
              <div className="panel-pad row" style={{ borderBottom: '1px solid var(--line)', padding: '10px 12px' }}>
                <b style={{ fontSize: 12.5 }}>📁 {book.name}</b><span className="spacer" />
                <button className="btn sm primary" onClick={() => setAddModal({ kind: 'file' })}>⬆️ آپلود فایل</button>
              </div>
              {files.length === 0 && <Empty icon="📭" text="فایلی نیست" />}
              {files.map(f => (
                <div key={f.id} className="file-row" style={{ margin: '6px 10px' }}>
                  <span>{f.lang === 'fa' ? '🇮🇷' : '🇬🇧'}</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ color: 'var(--txt)', fontSize: 12.5 }}>{f.description || '(بدون توضیح)'}</div>
                    <div className="muted">جلد {f.volume}</div>
                  </div>
                  <B>{Number(f.downloads || 0).toLocaleString('fa')} DL</B>
                  <button className="btn sm danger" onClick={() => setConfirm({
                    text: 'حذف این فایل؟',
                    run: async () => { await api.refFileDel(f.id); toast('حذف شد'); loadFiles(book); },
                  })}>🗑</button>
                </div>
              ))}
            </>
          )}
        </div>
      </div>

      {addModal && (
        <RefAddModal kind={addModal.kind} sub={sub} book={book} intake={intake}
                     onClose={(ok) => {
                       setAddModal(null);
                       if (ok) { if (addModal.kind === 'subject') loadSubjects(); else if (addModal.kind === 'book') loadBooks(sub); else loadFiles(book); }
                     }} />
      )}
      {confirm && <Confirm text={confirm.text} danger
                           onYes={async () => { await confirm.run(); setConfirm(null); }}
                           onNo={() => setConfirm(null)} />}
    </>
  );
}

function RefAddModal({ kind, sub, book, intake, onClose }) {
  const [name, setName] = useState('');
  const [lang, setLang] = useState('fa');
  const [volume, setVolume] = useState(1);
  const [desc, setDesc] = useState('');
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const titles = { subject: '➕ موضوع جدید', book: `➕ کتاب جدید — ${sub?.name}`, file: `⬆️ فایل — ${book?.name}` };
  return (
    <Modal title={titles[kind]} onClose={() => onClose(false)}>
      <div className="grid" style={{ gap: 10 }}>
        {kind !== 'file' && (
          <input className="inp" placeholder={kind === 'subject' ? 'نام موضوع (مثلاً آناتومی)…' : 'نام کتاب…'}
                 value={name} onChange={e => setName(e.target.value)} />
        )}
        {kind === 'file' && (
          <>
            <div className="row">
              <select className="inp" value={lang} onChange={e => setLang(e.target.value)}>
                <option value="fa">🇮🇷 فارسی</option>
                <option value="en">🇬🇧 انگلیسی</option>
              </select>
              <input className="inp" type="number" min="1" style={{ width: 90 }} value={volume}
                     onChange={e => setVolume(+e.target.value)} title="جلد" />
            </div>
            <input className="inp" placeholder="توضیح فایل…" value={desc} onChange={e => setDesc(e.target.value)} />
            <input type="file" className="inp" onChange={e => setFile(e.target.files[0] || null)} />
          </>
        )}
        <div className="row">
          <button className="btn primary" disabled={busy || (kind === 'file' ? !file : !name.trim())} onClick={async () => {
            setBusy(true);
            try {
              if (kind === 'subject') await api.refSubjectAdd({ name: name.trim(), intake: intake || '' });
              else if (kind === 'book') await api.refBookAdd(sub.id, name.trim());
              else {
                const fd = new FormData();
                fd.append('lang', lang); fd.append('volume', volume);
                fd.append('description', desc || (file && file.name) || '');
                fd.append('file', file);
                await api.refFileAdd(book.id, fd);
              }
              toast('ثبت شد ✅'); onClose(true);
            } catch (e) { toast(errText(e), 'err'); }
            setBusy(false);
          }}>{busy ? '⏳…' : 'ثبت'}</button>
          <button className="btn" onClick={() => onClose(false)}>انصراف</button>
        </div>
      </div>
    </Modal>
  );
}

// ── 📅 کلاس‌ها و برنامه (schedule با flex) ──────────────────────────
const SCHED_TYPES = [['', 'همه'], ['class', '🏫 کلاس'], ['exam', '📝 امتحان'], ['makeup', '🔄 جبرانی']];

export function ScheduleTab() {
  const [stype, setStype] = useState('');
  const [items, setItems] = useState(null);
  const [err, setErr] = useState('');
  const [permErr, setPermErr] = useState(false);
  const [edit, setEdit] = useState(null);
  const [flex, setFlex] = useState(null);
  const [confirm, setConfirm] = useState(null);

  const load = async () => {
    setErr('');
    try { setItems((await api.caSchedule(stype || undefined)).schedule || []); }
    catch (e) { if (e.status === 403) setPermErr(true); else setErr(errText(e)); }
  };
  useEffect(() => { setItems(null); load(); }, [stype]);

  if (permErr) return <NoPerm text="مدیریت برنامه فقط برای ادمین ارشد محتواست" />;
  if (err) return <ErrorState error={err} onRetry={load} />;

  const TYPE_FA = { class: 'کلاس', exam: 'امتحان', makeup: 'جبرانی' };
  return (
    <>
      <div className="row" style={{ marginBottom: 12 }}>
        <div className="tabs" style={{ marginBottom: 0, borderBottom: 'none' }}>
          {SCHED_TYPES.map(([k, v]) => (
            <button key={k} className={`tab ${stype === k ? 'on' : ''}`} onClick={() => setStype(k)}>{v}</button>
          ))}
        </div>
        <span className="spacer" />
        <button className="btn primary" onClick={() => setEdit({ type: 'class', group: 'هر دو', flex_type: 'fixed' })}>➕ مورد جدید</button>
      </div>
      {!items ? <Loading /> : items.length === 0 ? <Empty icon="📅" text="موردی نیست" /> : (
        <div className="grid" style={{ gap: 8 }}>
          {items.map(s => (
            <div key={s.id} className="panel panel-pad row" style={{ padding: '10px 14px' }}>
              <span style={{ fontSize: 17 }}>{s.type === 'class' ? '🏫' : s.type === 'exam' ? '📝' : '🔄'}</span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <b style={{ color: 'var(--txt)' }}>{s.lesson}</b>
                <span className="muted"> {s.teacher || ''}</span>
                <div className="muted" style={{ marginTop: 2 }}>
                  📅 <span className="code">{s.date}</span> {s.time || ''} · {s.group} {s.location ? `· 📍 ${s.location}` : ''}
                </div>
                {s.flex_note && <div className="muted" style={{ marginTop: 2 }}>🔄 آخرین اعلان: {s.flex_note}</div>}
              </div>
              {s.flex_type === 'flexible' && <B kind="warn">منعطف</B>}
              <B>{TYPE_FA[s.type] || s.type}</B>
              {s.flex_type === 'flexible' &&
                <button className="btn sm" title="اعلام زمان جدید کلاس منعطف" onClick={() => setFlex(s)}>🔄 زمان جدید</button>}
              <button className="btn sm" onClick={() => setEdit({ ...s, note: s.note || '' })}>✏️</button>
              <button className="btn sm danger" onClick={() => setConfirm({
                text: `حذف «${s.lesson}» (${s.date})؟`,
                run: async () => { await api.caScheduleDel(s.id); toast('حذف شد'); load(); },
              })}>🗑</button>
            </div>
          ))}
        </div>
      )}
      {edit && <ScheduleModal row={edit.id ? edit : null} preset={edit}
                              onClose={(ok) => { setEdit(null); if (ok) load(); }} />}
      {flex && <FlexModal row={flex} onClose={(ok) => { setFlex(null); if (ok) load(); }} />}
      {confirm && <Confirm text={confirm.text} danger
                           onYes={async () => { await confirm.run(); setConfirm(null); }}
                           onNo={() => setConfirm(null)} />}
    </>
  );
}

function ScheduleModal({ row, preset, onClose }) {
  const [f, setF] = useState({
    type: preset.type || 'class', lesson: preset.lesson || '', teacher: preset.teacher || '',
    date: preset.date || '', time: preset.time || '', group: preset.group || 'هر دو',
    location: preset.location || '', note: preset.note || '', flex_type: preset.flex_type || 'fixed',
  });
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF(x => ({ ...x, [k]: v }));
  return (
    <Modal title={row ? '✏️ ویرایش مورد برنامه' : '➕ مورد جدید برنامه'} onClose={() => onClose(false)}>
      <div className="grid" style={{ gap: 10 }}>
        <div className="row">
          <select className="inp" value={f.type} onChange={e => set('type', e.target.value)}>
            {[['class', '🏫 کلاس'], ['exam', '📝 امتحان'], ['makeup', '🔄 جبرانی']].map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <select className="inp" value={f.flex_type} onChange={e => set('flex_type', e.target.value)}>
            <option value="fixed">زمان ثابت</option>
            <option value="flexible">منعطف (اعلام بعدی)</option>
          </select>
          <select className="inp" value={f.group} onChange={e => set('group', e.target.value)}>
            {['هر دو', 'الف', 'ب'].map(g => <option key={g}>{g}</option>)}
          </select>
        </div>
        <input className="inp" placeholder="درس / عنوان *" value={f.lesson} onChange={e => set('lesson', e.target.value)} />
        <div className="row">
          <input className="inp" type="date" value={f.date} onChange={e => set('date', e.target.value)} />
          <input className="inp" type="time" value={f.time} onChange={e => set('time', e.target.value)} />
        </div>
        <input className="inp" placeholder="استاد…" value={f.teacher} onChange={e => set('teacher', e.target.value)} />
        <input className="inp" placeholder="مکان…" value={f.location} onChange={e => set('location', e.target.value)} />
        <textarea className="inp" rows={2} placeholder="یادداشت…" value={f.note} onChange={e => set('note', e.target.value)} />
        <div className="row">
          <button className="btn primary" disabled={busy || !f.lesson.trim() || !f.date} onClick={async () => {
            setBusy(true);
            try {
              const body = { ...f };
              if (row) { delete body.type; await api.caScheduleEdit(row.id, body); }
              else await api.caScheduleCreate(body);
              toast('ثبت شد ✅'); onClose(true);
            } catch (e) { toast(errText(e), 'err'); }
            setBusy(false);
          }}>{row ? 'ذخیره' : 'ایجاد + اطلاع‌رسانی'}</button>
          <button className="btn" onClick={() => onClose(false)}>انصراف</button>
        </div>
      </div>
    </Modal>
  );
}

function FlexModal({ row, onClose }) {
  const [f, setF] = useState({ date: row.date || '', time: row.time || '', note: '' });
  const [busy, setBusy] = useState(false);
  return (
    <Modal title={`🔄 اعلام زمان جدید — ${row.lesson}`} onClose={() => onClose(false)}>
      <div className="grid" style={{ gap: 10 }}>
        <p className="muted">این اکشن زمان جدید را ثبت و برای دانشجویان این گروه اطلاع‌رسانی می‌کند.</p>
        <div className="row">
          <input className="inp" type="date" value={f.date} onChange={e => setF(x => ({ ...x, date: e.target.value }))} />
          <input className="inp" type="time" value={f.time} onChange={e => setF(x => ({ ...x, time: e.target.value }))} />
        </div>
        <input className="inp" placeholder="یادداشت (اختیاری)…" value={f.note} onChange={e => setF(x => ({ ...x, note: e.target.value }))} />
        <div className="row">
          <button className="btn primary" disabled={busy || !f.date} onClick={async () => {
            setBusy(true);
            try {
              const r = await api.caFlexChange(row.id, f);
              toast(`زمان جدید ثبت و به ${Number(r.notified || 0).toLocaleString('fa')} نفر اطلاع داده شد ✅`);
              onClose(true);
            } catch (e) { toast(errText(e), 'err'); }
            setBusy(false);
          }}>اعلام</button>
          <button className="btn" onClick={() => onClose(false)}>انصراف</button>
        </div>
      </div>
    </Modal>
  );
}

// ── 🗂 بانک سؤال (فایل‌های PDF/ویدیو/ویس مباحث) ─────────────────────
export function QbankTab() {
  const intakes = useIntakes();
  const [intake, setIntake] = useState('');
  const [lesson, setLesson] = useState('');
  const [topic, setTopic] = useState('');
  const [files, setFiles] = useState(null);
  const [err, setErr] = useState('');
  const [permErr, setPermErr] = useState(false);
  const [addModal, setAddModal] = useState(false);
  const [confirm, setConfirm] = useState(null);

  const load = async () => {
    setErr('');
    try { setFiles((await api.caQbank({ lesson, topic, intake })).files || []); }
    catch (e) { if (e.status === 403) setPermErr(true); else setErr(errText(e)); }
  };
  useEffect(() => { setFiles(null); load(); }, [intake]);

  if (permErr) return <NoPerm text="بانک سؤال فقط برای مدیر محتواست" />;
  if (err) return <ErrorState error={err} onRetry={load} />;

  const FT = { video: '🎬 ویدیو', voice: '🎙 ویس', document: '📕 سند' };
  return (
    <>
      <div className="row" style={{ marginBottom: 12 }}>
        <IntakeSelect intakes={intakes} value={intake} onChange={setIntake} />
        <input className="inp" placeholder="درس…" value={lesson} onChange={e => setLesson(e.target.value)} />
        <input className="inp" placeholder="مبحث…" value={topic} onChange={e => setTopic(e.target.value)} />
        <button className="btn sm" onClick={() => { setFiles(null); load(); }}>🔎 اعمال فیلتر</button>
        <span className="spacer" />
        <button className="btn primary" onClick={() => setAddModal(true)}>⬆️ آپلود فایل</button>
      </div>
      {!files ? <Loading /> : files.length === 0 ? <Empty icon="🗂" text="فایلی نیست — فیلتر را خالی کنید یا فایل تازه آپلود کنید" /> : (
        <div className="grid" style={{ gap: 6 }}>
          {files.map(f => (
            <div key={f.id} className="panel row" style={{ padding: '9px 14px' }}>
              <span style={{ fontSize: 16 }}>{f.file_type === 'video' ? '🎬' : f.file_type === 'voice' ? '🎙' : '📕'}</span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <b style={{ color: 'var(--txt)' }}>{f.lesson}</b>
                <span className="muted"> — {f.topic}</span>
                <div className="muted">{f.description || ''}</div>
              </div>
              {f.readonly && <B>🔒 فقط‌خواندنی</B>}
              <B kind="acc">{FT[f.file_type] || f.file_type}</B>
              <B>{Number(f.downloads || 0).toLocaleString('fa')} DL</B>
              <span className="muted">{f.upload_date}</span>
              {!f.readonly && (
                <button className="btn sm danger" onClick={() => setConfirm({
                  text: `حذف فایل «${f.description || f.topic}»؟`,
                  run: async () => { await api.caQbankDel(f.id); toast('حذف شد'); load(); },
                })}>🗑</button>)}
            </div>
          ))}
        </div>
      )}
      {addModal && <QbankAddModal intakes={intakes} defaultIntake={intake}
                                  onClose={(ok) => { setAddModal(false); if (ok) load(); }} />}
      {confirm && <Confirm text={confirm.text} danger
                           onYes={async () => { await confirm.run(); setConfirm(null); }}
                           onNo={() => setConfirm(null)} />}
    </>
  );
}

function QbankAddModal({ intakes, defaultIntake, onClose }) {
  const [f, setF] = useState({ lesson: '', topic: '', description: '', intake: defaultIntake || '' });
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  return (
    <Modal title="⬆️ آپلود فایل بانک سؤال" onClose={() => onClose(false)}>
      <div className="grid" style={{ gap: 10 }}>
        <div className="row">
          <input className="inp" style={{ flex: 1 }} placeholder="درس *" value={f.lesson}
                 onChange={e => setF(x => ({ ...x, lesson: e.target.value }))} />
          <input className="inp" style={{ flex: 1 }} placeholder="مبحث *" value={f.topic}
                 onChange={e => setF(x => ({ ...x, topic: e.target.value }))} />
        </div>
        <IntakeSelect intakes={intakes} value={f.intake} onChange={v => setF(x => ({ ...x, intake: v }))} />
        <input className="inp" placeholder="توضیح…" value={f.description}
               onChange={e => setF(x => ({ ...x, description: e.target.value }))} />
        <input type="file" className="inp" onChange={e => setFile(e.target.files[0] || null)} />
        <div className="row">
          <button className="btn primary" disabled={busy || !f.lesson.trim() || !f.topic.trim() || !file} onClick={async () => {
            setBusy(true);
            try {
              const fd = new FormData();
              fd.append('lesson', f.lesson.trim()); fd.append('topic', f.topic.trim());
              fd.append('description', f.description); fd.append('intake', f.intake || '');
              fd.append('file', file);
              await api.caQbankAdd(fd);
              toast('آپلود شد ✅'); onClose(true);
            } catch (e) { toast(errText(e), 'err'); }
            setBusy(false);
          }}>{busy ? '⏳ در حال آپلود…' : 'آپلود'}</button>
          <button className="btn" onClick={() => onClose(false)}>انصراف</button>
        </div>
      </div>
    </Modal>
  );
}

// ── ❓ FAQ ──────────────────────────────────────────────────────────
export function FaqTab() {
  const [items, setItems] = useState(null);
  const [err, setErr] = useState('');
  const [permErr, setPermErr] = useState(false);
  const [addModal, setAddModal] = useState(false);
  const [confirm, setConfirm] = useState(null);
  const [open, setOpen] = useState({});

  const load = async () => {
    setErr('');
    try { setItems((await api.caFaq()).items || []); }
    catch (e) { if (e.status === 403) setPermErr(true); else setErr(errText(e)); }
  };
  useEffect(() => { load(); }, []);

  if (permErr) return <NoPerm text="مدیریت FAQ فقط برای مدیر محتواست" />;
  if (err) return <ErrorState error={err} onRetry={load} />;

  const cats = {};
  (items || []).forEach(i => { (cats[i.category] = cats[i.category] || []).push(i); });
  return (
    <>
      <div className="row" style={{ marginBottom: 12 }}>
        <span className="muted">{(items || []).length} پرسش</span>
        <span className="spacer" />
        <button className="btn primary" onClick={() => setAddModal(true)}>➕ پرسش جدید</button>
      </div>
      {!items ? <Loading /> : items.length === 0 ? <Empty icon="❓" text="پرسشی نیست" /> :
        Object.entries(cats).map(([cat, rows]) => (
          <div key={cat} className="panel" style={{ marginBottom: 10 }}>
            <div className="panel-pad row" style={{ padding: '10px 14px', borderBottom: '1px solid var(--line)' }}>
              <b>🗂 {cat}</b><B>{rows.length}</B>
            </div>
            {rows.map(f => (
              <div key={f.id} className="row" style={{ padding: '9px 14px', borderBottom: '1px solid var(--line)', alignItems: 'flex-start' }}>
                <div style={{ flex: 1, cursor: 'pointer' }} onClick={() => setOpen(x => ({ ...x, [f.id]: !x[f.id] }))}>
                  <div style={{ color: 'var(--txt)', fontSize: 12.5 }}>{open[f.id] ? '▾' : '▸'} {f.question}</div>
                  {open[f.id] && <div className="muted" style={{ marginTop: 6, lineHeight: 1.9, whiteSpace: 'pre-wrap' }}>{f.answer}</div>}
                </div>
                <button className="btn sm danger" onClick={() => setConfirm({
                  text: `حذف پرسش «${f.question.slice(0, 40)}…»؟`,
                  run: async () => { await api.caFaqDel(f.id); toast('حذف شد'); load(); },
                })}>🗑</button>
              </div>
            ))}
          </div>
        ))}
      {addModal && <FaqAddModal onClose={(ok) => { setAddModal(false); if (ok) load(); }} />}
      {confirm && <Confirm text={confirm.text} danger
                           onYes={async () => { await confirm.run(); setConfirm(null); }}
                           onNo={() => setConfirm(null)} />}
    </>
  );
}

function FaqAddModal({ onClose }) {
  const [f, setF] = useState({ category: 'عمومی', question: '', answer: '' });
  const [busy, setBusy] = useState(false);
  return (
    <Modal title="➕ پرسش متداول جدید" onClose={() => onClose(false)}>
      <div className="grid" style={{ gap: 10 }}>
        <input className="inp" placeholder="دسته…" value={f.category}
               onChange={e => setF(x => ({ ...x, category: e.target.value }))} />
        <input className="inp" placeholder="پرسش (حداقل ۵ حرف) *" value={f.question}
               onChange={e => setF(x => ({ ...x, question: e.target.value }))} />
        <textarea className="inp" rows={4} placeholder="پاسخ (حداقل ۵ حرف) *" value={f.answer}
                  onChange={e => setF(x => ({ ...x, answer: e.target.value }))} />
        <div className="row">
          <button className="btn primary" disabled={busy || f.question.trim().length < 5 || f.answer.trim().length < 5} onClick={async () => {
            setBusy(true);
            try {
              await api.caFaqAdd({ category: f.category.trim() || 'عمومی', question: f.question.trim(), answer: f.answer.trim() });
              toast('ثبت شد ✅'); onClose(true);
            } catch (e) { toast(errText(e), 'err'); }
            setBusy(false);
          }}>ثبت</button>
          <button className="btn" onClick={() => onClose(false)}>انصراف</button>
        </div>
      </div>
    </Modal>
  );
}
