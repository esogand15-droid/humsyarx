import React, { useEffect, useState } from 'react';
import { api, errText } from '../api.js';
import { B, DataTable, Empty, Loading, PageHeader, toast } from '../ui.jsx';

const fa = n => Number(n ?? 0).toLocaleString('fa-IR');

/* 🌊 QBANK-W3/§۷.۲ — صف تصاویر منتظر: اتصال تکی + تطبیق انبوه */
export default function PendingImages() {
  const [rows, setRows] = useState(null);
  const [total, setTotal] = useState(0);
  const [jobId, setJobId] = useState('');
  const [busy, setBusy] = useState(false);
  const [bulkJob, setBulkJob] = useState('');
  const [bulkFiles, setBulkFiles] = useState([]);
  const [bulkReport, setBulkReport] = useState(null);
  const [noPerm, setNoPerm] = useState(false);

  const load = async () => {
    setRows(null); setNoPerm(false);
    try {
      const data = await api.pendingImages({ job_id: jobId || undefined, limit: 100 });
      setRows(data.items || []); setTotal(data.total || 0);
    } catch (e) {
      if (e.status === 403) { setNoPerm(true); setRows([]); }
      else toast(errText(e), 'err');
    }
  };

  useEffect(() => { load(); }, []);

  const attach = async (row, file) => {
    if (!file) return;
    setBusy(true);
    try {
      await api.attachQuestionImage(row.id, file);
      toast('تصویر وصل شد ✅');
      await load();
    } catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };

  const runBulk = async () => {
    if (!bulkJob || !bulkFiles.length) return;
    setBusy(true); setBulkReport(null);
    try {
      const data = await api.bulkMatchImages(bulkJob, bulkFiles);
      setBulkReport(data);
      toast(`${fa(data.attached)} تصویر وصل شد ✅`);
      await load();
    } catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };

  const STATUS = { attached: ['✅ وصل شد', 'ok'], no_match: ['❓ بدون تطبیق', 'warn'], ambiguous: ['⚠️ مبهم (چند سؤال هم‌صفحه)', 'bad'], invalid_name: ['❌ نام نامعتبر', 'bad'], failed: ['❌ خطا', 'bad'] };

  const columns = [
    { k: 'question', label: 'سؤال', render: r => <div style={{ maxWidth: 320 }}>{r.question}<small className="muted" style={{ display: 'block' }}>{r.lesson} / {r.topic}{r.exam_year ? ` · 📅 ${r.exam_year}` : ''}</small></div> },
    { k: 'ref', label: 'نشانی تصویر', render: r => <div><span className="code" style={{ fontSize: 11 }}>{(r.source_file_name || '').slice(0, 40)}</span><small className="muted" style={{ display: 'block' }}>📄 ص {r.image_ref?.page || r.source_page || '؟'}{r.image_ref?.position ? ` · ${r.image_ref.position}` : ''}</small></div> },
    { k: 'ops', label: '', stop: true, render: r => <div className="row"><input className="inp" type="file" accept="image/jpeg,image/png,image/webp,image/gif" disabled={busy} onChange={e => { attach(r, e.target.files?.[0]); e.target.value = ''; }} style={{ maxWidth: 220 }} /></div> },
  ];

  return <>
    <PageHeader title="🖼 صف تصاویر منتظر" description="سؤال‌های approved که تا اتصال تصویر در تمرین/آزمون پنهان‌اند — قدیمی‌ترین اول" actions={<>
      <input className="inp" placeholder="فیلتر job_id (اختیاری)" value={jobId} onChange={e => setJobId(e.target.value)} style={{ maxWidth: 260 }} />
      <button className="btn" onClick={load}>↻ تازه‌سازی</button>
    </>} />
    {noPerm && <div className="panel panel-pad"><B kind="bad">دسترسی محدود</B><p className="muted">این صفحه فقط برای مالک (مجوز درون‌ریزی) است.</p></div>}
    {!rows ? <Loading /> : rows.length === 0 && !noPerm ? <Empty icon="🖼" text="صف خالی است — همه تصاویر وصل‌اند 🎉" /> : <>
      <div className="muted" style={{ marginBottom: 8 }}>⏳ {fa(total)} سؤال منتظر تصویر</div>
      <DataTable columns={columns} rows={rows} rowKey="id" />
    </>}
    <div className="panel panel-pad" style={{ marginTop: 16 }}>
      <b>⚡ تطبیق انبوه</b>
      <p className="muted">نام فایل‌ها باید <span className="code">{'{fingerprint}_{page}.png'}</span> باشد (fingerprint همان job؛ حداقل ۸ کاراکتر اول کافی است). هر فایل به سؤال منتظرِ هم‌صفحه‌ی همان job وصل می‌شود.</p>
      <div className="row" style={{ flexWrap: 'wrap' }}>
        <input className="inp" placeholder="job_id" value={bulkJob} onChange={e => setBulkJob(e.target.value)} style={{ maxWidth: 300 }} />
        <input className="inp" type="file" accept="image/*" multiple onChange={e => setBulkFiles([...(e.target.files || [])])} />
        <button className="btn primary" disabled={busy || !bulkJob || !bulkFiles.length} onClick={runBulk}>{busy ? 'در حال تطبیق…' : `تطبیق ${fa(bulkFiles.length)} فایل`}</button>
      </div>
      {bulkReport && <div style={{ marginTop: 10 }}>{bulkReport.results.map((r, i) => { const [label, kind] = STATUS[r.status] || [r.status, '']; return <div key={i} className="row" style={{ marginTop: 4 }}><span className="code" style={{ fontSize: 11 }}>{r.file}</span><B kind={kind}>{label}</B>{r.error && <small className="muted">{r.error}</small>}</div>; })}</div>}
    </div>
  </>;
}
