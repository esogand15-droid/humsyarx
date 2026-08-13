import React, { useEffect, useMemo, useState } from 'react';
import { api, errText } from '../api.js';
import { Loading, ErrorState, B, toast, NoPerm, Empty, Confirm } from '../ui.jsx';

const fa = (n) => Number(n ?? 0).toLocaleString('fa-IR');
const STEPS = [
  ['مخاطب', '🎯'],
  ['محتوا', '✍️'],
  ['پیش‌نمایش', '👁'],
  ['زمان‌بندی', '🗓'],
  ['تأیید و ارسال', '📢'],
];

// 🔔📢 جادوگر ارسال همگانی (موج Broadcast-Wizard) — ۵ گام کامل:
// مخاطب ← محتوا ← پیش‌نمایش ← زمان‌بندی (فوری/زمان‌دار) ← تأیید ← ارسال.
// بک‌اند: همان /api/admin/broadcast* سطح مالک (آیینه‌ی دقیق payload مینی‌اپ).
// ⚠️ هیچ endpoint سطح مالک آزاد نشده — فقط UX کامل‌تر شده است.
export default function Notify() {
  const [step, setStep] = useState(1);
  const [scope, setScope] = useState('all');
  const [intakes, setIntakes] = useState([]);
  const [intake, setIntake] = useState('');
  const [group, setGroup] = useState('1');
  const [text, setText] = useState('');
  const [count, setCount] = useState(null);
  const [mode, setMode] = useState('now');           // now | later
  const [sendAt, setSendAt] = useState('');
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(null);            // {queued, scheduled}
  const [history, setHistory] = useState(null);
  const [runs, setRuns] = useState(null);
  const [sched, setSched] = useState(null);          // 🌊 ارسال‌های زمان‌دار در انتظار
  const [cancelOf, setCancelOf] = useState(null);
  const [denied, setDenied] = useState(false);       // سطح مالک

  useEffect(() => {
    api.intakes().then(r => setIntakes(r.intakes || [])).catch(() => {});
    loadHist(); loadRuns(); loadSched();
  }, []);
  const loadSched = async () => {
    try { setSched((await api.broadcastScheduled()).scheduled || []); }
    catch { setSched([]); }
  };
  const cancelBatch = async () => {
    const it = cancelOf;
    setCancelOf(null);
    try {
      const r = await api.broadcastCancel(it.text, it.created_at);
      toast(`ارسال زمان‌دار برای ${fa(r.cancelled)} گیرنده لغو شد 🗑`);
      loadSched(); loadHist();
    } catch (e) { toast(errText(e), 'err'); loadSched(); }
  };
  const loadHist = async () => {
    try { setHistory((await api.broadcastHistory()).history || []); }
    catch (e) {
      if (e.status === 403) { setDenied(true); setHistory([]); }
      else setHistory([]);
    }
  };
  const loadRuns = async () => {
    try { setRuns((await api.notifRuns()).runs || []); } catch { setRuns([]); }
  };
  const retry = async (id) => {
    try {
      const r = await api.notifRetry(id);
      toast(`${fa(r.requeued)} گیرنده دوباره در صف قرار گرفت 🔁`);
      loadRuns();
    } catch (e) { toast(errText(e), 'err'); }
  };

  const intakeLabel = (code) => intakes.find(i => (i.code || i) === code)?.label
    || intakes.find(i => (i.code || i) === code)?.code || code;
  const target = useMemo(() => {
    const t = { scope };
    if (scope !== 'all') t.intake = intake;
    if (scope === 'intake_group') t.group = group;
    return t;
  }, [scope, intake, group]);
  const audienceLabel = useMemo(() => {
    if (scope === 'all') return 'همه‌ی کاربران تأییدشده';
    if (scope === 'intake') return `ورودی «${intakeLabel(intake)}»`;
    return `ورودی «${intakeLabel(intake)}» — گروه ${fa(group)}`;
  }, [scope, intake, group, intakes]);

  const preview = async () => {
    setBusy(true);
    try {
      const r = await api.broadcastPreview({ target });
      setCount(r.recipient_count);
      setStep(3);
      if (!r.recipient_count) toast('برای این مخاطب، گیرنده‌ای یافت نشد ⚠️', 'err');
    } catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };

  const send = async () => {
    setBusy(true);
    try {
      const body = { text: text.trim(), target, send_at: null };
      if (mode === 'later') body.send_at = new Date(sendAt).toISOString();
      const r = await api.broadcast(body);
      setSent({ queued: r.queued || 0, scheduled: !!r.scheduled });
      loadHist(); loadSched();
    } catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };
  const reset = () => {
    setStep(1); setScope('all'); setIntake(''); setGroup('1'); setText('');
    setCount(null); setMode('now'); setSendAt(''); setSent(null);
  };

  const minAt = useMemo(() => {
    const d = new Date(Date.now() + 5 * 60000);
    d.setSeconds(0, 0);
    return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  }, [step]);
  const sendAtFa = useMemo(() => {
    if (!sendAt) return '';
    try { return new Date(sendAt).toLocaleString('fa-IR', { dateStyle: 'full', timeStyle: 'short' }); }
    catch { return sendAt; }
  }, [sendAt]);

  const canNext1 = scope === 'all' || !!intake;
  const canPreview = text.trim().length >= 5 && !busy;
  const canConfirm = mode === 'now' || (!!sendAt && new Date(sendAt).getTime() > Date.now());

  return (
    <div className="grid" style={{ gridTemplateColumns: 'minmax(340px,460px) 1fr', alignItems: 'start' }}>
      {/* ═══ جادوگر ═══ */}
      <div className="panel panel-pad">
        <div className="h1" style={{ fontSize: 16 }}>📢 جادوگر ارسال همگانی</div>
        <div className="sub">از مسیر صف outbox ربات · ثبت در تاریخچه و مرکز اعلان مینی‌اپ</div>

        {denied ? (
          <NoPerm text="ارسال همگانی فقط برای مالک سامانه است" />
        ) : sent ? (
          <div className="grid" style={{ gap: 12, marginTop: 14, textAlign: 'center', padding: '10px 0' }}>
            <div style={{ fontSize: 42 }}>{sent.scheduled ? '🗓' : '✅'}</div>
            <b style={{ fontSize: 15 }}>
              {sent.scheduled ? 'زمان‌بندی و در صف قرار گرفت' : 'ارسال به صف رفت'}
            </b>
            <div><B kind="acc">{fa(sent.queued)} گیرنده</B>{' '}
              <B kind={sent.scheduled ? 'warn' : 'ok'}>{sent.scheduled ? 'زمان‌دار' : 'فوری'}</B></div>
            <p className="muted" style={{ margin: 0 }}>
              {sent.scheduled ? `در ${sendAtFa || 'زمان تعیین‌شده'} ارسال می‌شود.` : 'ربات به‌تدریج و امن برای همه می‌فرستد.'}
            </p>
            <div className="row" style={{ justifyContent: 'center' }}>
              <button className="btn primary" onClick={reset}>📢 ارسال جدید</button>
              <button className="btn" onClick={() => { setSent(null); setStep(5); }}>بازبینی آخرین ارسال</button>
            </div>
          </div>
        ) : (
          <>
            {/* ریل گام‌ها */}
            <div className="wiz-steps" style={{ margin: '14px 0 16px' }}>
              {STEPS.map(([label, icon], i) => (
                <div key={label}
                     className={`wiz-step ${step === i + 1 ? 'on' : ''} ${step > i + 1 ? 'done' : ''}`}
                     onClick={() => { if (step > i + 1) setStep(i + 1); }}
                     title={step > i + 1 ? 'بازگشت به این گام' : ''}>
                  <span className="wiz-n">{step > i + 1 ? '✓' : fa(i + 1)}</span>
                  <span className="wiz-l">{icon} {label}</span>
                </div>
              ))}
            </div>

            {step === 1 && (
              <div className="grid" style={{ gap: 10 }}>
                {[
                  ['all', '🌐', 'همه‌ی کاربران تأییدشده', 'هر کاربر فعال سامانه'],
                  ['intake', '🏷', 'یک ورودی خاص', 'مثلاً فقط ورودی بهمن'],
                  ['intake_group', '👥', 'یک ورودی + گروه', 'دقیق‌ترین هدف‌گیری'],
                ].map(([v, icon, title, desc]) => (
                  <label key={v} className={`pick ${scope === v ? 'on' : ''}`}>
                    <input type="radio" checked={scope === v} onChange={() => setScope(v)} />
                    <span style={{ fontSize: 17 }}>{icon}</span>
                    <span style={{ flex: 1 }}>
                      <b style={{ display: 'block', fontSize: 13 }}>{title}</b>
                      <span className="muted" style={{ fontSize: 11 }}>{desc}</span>
                    </span>
                  </label>
                ))}
                {scope !== 'all' && (
                  <select className="inp" value={intake} onChange={e => setIntake(e.target.value)}>
                    <option value="">انتخاب ورودی…</option>
                    {intakes.map(i => <option key={i.code || i} value={i.code || i}>{i.label || i.code || i}</option>)}
                  </select>
                )}
                {scope === 'intake_group' && (
                  <div className="row">
                    {['1', '2'].map(g => (
                      <label key={g} className={`pick ${group === g ? 'on' : ''}`} style={{ flex: 1 }}>
                        <input type="radio" checked={group === g} onChange={() => setGroup(g)} />
                        <b>{g === '1' ? '1️⃣ گروه ۱' : '2️⃣ گروه ۲'}</b>
                      </label>
                    ))}
                  </div>
                )}
                <button className="btn primary" disabled={!canNext1} onClick={() => setStep(2)}>ادامه ←</button>
              </div>
            )}

            {step === 2 && (
              <div className="grid" style={{ gap: 10 }}>
                <div className="row" style={{ alignItems: 'center' }}>
                  <b>متن پیام</b><span className="spacer" />
                  <B kind={audienceLabel.startsWith('همه') ? 'acc' : 'purple'}>🎯 {audienceLabel}</B>
                </div>
                <textarea className="inp" rows={8} placeholder="متن اعلان… (حداقل ۵ نویسه)"
                          value={text} onChange={e => setText(e.target.value)} />
                <div className="row">
                  <span className="muted" style={{ fontSize: 11 }}>
                    {fa(text.trim().length)} نویسه · تگ‌های ساده‌ی HTML مثل &lt;b&gt; در تلگرام نمایش داده می‌شوند
                  </span>
                  <span className="spacer" />
                  {text.trim().length > 0 && text.trim().length < 5 && <B kind="bad">خیلی کوتاه</B>}
                </div>
                <div className="row">
                  <button className="btn" onClick={() => setStep(1)}>→ بازگشت</button>
                  <button className="btn primary" disabled={!canPreview} onClick={preview}>
                    {busy ? '⏳ شمار مخاطبان…' : '👁 پیش‌نمایش مخاطبان'}
                  </button>
                </div>
              </div>
            )}

            {step === 3 && (
              <div className="grid" style={{ gap: 10 }}>
                <div className="ct3-kv"><span className="muted">مخاطب</span><span>{audienceLabel}</span></div>
                <div className="ct3-kv"><span className="muted">گیرندگان</span>
                  <B kind={count ? 'acc' : 'bad'}>{count == null ? '…' : `${fa(count)} نفر`}</B>
                </div>
                <div className="panel panel-pad" style={{ background: 'var(--bg)' }}>
                  <div className="muted" style={{ fontSize: 11, marginBottom: 6 }}>پیش‌نمایش پیام در گفت‌وگوی کاربر:</div>
                  <div className="bubble user" style={{ maxWidth: '100%', whiteSpace: 'pre-wrap' }}>{text.trim()}</div>
                </div>
                <p className="muted" style={{ fontSize: 11, margin: 0 }}>
                  📱 علاوه بر پیام تلگرام، در «مرکز اعلان» مینی‌اپ هم به‌عنوان اطلاعیه‌ی مدیریت ثبت می‌شود.
                </p>
                <div className="row">
                  <button className="btn" onClick={() => setStep(2)}>→ ویرایش</button>
                  <button className="btn primary" disabled={!count} onClick={() => setStep(4)}>ادامه ←</button>
                </div>
              </div>
            )}

            {step === 4 && (
              <div className="grid" style={{ gap: 10 }}>
                <label className={`pick ${mode === 'now' ? 'on' : ''}`}>
                  <input type="radio" checked={mode === 'now'} onChange={() => setMode('now')} />
                  <span style={{ fontSize: 17 }}>⚡</span>
                  <span style={{ flex: 1 }}>
                    <b style={{ display: 'block', fontSize: 13 }}>ارسال فوری</b>
                    <span className="muted" style={{ fontSize: 11 }}>بلافاصله وارد صف ارسال می‌شود</span>
                  </span>
                </label>
                <label className={`pick ${mode === 'later' ? 'on' : ''}`}>
                  <input type="radio" checked={mode === 'later'} onChange={() => setMode('later')} />
                  <span style={{ fontSize: 17 }}>🗓</span>
                  <span style={{ flex: 1 }}>
                    <b style={{ display: 'block', fontSize: 13 }}>ارسال زمان‌دار</b>
                    <span className="muted" style={{ fontSize: 11 }}>تا زمان مقرر در صف می‌ماند</span>
                  </span>
                </label>
                {mode === 'later' && (
                  <>
                    <input type="datetime-local" className="inp" style={{ direction: 'ltr', textAlign: 'left' }}
                           min={minAt} value={sendAt} onChange={e => setSendAt(e.target.value)} />
                    {sendAt && (
                      <div className="ct3-kv"><span className="muted">زمان ارسال</span>
                        <B kind={new Date(sendAt).getTime() > Date.now() ? 'warn' : 'bad'}>{sendAtFa}</B>
                      </div>
                    )}
                    {sendAt && new Date(sendAt).getTime() <= Date.now() &&
                      <span className="muted" style={{ color: 'var(--c-bad)', fontSize: 11 }}>زمان انتخابی در گذشته است — زمان آینده برگزینید.</span>}
                  </>
                )}
                <div className="row">
                  <button className="btn" onClick={() => setStep(3)}>→ بازگشت</button>
                  <button className="btn primary" disabled={!canConfirm} onClick={() => setStep(5)}>ادامه ←</button>
                </div>
              </div>
            )}

            {step === 5 && (
              <div className="grid" style={{ gap: 10 }}>
                <div className="ct3-kv"><span className="muted">مخاطب</span><span>{audienceLabel} — <B kind="acc">{fa(count)} نفر</B></span></div>
                <div className="ct3-kv"><span className="muted">زمان</span>
                  {mode === 'now' ? <B kind="ok">⚡ فوری</B> : <B kind="warn">🗓 {sendAtFa}</B>}
                </div>
                <div className="panel panel-pad" style={{ background: 'var(--bg)', fontSize: 12.5, color: 'var(--txt2)', whiteSpace: 'pre-wrap', maxHeight: 120, overflowY: 'auto' }}>
                  {text.trim()}
                </div>
                <p className="muted" style={{ fontSize: 11, margin: 0 }}>
                  ⚠️ این عمل در تاریخچه و حسابرسی (severity: HIGH) ثبت می‌شود و قابل بازگشت نیست.
                </p>
                <div className="row">
                  <button className="btn" onClick={() => setStep(4)}>→ بازگشت</button>
                  <button className="btn danger" style={{ flex: 1 }} disabled={busy} onClick={send}>
                    {busy ? '⏳ در حال ثبت در صف…' : `📢 ارسال قطعی به ${fa(count)} نفر`}
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* ═══ ستون کناری: زمان‌دارها + تاریخچه + اجراها ═══ */}
      <div className="grid" style={{ gap: 14, alignContent: 'start' }}>
        {/* 🌊 موج Notif-Scheduled — ارسال‌های زمان‌دار در انتظار + لغو */}
        {!denied && sched !== null && (
          <div className="panel panel-pad">
            <div className="row"><b>🗓 ارسال‌های زمان‌دار در انتظار</b><span className="spacer" />
              <B kind={sched.length ? 'warn' : 'ok'}>{fa(sched.length)}</B>
              <button className="btn sm" onClick={loadSched}>🔄</button></div>
            {sched.length === 0 ? (
              <p className="muted" style={{ marginTop: 8 }}>ارسال زمان‌داری در صف نیست.</p>
            ) : (
              <div className="grid" style={{ gap: 8, marginTop: 10 }}>
                {sched.map((it, i) => (
                  <div key={i} className="panel panel-pad" style={{ background: 'var(--bg)' }}>
                    <div className="row" style={{ flexWrap: 'wrap', gap: 5 }}>
                      <B kind="warn">🗓 {(it.send_at || '').slice(0, 16).replace('T', ' ')}</B>
                      <B kind="acc">{fa(it.total)} گیرنده</B>
                      <span className="spacer" />
                      <button className="btn sm danger" onClick={() => setCancelOf(it)}>🗑 لغو ارسال</button>
                    </div>
                    <div style={{ marginTop: 6, fontSize: 12.5, color: 'var(--txt2)' }}>{it.text}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="panel panel-pad">
          <div className="row"><b>تاریخچه‌ی ارسال‌های همگانی</b><span className="spacer" />
            <button className="btn sm" onClick={loadHist}>🔄</button></div>
          {!history ? <Loading rows={3} /> : !history.length ? (
            <Empty icon="📭" text="ارسالی ثبت نشده است" />
          ) : (
            <div className="grid" style={{ gap: 8, marginTop: 10 }}>
              {history.map((h, i) => {
                const pending = Math.max(0, (h.total || 0) - (h.sent || 0) - (h.failed || 0));
                const pct = h.total ? Math.round((h.sent / h.total) * 100) : 0;
                return (
                  <div key={i} className="panel panel-pad" style={{ background: 'var(--bg)' }}>
                    <div className="row" style={{ flexWrap: 'wrap', gap: 5 }}>
                      <B kind="acc">{fa(h.total)} نفر</B>
                      <B kind="ok">✔ {fa(h.sent)}</B>
                      {h.failed > 0 && <B kind="bad">✖ {fa(h.failed)}</B>}
                      {pending > 0 && <B kind="warn">⏳ {fa(pending)}</B>}
                      <span className="spacer" />
                      <span className="muted">{(h.created_at || '').slice(0, 16).replace('T', ' ')}</span>
                    </div>
                    <div className="minibar-track" style={{ marginTop: 7 }}>
                      <div className="minibar-fill" style={{ width: `${pct}%` }} />
                    </div>
                    <div style={{ marginTop: 6, fontSize: 12.5, color: 'var(--txt2)' }}>
                      {(h.text || '').slice(0, 120)}{(h.text || '').length > 120 ? '…' : ''}
                    </div>
                  </div>
                );
              })}
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
                  <span className="muted">✔{fa(r.sent)} · ✖{fa(r.failed)} · {fa(r.total)}</span>
                  <span className="spacer" />
                  <span className="muted">{r.started_at}</span>
                  {r.failed > 0 && <button className="btn sm" onClick={() => retry(r.id)}>🔁 تلاش مجدد</button>}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {cancelOf && (
        <Confirm danger
                 text={`لغو ارسال زمان‌دار برای ${fa(cancelOf.total)} گیرنده؟ پیام‌ها از صف حذف می‌شوند و این عمل در حسابرسی (HIGH) ثبت می‌شود.`}
                 onYes={cancelBatch}
                 onNo={() => setCancelOf(null)} />
      )}
    </div>
  );
}
