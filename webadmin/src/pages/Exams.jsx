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
export default function Exams() {
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

function ExamModal({ row, onClose }) {
  const [f, setF] = useState({
    lesson: row?.lesson || '', date: row?.date || '', time: row?.time || '',
    teacher: row?.teacher || '', location: row?.location || '',
    notes: row?.notes || '', group: row?.group || 'هر دو',
  });
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF(x => ({ ...x, [k]: v }));
  return (
    <Modal title={row ? `✏️ ویرایش آزمون — ${row.lesson}` : '➕ آزمون جدید'} onClose={() => onClose(false)}>
      <div className="grid" style={{ gap: 10 }}>
        <input className="inp" placeholder="درس / عنوان آزمون *" value={f.lesson} onChange={e => set('lesson', e.target.value)} />
        <div className="row">
          <input className="inp" type="date" value={f.date} onChange={e => set('date', e.target.value)} />
          <input className="inp" type="time" value={f.time} onChange={e => set('time', e.target.value)} />
          <select className="inp" value={f.group} onChange={e => set('group', e.target.value)}>
            {['هر دو', 'الف', 'ب'].map(g => <option key={g}>{g}</option>)}
          </select>
        </div>
        <input className="inp" placeholder="استاد…" value={f.teacher} onChange={e => set('teacher', e.target.value)} />
        <input className="inp" placeholder="مکان (سایت امتحانات/سالن)…" value={f.location} onChange={e => set('location', e.target.value)} />
        <textarea className="inp" rows={2} placeholder="یادداشت…" value={f.notes} onChange={e => set('notes', e.target.value)} />
        <div className="row">
          <button className="btn primary" disabled={busy || !f.lesson.trim() || !f.date} onClick={async () => {
            setBusy(true);
            try {
              if (row) await api.examUpdate(row.id, f);
              else await api.examCreate(f);
              toast(row ? 'ویرایش شد ✅' : 'آزمون ساخته شد ✅'); onClose(true);
            } catch (e) { toast(errText(e), 'err'); }
            setBusy(false);
          }}>{row ? 'ذخیره' : 'ایجاد'}</button>
          <button className="btn" onClick={() => onClose(false)}>انصراف</button>
        </div>
      </div>
    </Modal>
  );
}
