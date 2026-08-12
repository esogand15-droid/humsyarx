import React, { useEffect, useState } from 'react';
import { api, errText } from '../api.js';
import { Loading, ErrorState, B, toast } from '../ui.jsx';

// 🔔 اعلان همگانی — چندمرحله‌ای: مخاطب → متن → پیش‌نمایش → تأیید → ارسال
export default function Notify() {
  const [step, setStep] = useState(1);
  const [scope, setScope] = useState('all');
  const [intakes, setIntakes] = useState([]);
  const [intake, setIntake] = useState('');
  const [text, setText] = useState('');
  const [count, setCount] = useState(null);
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState(null);
  const [runs, setRuns] = useState(null);
  const [err, setErr] = useState('');

  useEffect(() => {
    api.intakes().then(r => setIntakes(r.intakes || [])).catch(() => {});
    loadHist(); loadRuns();
  }, []);
  const loadHist = async () => {
    try { setHistory((await api.broadcastHistory()).broadcasts || []); } catch { setHistory([]); }
  };
  const loadRuns = async () => {
    try { setRuns((await api.notifRuns()).runs || []); } catch { setRuns([]); }
  };
  const retry = async (id) => {
    try {
      const r = await api.notifRetry(id);
      toast(`${r.requeued} گیرنده دوباره در صف قرار گرفت 🔁`);
      loadRuns();
    } catch (e) { toast(errText(e), 'err'); }
  };

  const preview = async () => {
    if (scope === 'all') { setCount(null); setStep(3); return; }
    setBusy(true);
    try {
      const r = await api.broadcastPreview({ target: { scope, intake: intake || undefined } });
      setCount(r.recipient_count); setStep(3);
    } catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };
  const send = async () => {
    setBusy(true);
    try {
      const r = await api.broadcast({ text, target: { scope, intake: intake || undefined } });
      toast(`ارسال به صف شد (${Number(r.recipient_count || r.queued || 0).toLocaleString('fa')} نفر)`);
      setStep(1); setText(''); setScope('all'); setIntake('');
      loadHist();
    } catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };

  return (
    <div className="grid" style={{ gridTemplateColumns: 'minmax(320px,440px) 1fr', alignItems: 'start' }}>
      <div className="panel panel-pad">
        <div className="h1" style={{ fontSize: 16 }}>ارسال همگانی</div>
        <div className="sub">گام {step} از ۴</div>

        {step === 1 && (
          <div className="grid" style={{ gap: 10 }}>
            <b>۱) مخاطب</b>
            <label className="row"><input type="radio" checked={scope === 'all'} onChange={() => setScope('all')} /> همه‌ی کاربران تأییدشده</label>
            <label className="row"><input type="radio" checked={scope === 'intake'} onChange={() => setScope('intake')} /> ورودی خاص</label>
            {scope === 'intake' && (
              <select className="inp" value={intake} onChange={e => setIntake(e.target.value)}>
                <option value="">انتخاب ورودی…</option>
                {intakes.map(i => <option key={i.code || i} value={i.code || i}>{i.label || i.code || i}</option>)}
              </select>
            )}
            <button className="btn primary" disabled={scope === 'intake' && !intake} onClick={() => setStep(2)}>ادامه ←</button>
          </div>
        )}
        {step === 2 && (
          <div className="grid" style={{ gap: 10 }}>
            <b>۲) متن پیام</b>
            <textarea className="inp" rows={6} placeholder="متن اعلان…" value={text}
                      onChange={e => setText(e.target.value)} />
            <div className="row">
              <button className="btn" onClick={() => setStep(1)}>→ بازگشت</button>
              <button className="btn primary" disabled={!text.trim() || busy} onClick={preview}>
                {busy ? '…' : 'پیش‌نمایش مخاطبان'}
              </button>
            </div>
          </div>
        )}
        {step === 3 && (
          <div className="grid" style={{ gap: 10 }}>
            <b>۳) پیش‌نمایش</b>
            <div className="panel panel-pad" style={{ background: 'var(--bg)' }}>
              <div className="bubble user">{text}</div>
            </div>
            {count != null && <B kind="acc">{Number(count).toLocaleString('fa')} دریافت‌کننده</B>}
            <div className="row">
              <button className="btn" onClick={() => setStep(2)}>→ ویرایش</button>
              <button className="btn primary" onClick={() => setStep(4)}>ادامه ←</button>
            </div>
          </div>
        )}
        {step === 4 && (
          <div className="grid" style={{ gap: 10 }}>
            <b>۴) تأیید نهایی</b>
            <p className="muted">پیام از طریق صف outbox ربات ارسال می‌شود و در تاریخچه ثبت خواهد شد.</p>
            <div className="row">
              <button className="btn" onClick={() => setStep(3)}>→ بازگشت</button>
              <button className="btn danger" disabled={busy} onClick={send}>
                {busy ? '…' : '📢 ارسال قطعی'}
              </button>
            </div>
          </div>
        )}
      </div>

      <div className="grid" style={{ gap: 14, alignContent: 'start' }}>
        <div className="panel panel-pad">
          <b>تاریخچه‌ی ارسال‌های همگانی</b>
          {!history ? <Loading rows={3} /> : !history.length ? <p className="muted" style={{ marginTop: 10 }}>موردی نیست</p> : (
            <div className="grid" style={{ gap: 8, marginTop: 10 }}>
              {history.map((h, i) => (
                <div key={i} className="panel panel-pad" style={{ background: 'var(--bg)' }}>
                  <div className="row">
                    <B kind="acc">{Number(h.recipients || h.total || 0).toLocaleString('fa')} نفر</B>
                    <span className="muted">{(h.created_at || h.at || '').slice(0, 16).replace('T', ' ')}</span>
                  </div>
                  <div style={{ marginTop: 6, fontSize: 12.5, color: 'var(--txt2)' }}>
                    {(h.text || '').slice(0, 120)}{(h.text || '').length > 120 ? '…' : ''}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 🌊 WA2.7 — اجراهای جاب‌های اعلان + تلاش مجدد */}
        <div className="panel panel-pad">
          <div className="row"><b>🔔 اجراهای اخیر اعلان‌ها</b><span className="spacer" />
            <button className="btn sm" onClick={loadRuns}>🔄</button></div>
          {!runs ? <Loading rows={3} /> : !runs.length ? <p className="muted" style={{ marginTop: 10 }}>اجلاسی ثبت نشده — یا مجوز notifications.manage ندارید</p> : (
            <div className="grid" style={{ gap: 6, marginTop: 10 }}>
              {runs.map(r => (
                <div key={r.id} className="row" style={{ padding: '7px 0', borderBottom: '1px solid var(--line)' }}>
                  <B kind={r.status === 'done' || r.status === 'finished' ? 'ok' : r.failed > 0 ? 'warn' : 'acc'}>{r.status || '—'}</B>
                  <span style={{ minWidth: 130 }}>{r.job_name}</span>
                  <span className="muted">✔{r.sent} · ✖{r.failed} · {r.total}</span>
                  <span className="spacer" />
                  <span className="muted">{r.started_at}</span>
                  {r.failed > 0 && <button className="btn sm" onClick={() => retry(r.id)}>🔁 تلاش مجدد</button>}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
