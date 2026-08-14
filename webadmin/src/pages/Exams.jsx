import React, { useEffect, useState } from 'react';
import { api, errText } from '../api.js';
import { DataTable, Loading, ErrorState, B, toast, Confirm, Modal, Stat, NoPerm } from '../ui.jsx';

const ST = [
  ['', 'همه'],
  ['scheduled', 'زمان‌بندی‌شده'],
  ['active', 'در حال برگزاری'],
  ['finished', 'برگزارشده'],
];

// 📝🌊 WA2.2 — مدیریت آزمون‌ها: CRUD روی schedules type=exam + آمار آزمون‌های تمرینی
// 🌊 WA3 — تب دوم «نمرات»: recent + جستجوی دانشجو + ثبت گروهی (معادل ربات)
export default function Exams() {
  const [tab, setTab] = useState('exams');
  return (
    <>
      <div className="tabs" style={{ marginBottom: 14 }}>
        {[['exams', '📝 آزمون‌ها'], ['grades', '📊 نمرات']].map(([k, v]) => (
          <button key={k} className={`tab ${tab === k ? 'on' : ''}`} onClick={() => setTab(k)}>{v}</button>
        ))}
      </div>
      {tab === 'exams' ? <ExamsTab /> : <GradesTab />}
    </>
  );
}

function ExamsTab() {
  const [status, setStatus] = useState('');
  const [data, setData] = useState(null);
  const [stats, setStats] = useState(null);
  const [err, setErr] = useState('');
  const [permErr, setPermErr] = useState(false);
  const [edit, setEdit] = useState(null);       // null | {} new | {row}
  const [confirm, setConfirm] = useState(null);

  const load = async () => {
    setErr('');
    try {
      const r = await api.exams(status || undefined);
      setData(r);
    } catch (e) {
      if (e.status === 403) setPermErr(true); else setErr(errText(e));
    }
  };
  useEffect(() => { setData(null); load(); }, [status]);
  useEffect(() => { api.examStats().then(setStats).catch(() => {}); }, []);

  if (permErr) return <NoPerm text="مدیریت آزمون‌ها نیازمند مجوز «مدیریت برنامه و امتحان» (schedules.manage) است" />;
  if (err) return <ErrorState error={err} onRetry={load} />;

  const counts = (data && data.counts) || {};
  const cols = [
    { k: 'lesson', label: 'درس / عنوان', render: r => (
      <div><b style={{ color: 'var(--txt)' }}>{r.lesson}</b>
        <div className="muted">{r.teacher || ''}</div></div>) },
    { k: 'date', label: 'تاریخ', render: r => <span className="code">{r.date}</span> },
    { k: 'time', label: 'ساعت', render: r => r.time || '—' },
    { k: 'group', label: 'گروه' },
    { k: 'location', label: 'مکان', render: r => r.location || '—' },
    { k: 'status', label: 'وضعیت', render: r => (
      <B kind={r.status === 'active' ? 'bad' : r.status === 'scheduled' ? 'acc' : 'ok'}>{r.status_fa}</B>) },
    { k: 'reminded', label: 'یادآوری', render: r => (r.reminded || []).length
      ? <B kind="purple">{(r.reminded || []).join(' ')}</B> : <span className="muted">—</span> },
    { k: 'ops', label: '', stop: true, render: r => (
      <div className="row" style={{ gap: 4 }}>
        <button className="btn sm" onClick={() => setEdit(r)}>✏️</button>
        <button className="btn sm danger" onClick={() => setConfirm(r)}>🗑</button>
      </div>) },
  ];

  return (
    <>
      <div className="row">
        <div><div className="h1">مدیریت آزمون‌ها</div>
          <div className="sub">آزمون‌های رسمی (اطلاع‌رسانی خودکار ۷/۳/۱ روز قبل توسط ربات)</div></div>
        <span className="spacer" />
        <button className="btn primary" onClick={() => setEdit({})}>➕ آزمون جدید</button>
      </div>

      {stats && (
        <div className="grid g4" style={{ marginBottom: 14 }}>
          <Stat icon="🧪" label="کل آزمون‌های تمرینی اجراشده" value={Number(stats.total_runs || 0).toLocaleString('fa')} tint="var(--acc)" />
          <Stat icon="🏁" label="تکمیل‌شده" value={Number(stats.finished || 0).toLocaleString('fa')} tint="var(--ok)" />
          <Stat icon="🎯" label="میانگین درصد (آزمون تمرینی)" value={stats.avg_pct != null ? `${Number(stats.avg_pct).toLocaleString('fa')}٪` : '—'} tint="var(--purple)" />
          <Stat icon="🗓" label="اجرا در ۷ روز اخیر" value={Number(stats.runs_7d || 0).toLocaleString('fa')} tint="var(--warn)" />
        </div>
      )}

      <div className="tabs">
        {ST.map(([k, v]) => (
          <button key={k} className={`tab ${status === k ? 'on' : ''}`} onClick={() => setStatus(k)}>
            {v}{k && counts[k] != null ? ` (${Number(counts[k]).toLocaleString('fa')})` : ''}
          </button>
        ))}
      </div>

      {!data ? <Loading /> : (
        <DataTable columns={cols} rows={data.exams} empty={
          <div className="center-state">آزمونی در این وضعیت نیست</div>} />
      )}

      {edit && <ExamModal row={edit.id ? edit : null} onClose={(ch) => { setEdit(null); if (ch) load(); }} />}
      {confirm && (
        <Confirm text={`حذف آزمون «${confirm.lesson}» (${confirm.date})؟`} danger
                 onYes={async () => {
                   try { await api.examDelete(confirm.id); toast('حذف شد'); setConfirm(null); load(); }
                   catch (e) { toast(errText(e), 'err'); setConfirm(null); }
                 }}
                 onNo={() => setConfirm(null)} />
      )}
    </>
  );
}

// 🌊 موج Exams-Builder — سازنده‌ی مرحله‌ای: مشخصات ← زمان/مکان ← بازبینی و ثبت
// (همان payload قبلی؛ فقط UX گام‌به‌گام با اعتبارسنجی هر گام)
const EX_STEPS = [['مشخصات', '📚'], ['زمان و مکان', '🗓'], ['بازبینی و ثبت', '✅']];

function ExamModal({ row, onClose }) {
  const [f, setF] = useState({
    lesson: row?.lesson || '', date: row?.date || '', time: row?.time || '',
    teacher: row?.teacher || '', location: row?.location || '',
    notes: row?.notes || '', group: row?.group || 'هر دو',
  });
  const [step, setStep] = useState(1);
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF(x => ({ ...x, [k]: v }));

  const faDate = (() => {
    if (!f.date) return '—';
    try { return new Date(f.date + 'T00:00:00').toLocaleDateString('fa-IR', { dateStyle: 'full' }); }
    catch { return f.date; }
  })();
  const okStep1 = !!f.lesson.trim();
  const okStep2 = !!f.date;
  const todayIso = new Date().toLocaleDateString('en-CA');

  const submit = async () => {
    setBusy(true);
    try {
      if (row) await api.examUpdate(row.id, f);
      else await api.examCreate(f);
      toast(row ? 'ویرایش شد ✅' : 'آزمون ساخته شد ✅ — اطلاع‌رسانی خودکار ۷/۳/۱ روز قبل فعال است'); onClose(true);
    } catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };

  return (
    <Modal title={row ? `✏️ ویرایش آزمون — ${row.lesson}` : '📝 سازنده‌ی آزمون جدید'} onClose={() => onClose(false)}>
      <div className="wiz-steps" style={{ marginBottom: 14 }}>
        {EX_STEPS.map(([label, icon], i) => (
          <div key={label} className={`wiz-step ${step === i + 1 ? 'on' : ''} ${step > i + 1 ? 'done' : ''}`}
               onClick={() => { if (step > i + 1) setStep(i + 1); }}>
            <span className="wiz-n">{step > i + 1 ? '✓' : Number(i + 1).toLocaleString('fa')}</span>
            <span className="wiz-l">{icon} {label}</span>
          </div>
        ))}
      </div>

      {step === 1 && (
        <div className="grid" style={{ gap: 10 }}>
          <label className="muted" style={{ fontSize: 11 }}>درس / عنوان آزمون *
            <input className="inp" placeholder="مثلاً فیزیولوژی — آزمون میانترم قلب" value={f.lesson}
                   onChange={e => set('lesson', e.target.value)} autoFocus /></label>
          <label className="muted" style={{ fontSize: 11 }}>استاد
            <input className="inp" placeholder="نام استاد…" value={f.teacher} onChange={e => set('teacher', e.target.value)} /></label>
          <label className="muted" style={{ fontSize: 11 }}>گروه هدف
            <div className="row">
              {['هر دو', 'الف', 'ب'].map(g => (
                <label key={g} className={`pick ${f.group === g ? 'on' : ''}`} style={{ flex: 1 }}>
                  <input type="radio" checked={f.group === g} onChange={() => set('group', g)} />
                  <b>{g === 'هر دو' ? '👥 هر دو گروه' : g === 'الف' ? '1️⃣ الف' : '2️⃣ ب'}</b>
                </label>
              ))}
            </div>
          </label>
          <button className="btn primary" disabled={!okStep1} onClick={() => setStep(2)}>ادامه ←</button>
        </div>
      )}

      {step === 2 && (
        <div className="grid" style={{ gap: 10 }}>
          <div className="row">
            <label className="muted" style={{ fontSize: 11, flex: 1 }}>تاریخ *
              <input className="inp" type="date" style={{ direction: 'ltr' }} value={f.date}
                     onChange={e => set('date', e.target.value)} /></label>
            <label className="muted" style={{ fontSize: 11, width: 130 }}>ساعت
              <input className="inp" type="time" style={{ direction: 'ltr' }} value={f.time}
                     onChange={e => set('time', e.target.value)} /></label>
          </div>
          {f.date && (
            <div className="ct3-kv"><span className="muted">نمایش به دانشجو</span>
              <B kind={f.date < todayIso ? 'warn' : 'acc'}>{faDate}{f.time ? ` · ساعت ${f.time}` : ''}</B>
            </div>
          )}
          {f.date && f.date < todayIso && !row && (
            <span className="muted" style={{ color: 'var(--c-warn)', fontSize: 11 }}>
              ⚠️ تاریخ در گذشته است — آزمون «برگزارشده» ثبت می‌شود و اطلاع‌رسانی نخواهد داشت.</span>
          )}
          <label className="muted" style={{ fontSize: 11 }}>مکان
            <input className="inp" placeholder="سایت امتحانات / سالن…" value={f.location} onChange={e => set('location', e.target.value)} /></label>
          <label className="muted" style={{ fontSize: 11 }}>یادداشت (اختیاری)
            <textarea className="inp" rows={2} placeholder="نکته‌ی تکمیلی برای دانشجویان…" value={f.notes}
                      onChange={e => set('notes', e.target.value)} /></label>
          <div className="row">
            <button className="btn" onClick={() => setStep(1)}>→ بازگشت</button>
            <button className="btn primary" disabled={!okStep2} onClick={() => setStep(3)}>ادامه ←</button>
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="grid" style={{ gap: 8 }}>
          <div className="ct3-kv"><span className="muted">عنوان</span><b>{f.lesson}</b></div>
          <div className="ct3-kv"><span className="muted">استاد</span><span>{f.teacher || '—'}</span></div>
          <div className="ct3-kv"><span className="muted">گروه</span><B>{f.group}</B></div>
          <div className="ct3-kv"><span className="muted">زمان</span><span>{faDate}{f.time ? ` · ${f.time}` : ''}</span></div>
          <div className="ct3-kv"><span className="muted">مکان</span><span>{f.location || '—'}</span></div>
          {f.notes && <div className="ct3-kv"><span className="muted">یادداشت</span><span>{f.notes}</span></div>}
          <div className="panel panel-pad" style={{ background: 'var(--bg)', fontSize: 12 }}>
            🤖 پس از ثبت، ربات <b>۷، ۳ و ۱ روز قبل</b> به دانشجویانِ {f.group === 'هر دو' ? 'هر دو گروه' : `گروه ${f.group}`} خودکار یادآوری می‌کند.
          </div>
          <div className="row">
            <button className="btn" onClick={() => setStep(2)}>→ بازگشت</button>
            <button className="btn primary" style={{ flex: 1 }} disabled={busy} onClick={submit}>
              {busy ? '⏳ …' : row ? '💾 ذخیره‌ی تغییرات' : '📝 ثبت آزمون'}
            </button>
          </div>
        </div>
      )}
    </Modal>
  );
}

/* ── 📊🌊 WA3 — تب نمرات: لیست اخیر + ثبت گروهی (همان grades ربات) ───── */
function GradesTab() {
  const [skip, setSkip] = useState(0);
  const [data, setData] = useState(null);
  const [err, setErr] = useState('');
  const [permErr, setPermErr] = useState(false);
  const [bulkOpen, setBulkOpen] = useState(false);
  const LIMIT = 30;

  const load = async () => {
    setErr('');
    try { setData(await api.gradesRecent(skip, LIMIT)); }
    catch (e) { if (e.status === 403) setPermErr(true); else setErr(errText(e)); }
  };
  useEffect(() => { setData(null); load(); }, [skip]);

  if (permErr) return <NoPerm text="مدیریت نمرات نیازمند مجوز «مدیریت نمرات» (grades.manage) است" />;
  if (err) return <ErrorState error={err} onRetry={load} />;

  const total = data?.total || 0;
  const page = Math.floor(skip / LIMIT) + 1;
  const pages = Math.max(1, Math.ceil(total / LIMIT));
  const cols = [
    { k: 'student_name', label: 'دانشجو', render: r => (
      <div><b style={{ color: 'var(--txt)' }}>{r.student_name || '—'}</b>
        <div className="muted code">#{r.student_id}</div></div>) },
    { k: 'lesson', label: 'درس' },
    { k: 'exam_title', label: 'عنوان آزمون' },
    { k: 'exam_date', label: 'تاریخ', render: r => <span className="code">{r.exam_date}</span> },
    { k: 'score', label: 'نمره', render: r => (
      <B kind={r.score >= 10 ? 'ok' : 'bad'}>{Number(r.score).toLocaleString('fa')}</B>) },
  ];
  return (
    <>
      <div className="row">
        <div><div className="h1">نمرات</div>
          <div className="sub">ثبت گروهی نمره — همان «📊 مدیریت نمرات» پنل ربات؛ به هر دانشجو از سمت ربات خبر می‌رسد</div></div>
        <span className="spacer" />
        <button className="btn primary" onClick={() => setBulkOpen(true)}>➕ ثبت گروهی نمره</button>
      </div>

      {!data ? <Loading /> : (
        <>
          <DataTable columns={cols} rows={data.grades} empty={
            <div className="center-state">نمره‌ای ثبت نشده</div>} />
          <div className="row" style={{ marginTop: 10 }}>
            <span className="muted">مجموع: {Number(total).toLocaleString('fa')} نمره</span>
            <span className="spacer" />
            <button className="btn sm" disabled={skip <= 0} onClick={() => setSkip(Math.max(0, skip - LIMIT))}>قبلی ◂</button>
            <B>{Number(page).toLocaleString('fa')} / {Number(pages).toLocaleString('fa')}</B>
            <button className="btn sm" disabled={skip + LIMIT >= total} onClick={() => setSkip(skip + LIMIT)}>▸ بعدی</button>
          </div>
        </>
      )}
      {bulkOpen && <GradeBulkModal onClose={(ch) => { setBulkOpen(false); if (ch) { setSkip(0); load(); } }} />}
    </>
  );
}

function GradeBulkModal({ onClose }) {
  const [meta, setMeta] = useState({ lesson: '', exam_title: '', exam_date: '' });
  const [rows, setRows] = useState([{ q: '', hits: null, picked: null, score: '' }]);
  const [busy, setBusy] = useState(false);
  const setRow = (i, patch) => setRows(rs => rs.map((r, j) => j === i ? { ...r, ...patch } : r));

  const find = async (i) => {
    const q = rows[i].q.trim();
    if (q.length < 2) return toast('حداقل ۲ حرف برای جست‌وجو', 'err');
    try { setRow(i, { hits: (await api.gradesFind(q)).students || [], picked: null }); }
    catch (e) { toast(errText(e), 'err'); }
  };
  const submit = async () => {
    const entries = rows.filter(r => r.picked && r.score !== '').map(r => ({
      student_id: r.picked.id, score: Number(r.score),
    }));
    if (!entries.length) return toast('حداقل یک دانشجو با نمره لازم است', 'err');
    setBusy(true);
    try {
      const r = await api.gradesBulk({ entries, lesson: meta.lesson.trim(),
        exam_title: meta.exam_title.trim(), exam_date: meta.exam_date });
      toast(`${r.updated} نمره ثبت شد و برای دانشجویان ارسال شد 📊`);
      onClose(true);
    } catch (e) { toast(errText(e), 'err'); setBusy(false); }
  };

  return (
    <Modal title="➕ ثبت گروهی نمره" onClose={() => onClose(false)}>
      <div className="grid" style={{ gap: 10 }}>
        <div className="row">
          <input className="inp" placeholder="درس *" value={meta.lesson}
                 onChange={e => setMeta({ ...meta, lesson: e.target.value })} />
          <input className="inp" placeholder="عنوان آزمون *" value={meta.exam_title}
                 onChange={e => setMeta({ ...meta, exam_title: e.target.value })} />
          <input className="inp" type="date" title="تاریخ آزمون" value={meta.exam_date}
                 onChange={e => setMeta({ ...meta, exam_date: e.target.value })} />
        </div>
        {rows.map((r, i) => (
          <div key={i} className="panel panel-pad" style={{ background: 'var(--bg)' }}>
            <div className="row">
              <input className="inp" style={{ flex: 1 }} placeholder="نام/شماره دانشجویی/یوزرنیم…"
                     value={r.q} onChange={e => setRow(i, { q: e.target.value, hits: null, picked: null })}
                     onKeyDown={e => e.key === 'Enter' && find(i)} />
              <button className="btn sm" onClick={() => find(i)}>🔎</button>
              <input className="inp" type="number" step="0.25" min="0" max="20" style={{ width: 90 }}
                     placeholder="نمره" value={r.score} onChange={e => setRow(i, { score: e.target.value })} />
              <button className="btn sm danger" disabled={rows.length === 1}
                      onClick={() => setRows(rs => rs.filter((_, j) => j !== i))}>✕</button>
            </div>
            {r.hits && !r.picked && (
              <div style={{ marginTop: 6 }}>
                {r.hits.length === 0 && <span className="muted">دانشجویی یافت نشد</span>}
                {r.hits.slice(0, 5).map(s => (
                  <button key={s.id} className="btn sm" style={{ margin: '3px 0 3px 5px' }}
                          onClick={() => setRow(i, { picked: s, hits: null, q: `${s.name} (${s.student_id || s.id})` })}>
                    {s.name} · <span className="code">{s.student_id || s.id}</span> {s.group ? `· ${s.group}` : ''}
                  </button>
                ))}
              </div>
            )}
            {r.picked && <div className="muted" style={{ marginTop: 5 }}>✅ {r.picked.name} انتخاب شد</div>}
          </div>
        ))}
        <div className="row">
          <button className="btn sm" onClick={() => setRows(rs => [...rs, { q: '', hits: null, picked: null, score: '' }])}>➕ ردیف جدید</button>
          <span className="spacer" />
          <span className="muted">{rows.filter(r => r.picked && r.score !== '').length} دانشجو آماده</span>
        </div>
        <div className="row">
          <button className="btn primary" disabled={busy || !meta.lesson.trim() || !meta.exam_title.trim() || !meta.exam_date}
                  onClick={submit}>{busy ? '⏳ …' : 'ثبت و ارسال به دانشجویان'}</button>
          <button className="btn" onClick={() => onClose(false)}>انصراف</button>
        </div>
      </div>
    </Modal>
  );
}
