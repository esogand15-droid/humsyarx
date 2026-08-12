import React, { useEffect, useState } from 'react';
import { api, errText } from '../api.js';
import { DataTable, Loading, ErrorState, B, toast, Modal, Confirm } from '../ui.jsx';

// 🧪 صف بازبینی سوالات (scope-aware) + ⚡ WA2.4 تأیید/رد گروهی
export default function Questions() {
  const [rows, setRows] = useState(null);
  const [err, setErr] = useState('');
  const [view, setView] = useState(null);
  const [sel, setSel] = useState([]);
  const [confirm, setConfirm] = useState(null);

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

  const bulk = async (action) => {
    if (!sel.length) return;
    try {
      const r = await api.questionsBulk(action, sel);
      toast(`${r.done} سؤال ${action === 'approve' ? 'تأیید' : 'رد'} شد`);
      setSel([]); load();
    } catch (e) { toast(errText(e), 'err'); }
  };

  if (err) return <ErrorState error={err} onRetry={load} />;

  const cols = [
    { k: 'question', label: 'سؤال', render: r => (
      <div style={{ maxWidth: 380, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
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
      <div className="row">
        <div><div className="h1">بازبینی سوالات</div>
          <div className="sub">سوالات طراحی‌شده توسط دانشجویان در انتظار تأیید — تک‌تک یا گروهی</div></div>
        <span className="spacer" />
        {sel.length > 0 && <>
          <span className="badge acc">{sel.length} انتخاب‌شده</span>
          <button className="btn sm ok" onClick={() => setConfirm({ action: 'approve', n: sel.length })}>✅ تأیید گروهی</button>
          <button className="btn sm danger" onClick={() => setConfirm({ action: 'reject', n: sel.length })}>❌ رد گروهی</button>
        </>}
      </div>
      {!rows ? <Loading /> : <DataTable columns={cols} rows={rows} rowKey="id"
        selectable onSelect={setSel}
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
      {confirm && (
        <Confirm text={`${confirm.action === 'approve' ? 'تأیید' : 'رد'} ${confirm.n} سؤال انتخاب‌شده؟ (فقط موارد داخل scope شما پردازش می‌شوند)`}
                 danger={confirm.action === 'reject'}
                 onYes={async () => { await bulk(confirm.action); setConfirm(null); }}
                 onNo={() => setConfirm(null)} />
      )}
    </>
  );
}
