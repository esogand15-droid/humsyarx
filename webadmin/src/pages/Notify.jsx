import React, { useEffect, useMemo, useState } from 'react';
import { api, errText } from '../api.js';
import { Loading, ErrorState, B, PageHeader, toast, NoPerm, Empty, Confirm, Switch, Modal } from '../ui.jsx';

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
  const [auxErr, setAuxErr] = useState('');
  const [segments, setSegments] = useState([]);
  const [drafts, setDrafts] = useState([]);
  const [saveOpen, setSaveOpen] = useState(null); // segment | draft
  const [saveName, setSaveName] = useState('');
  const [denied, setDenied] = useState(false);       // سطح مالک

  useEffect(() => {
    api.waIntakes().then(r => setIntakes(r.intakes || [])).catch(() => {});
    loadHist(); loadRuns(); loadSched(); loadSaved();
  }, []);
  const loadSaved = async () => {
    try {
      const [s, d] = await Promise.all([api.savedFilters('broadcast_segment'), api.savedFilters('broadcast_draft')]);
      setSegments(s.filters || []); setDrafts(d.filters || []);
    } catch { setSegments([]); setDrafts([]); }
  };
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
    try { setRuns((await api.notifRuns()).runs || []); }
    catch (e) { if (e.status !== 403) setAuxErr(errText(e)); setRuns([]); }
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
  const saveCurrent = async () => {
    if (!saveName.trim() || !saveOpen) return;
    const isDraft = saveOpen === 'draft';
    try {
      await api.saveFilter({ name: saveName.trim(), scope: isDraft ? 'broadcast_draft' : 'broadcast_segment',
        filters: isDraft ? { scope, intake, group, text, mode, sendAt } : { scope, intake, group } });
      toast(isDraft ? 'پیش‌نویس ذخیره شد' : 'Segment مخاطبان ذخیره شد');
      setSaveOpen(null); setSaveName(''); loadSaved();
    } catch (e) { toast(errText(e), 'err'); }
  };
  const applySaved = (item, isDraft = false) => {
    const f = item.filters || {};
    setScope(f.scope || 'all'); setIntake(f.intake || ''); setGroup(f.group || '1');
    if (isDraft) { setText(f.text || ''); setMode(f.mode || 'now'); setSendAt(f.sendAt || ''); }
    setCount(null); setSent(null); setStep(isDraft && f.text ? 2 : 1);
    toast(`«${item.name}» بارگذاری شد`);
  };
  const removeSaved = async (item) => {
    try { await api.delFilter(item.id); loadSaved(); }
    catch (e) { toast(errText(e), 'err'); }
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
    <>
      <PageHeader title="مرکز اعلان‌ها و ارسال همگانی" description="طراحی، پیش‌نمایش، زمان‌بندی، ارسال و پایش اعلان‌ها"
        actions={<><button className="btn" onClick={() => { setSaveName(''); setSaveOpen('segment'); }}>💾 ذخیره Segment</button>
          <button className="btn" disabled={!text.trim()} onClick={() => { setSaveName(''); setSaveOpen('draft'); }}>📝 ذخیره پیش‌نویس</button></>} />
      {auxErr && <div className="panel panel-pad" style={{ marginBottom: 12 }}><ErrorState title="بخشی از داده‌های اعلان بارگذاری نشد" error={auxErr} onRetry={() => { setAuxErr(''); loadHist(); loadRuns(); loadSched(); }} /></div>}
      <div className="notify-layout">
      {/* ═══ جادوگر ═══ */}
      <div className="panel panel-pad">
        <div className="h1" style={{ fontSize: 16 }}>📢 جادوگر ارسال همگانی</div>
        <div className="sub">از مسیر صف outbox ربات · ثبت در تاریخچه و مرکز اعلان مینی‌اپ</div>

        {denied ? (
          <NoPerm text="ارسال همگانی نیازمند مجوز broadcast.send است" />
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
        {(segments.length > 0 || drafts.length > 0) && <div className="panel panel-pad">
          <b>نماهای ذخیره‌شده</b>
          {!!segments.length && <div style={{ marginTop: 8 }}><div className="muted">Segmentهای مخاطبان</div>
            <div className="row" style={{ marginTop: 5 }}>{segments.map(s => <span className="chip" key={s.id}>
              <a onClick={() => applySaved(s)}>{s.name}</a><button className="chip-x" aria-label={`حذف Segment ${s.name}`} onClick={() => removeSaved(s)}>✕</button>
            </span>)}</div></div>}
          {!!drafts.length && <div style={{ marginTop: 8 }}><div className="muted">پیش‌نویس‌ها</div>
            <div className="grid" style={{ gap: 5, marginTop: 5 }}>{drafts.map(d => <div className="row" key={d.id}>
              <button className="btn sm" style={{ flex: 1, textAlign: 'right' }} onClick={() => applySaved(d, true)}>📝 {d.name}</button>
              <button className="btn sm danger" aria-label={`حذف پیش‌نویس ${d.name}`} onClick={() => removeSaved(d)}>🗑</button>
            </div>)}</div></div>}
        </div>}
        {/* 🌊 موج Notif-Scheduled — ارسال‌های زمان‌دار در انتظار + لغو */}
        {!denied && sched !== null && (
          <div className="panel panel-pad">
            <div className="row"><b>🗓 ارسال‌های زمان‌دار در انتظار</b><span className="spacer" />
              <B kind={sched.length ? 'warn' : 'ok'}>{fa(sched.length)}</B>
              <button className="btn sm" onClick={loadSched} aria-label="تازه‌سازی ارسال‌های زمان‌دار">🔄</button></div>
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
            <button className="btn sm" onClick={loadHist} aria-label="تازه‌سازی تاریخچه ارسال‌ها">🔄</button></div>
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
                      <button className="btn sm" onClick={() => { reset(); setText(h.text || ''); setStep(2); }}>📄 استفاده مجدد</button>
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

        {/* 🌊 موج Poll-Notif — نظرسنجی کانال + فاصله‌ی اعلان منابع (سطح مالک) */}
        <PollPanel />
        <NotifIntervalPanel />

        {/* 🌊 WA2.7 — اجراهای جاب‌های اعلان + تلاش مجدد */}
        <div className="panel panel-pad">
          <div className="row"><b>🔔 اجراهای اخیر اعلان‌ها</b><span className="spacer" />
            <button className="btn sm" onClick={loadRuns} aria-label="تازه‌سازی اجراهای اعلان‌ها">🔄</button></div>
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

      {saveOpen && <Modal title={saveOpen === 'draft' ? 'ذخیره پیش‌نویس ارسال' : 'ذخیره Segment مخاطبان'} onClose={() => setSaveOpen(null)}>
        <p className="muted" style={{ marginBottom: 8 }}>{saveOpen === 'draft' ? 'مخاطب، متن و زمان‌بندی فعلی ذخیره می‌شود.' : `مخاطب فعلی: ${audienceLabel}`}</p>
        <input className="inp" style={{ width: '100%' }} placeholder="نام قابل تشخیص…" value={saveName} onChange={e => setSaveName(e.target.value)} />
        <div className="row" style={{ marginTop: 12 }}><button className="btn primary" disabled={!saveName.trim()} onClick={saveCurrent}>ذخیره</button>
          <button className="btn" onClick={() => setSaveOpen(null)}>انصراف</button></div>
      </Modal>}
      {cancelOf && (
        <Confirm danger
                 text={`لغو ارسال زمان‌دار برای ${fa(cancelOf.total)} گیرنده؟ پیام‌ها از صف حذف می‌شوند و این عمل در حسابرسی (HIGH) ثبت می‌شود.`}
                 onYes={cancelBatch}
                 onNo={() => setCancelOf(null)} />
      )}
      </div>
    </>
  );
}

/* ── 📊🌊 پنل نظرسنجی کانال (موج Poll-Notif) — همان admin:poll_main ربات ── */
export function PollPanel() {
  const [st, setSt] = useState(null);               // {channel_id, configured}
  const [editing, setEditing] = useState(false);
  const [ch, setCh] = useState('');
  const [q, setQ] = useState('');
  const [opts, setOpts] = useState(['', '']);
  const [anon, setAnon] = useState(false);
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const load = async () => {
    try { const r = await api.pollStatus(); setSt(r); setCh(r.channel_id || ''); }
    catch { setSt(null); }
  };
  useEffect(() => { load(); }, []);
  if (!st) return null;
  const saveCh = async () => {
    setBusy(true);
    try { await api.pollSetChannel(ch.trim()); toast('کانال نظرسنجی ذخیره شد 📊'); setEditing(false); load(); }
    catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };
  const validOpts = opts.map(o => o.trim()).filter(Boolean);
  const send = async () => {
    setConfirm(false); setBusy(true);
    try {
      await api.pollCreate(q.trim(), validOpts, anon);
      toast('نظرسنجی در کانال منتشر شد 🗳'); setQ(''); setOpts(['', '']); setAnon(false);
    } catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };
  return (
    <div className="panel panel-pad">
      <div className="row"><b>📊 نظرسنجی کانال</b><span className="spacer" />
        {st.configured
          ? <B kind="ok">کانال: <span className="code">{st.channel_id}</span></B>
          : <B kind="warn">کانال تنظیم نشده</B>}
        <button className="btn sm" onClick={() => setEditing(e => !e)}>{editing ? 'انصراف' : '✏️ تغییر کانال'}</button>
      </div>
      {editing && (
        <div className="row" style={{ marginTop: 10, gap: 6 }}>
          <input className="inp" style={{ flex: 1 }} dir="ltr" placeholder="@channel یا -100…"
                 value={ch} onChange={e => setCh(e.target.value)} />
          <button className="btn primary sm" disabled={busy || !ch.trim()} onClick={saveCh}>{busy ? '⏳' : 'ذخیره'}</button>
        </div>
      )}
      {st.configured && !editing && (<>
        <input className="inp" style={{ width: '100%', marginTop: 10 }} placeholder="سؤال نظرسنجی…"
               value={q} onChange={e => setQ(e.target.value)} maxLength={300} />
        <div className="grid" style={{ gap: 6, marginTop: 8 }}>
          {opts.map((o, i) => (
            <div key={i} className="row" style={{ gap: 6 }}>
              <input className="inp" style={{ flex: 1 }} placeholder={`گزینه‌ی ${fa(i + 1)}`} maxLength={100}
                     value={o}
                     onChange={e => setOpts(s => s.map((x, j) => j === i ? e.target.value : x))} />
              {opts.length > 2 && (
                <button className="btn sm danger" title="حذف گزینه" aria-label="حذف گزینه"
                        onClick={() => setOpts(s => s.filter((_, j) => j !== i))}>🗑</button>
              )}
            </div>
          ))}
        </div>
        <div className="row" style={{ marginTop: 8, flexWrap: 'wrap', gap: 8 }}>
          <button className="btn sm" disabled={opts.length >= 10}
                  onClick={() => setOpts(s => [...s, ''])}>➕ گزینه</button>
          <label className="row" style={{ gap: 6 }}>
            <Switch on={anon} onChange={setAnon} /><span className="muted">ناشناس</span>
          </label>
          <span className="spacer" />
          <button className="btn primary sm" disabled={busy || q.trim().length < 3 || validOpts.length < 2}
                  onClick={() => setConfirm(true)}>{busy ? '⏳' : '🗳 انتشار در کانال'}</button>
        </div>
      </>)}
      {confirm && (
        <Confirm text={`انتشار نظرسنجی «${q.trim().slice(0, 60)}» با ${fa(validOpts.length)} گزینه در کانال؟ (بلافاصله ارسال می‌شود)`}
                 onYes={send} onNo={() => setConfirm(false)} />
      )}
    </div>
  );
}

/* ── ⏱🌊 پنل فاصله‌ی اعلان منابع (موج Poll-Notif) — همان admin:notif_manage ربات ── */
export function NotifIntervalPanel() {
  const [st, setSt] = useState(null);
  const [hours, setHours] = useState(24);
  const [busy, setBusy] = useState(false);
  const load = async () => {
    try { const r = await api.notifSettings(); setSt(r); setHours(r.interval_hours ?? 24); }
    catch { setSt(null); }
  };
  useEffect(() => { load(); }, []);
  if (!st) return null;
  const save = async () => {
    setBusy(true);
    try { await api.notifSetInterval(Number(hours)); toast('فاصله‌ی اعلان ذخیره شد ⏱'); load(); }
    catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };
  return (
    <div className="panel panel-pad">
      <b>⏱ اعلان خودکار منابع جدید</b>
      <div className="row" style={{ marginTop: 10, gap: 6 }}>
        <span className="muted">هر</span>
        {[24, 48, 72].map(h => (
          <button key={h} className={`btn sm ${Number(hours) === h ? 'primary' : ''}`}
                  onClick={() => setHours(h)}>{fa(h)} ساعت</button>
        ))}
        <button className="btn primary sm" disabled={busy}
                onClick={save}>{busy ? '⏳' : 'ذخیره'}</button>
      </div>
      <div className="muted" style={{ marginTop: 8 }}>
        🕐 آخرین ارسال: <span className="code">{(st.last_sent || '—').slice(0, 16).replace('T', ' ') || '—'}</span>
      </div>
      {st.last_error && (
        <div className="badge bad" style={{ marginTop: 6 }} title={st.last_error}>
          خطای آخرین اجرا: {st.last_error.slice(0, 60)}…
        </div>
      )}
    </div>
  );
}
