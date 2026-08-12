import React, { useEffect, useState } from 'react';
import { api, errText } from '../api.js';
import { DataTable, Loading, ErrorState, B, toast, Modal } from '../ui.jsx';

// 🧪 صف بازبینی سوالات (scope-aware) — approve/reject از API content_admin
export default function Questions() {
  const [rows, setRows] = useState(null);
  const [err, setErr] = useState('');
  const [view, setView] = useState(null);

  const load = async () => {
    setErr('');
    try {
      const r = await api.caQuestionsPending();
      setRows(r.questions || r.items || []);
    } catch (e) { setErr(errText(e)); }
  };
  useEffect(() => { load(); }, []);

  const act = async (qid, kind) => {
    try {
      await (kind === 'approve' ? api.caQuestionApprove(qid) : api.caQuestionReject(qid));
      toast(kind === 'approve' ? 'تأیید شد ✅' : 'رد شد');
      load();
    } catch (e) { toast(errText(e), 'err'); }
  };

  if (err) return <ErrorState error={err} onRetry={load} />;

  const cols = [
    { k: 'question', label: 'سؤال', render: r => (
      <div style={{ maxWidth: 420, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {r.question || r.text}</div>) },
    { k: 'lesson', label: 'درس' },
    { k: 'topic', label: 'مبحث' },
    { k: 'difficulty', label: 'سختی', render: r => <B kind={r.difficulty === 'hard' ? 'bad' : r.difficulty === 'medium' ? 'warn' : 'ok'}>
      {r.difficulty === 'hard' ? 'سخت' : r.difficulty === 'medium' ? 'متوسط' : 'آسان'}</B> },
    { k: 'intake', label: 'ورودی', render: r => r.intake || <B>سراسری</B> },
    { k: 'ops', label: '', stop: true, render: r => {
      const id = r.id || r._id;
      return (
        <div className="row" style={{ gap: 4 }}>
          <button className="btn sm" onClick={() => setView(r)}>👁</button>
          <button className="btn sm ok" onClick={() => act(id, 'approve')}>✅</button>
          <button className="btn sm danger" onClick={() => act(id, 'reject')}>❌</button>
        </div>);
    } },
  ];

  return (
    <>
      <div className="h1">بازبینی سوالات</div>
      <div className="sub">سوالات طراحی‌شده توسط دانشجویان در انتظار تأیید</div>
      {!rows ? <Loading /> : <DataTable columns={cols} rows={rows} rowKey="id"
        empty={<div className="center-state">🎉 صف بازبینی خالی است</div>} />}
      {view && (
        <Modal title="مشاهده سؤال" onClose={() => setView(null)}>
          <p style={{ lineHeight: 2, marginBottom: 12 }}>{view.question || view.text}</p>
          <div className="grid" style={{ gap: 6 }}>
            {(view.options || []).map((o, i) => (
              <div key={i} className="badge" style={{ justifyContent: 'flex-start',
                borderColor: i === (view.correct ?? view.answer) ? 'rgba(52,211,153,.6)' : undefined }}>
                {i === (view.correct ?? view.answer) ? '✅' : '▫️'} {o}
              </div>
            ))}
          </div>
          {view.explanation && <p className="muted" style={{ marginTop: 10 }}>💡 {view.explanation}</p>}
        </Modal>
      )}
    </>
  );
}
