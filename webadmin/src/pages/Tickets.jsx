import React, { useEffect, useState } from 'react';
import { api, errText } from '../api.js';
import { Loading, ErrorState, Empty, B, toast } from '../ui.jsx';

// 🎫 کنسول سه‌ستونه‌ی تیکت: لیست | گفت‌وگو | اکشن
export default function Tickets() {
  const [status, setStatus] = useState('');
  const [list, setList] = useState(null);
  const [err, setErr] = useState('');
  const [cur, setCur] = useState(null);
  const [detail, setDetail] = useState(null);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [sel, setSel] = useState([]);   // ⚡ WA2.4 — انتخاب گروهی

  const bulk = async (action) => {
    if (!sel.length) return;
    try {
      const r = await api.ticketsBulk(action, sel);
      toast(`${r.done} تیکت ${action === 'close' ? 'بسته' : 'بازگشایی'} شد`);
      setSel([]); load();
    } catch (e) { toast(errText(e), 'err'); }
  };

  const load = async () => {
    setErr('');
    try { setList(await api.tickets(status || undefined)); }
    catch (e) { setErr(errText(e)); }
  };
  useEffect(() => { load(); }, [status]);

  const open = async (t) => {
    setCur(t.id || t.tid);
    setDetail(null);
    try { setDetail((await api.ticket(t.id || t.tid)).ticket); }
    catch (e) { toast(errText(e), 'err'); }
  };
  const send = async () => {
    if (!text.trim()) return;
    setBusy(true);
    try { await api.ticketReply(cur, text.trim()); setText(''); open({ id: cur }); load(); }
    catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };
  const act = async (fn) => {
    try { await fn(cur); open({ id: cur }); load(); toast('انجام شد'); }
    catch (e) { toast(errText(e), 'err'); }
  };

  if (err) return <ErrorState error={err} onRetry={load} />;
  const items = (list && (list.tickets || list)) || [];

  return (
    <>
      <div className="h1">کنسول تیکت‌ها</div>
      <div className="sub">پاسخ، بستن و بازگشایی — بدون ترک صفحه</div>
      <div className="row" style={{ alignItems: 'flex-end' }}>
        <div className="tabs" style={{ flex: 1, marginBottom: sel.length ? 0 : 14 }}>
          {[['', 'همه'], ['open', 'باز'], ['answered', 'پاسخ‌داده‌شده'], ['closed', 'بسته']].map(([k, v]) => (
            <button key={k} className={`tab ${status === k ? 'on' : ''}`} onClick={() => setStatus(k)}>{v}</button>
          ))}
        </div>
        {sel.length > 0 && (
          <div className="row" style={{ marginBottom: 6 }}>
            <span className="badge acc">{sel.length} انتخاب‌شده</span>
            <button className="btn sm ok" onClick={() => bulk('close')}>✅ بستن گروهی</button>
            <button className="btn sm" onClick={() => bulk('reopen')}>🔓 بازگشایی</button>
          </div>
        )}
      </div>
      <div className="grid" style={{ gridTemplateColumns: '300px 1fr', alignItems: 'start' }}>
        <div className="panel" style={{ maxHeight: '70vh', overflowY: 'auto' }}>
          {!list && <div className="panel-pad"><Loading /></div>}
          {list && !items.length && <Empty icon="🎫" text="تیکتی نیست" />}
          {items.map(t => (
            <div key={t.id || t.tid} className={`tree-row ${cur === (t.id || t.tid) ? 'on' : ''}`}
                 style={{ cursor: 'pointer', borderBottom: '1px solid var(--line)',
                          background: cur === (t.id || t.tid) ? 'var(--panel2)' : '' }}
                 onClick={() => open(t)}>
              <input type="checkbox" checked={sel.includes(t.id || t.tid)}
                     onClick={e => e.stopPropagation()}
                     onChange={() => setSel(x => x.includes(t.id || t.tid)
                       ? x.filter(i => i !== (t.id || t.tid)) : [...x, t.id || t.tid])} />
              <span>🎫</span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ color: 'var(--txt)', fontSize: 12.5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {t.subject || t.title || `تیکت ${t.id || t.tid}`}
                </div>
                <div className="muted">{t.user_name || t.name || ''}</div>
              </div>
              <B kind={t.status === 'open' ? 'bad' : t.status === 'answered' ? 'warn' : 'ok'}>
                {t.status === 'open' ? 'باز' : t.status === 'answered' ? 'پاسخ' : 'بسته'}
              </B>
            </div>
          ))}
        </div>
        <div className="panel" style={{ minHeight: '60vh', display: 'flex', flexDirection: 'column' }}>
          {!cur && <Empty icon="💬" text="یک تیکت را انتخاب کنید" />}
          {cur && !detail && <div className="panel-pad"><Loading /></div>}
          {detail && (
            <>
              <div className="chat" style={{ flex: 1, overflowY: 'auto', maxHeight: '55vh' }}>
                {(detail.replies || detail.messages || [
                  { by: 'user', text: detail.text || detail.body || detail.subject || '' },
                ]).map((m, i) => (
                  <div key={i} className={`bubble ${(m.by || m.sender) === 'admin' ? 'admin' : 'user'}`}>
                    {m.text || m.message}
                    <div className="muted" style={{ marginTop: 4 }}>{m.at || m.created_at || ''}</div>
                  </div>
                ))}
              </div>
              <div className="panel-pad row" style={{ borderTop: '1px solid var(--line)' }}>
                <input className="inp" style={{ flex: 1 }} placeholder="پاسخ…"
                       value={text} onChange={e => setText(e.target.value)}
                       onKeyDown={e => e.key === 'Enter' && send()} />
                <button className="btn primary" disabled={busy} onClick={send}>ارسال ➤</button>
                {detail.status !== 'closed'
                  ? <button className="btn sm" onClick={() => act(api.ticketClose)}>✅ بستن</button>
                  : <button className="btn sm" onClick={() => act(api.ticketReopen)}>🔓 بازگشایی</button>}
              </div>
            </>
          )}
        </div>
      </div>
    </>
  );
}
