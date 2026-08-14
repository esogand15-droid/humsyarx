import React, { useEffect, useState } from 'react';
import { api, errText } from '../api.js';
import { Loading, ErrorState, Empty, B, FilterBar, PageHeader, toast, NoPerm } from '../ui.jsx';

// 🎫🌊 W-Admin — Support Command Center سه‌ستونه: صف | گفت‌وگو | کانتکست کاربر
// (اصلاح باگ: فیلد پاسخ = message — قبلاً text می‌رفت و 422 می‌شد؛ حباب support راست‌چین شد)
export default function Tickets({ go, me }) {
  const [status, setStatus] = useState('open');
  const [list, setList] = useState(null);
  const [err, setErr] = useState('');
  const [denied, setDenied] = useState(false);
  const [cur, setCur] = useState(null);
  const [detail, setDetail] = useState(null);
  const [ctx, setCtx] = useState(null);          // user360-lite برای کانتکست
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [sel, setSel] = useState([]);
  const [q, setQ] = useState('');
  const canManage = !!me?.is_owner || (me?.perms || []).includes('tickets.manage');
  const canReply = !!me?.is_owner || (me?.perms || []).includes('tickets.reply');

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
    catch (e) { if (e.status === 403) setDenied(true); else setErr(errText(e)); }
  };
  useEffect(() => { load(); }, [status]);

  const open = async (t) => {
    const id = t.id ?? t.tid;
    setCur(id); setDetail(null); setCtx(null);
    try {
      const d = (await api.ticket(id)).ticket;
      setDetail(d);
      // کانتکست غنی: user360 موجود (users.view) — ضدخطا، اختیاری
      if (d.user?.id) api.user360(d.user.id).then(x => setCtx(x)).catch(() => {});
    } catch (e) { toast(errText(e), 'err'); }
  };
  const send = async () => {
    if (!text.trim()) return;
    setBusy(true);
    try { await api.ticketReply(cur, text.trim()); setText(''); open({ id: cur }); load(); }
    catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };
  const act = async (fn, okMsg) => {
    try { await fn(cur); open({ id: cur }); load(); toast(okMsg); }
    catch (e) { toast(errText(e), 'err'); }
  };

  if (denied) return <NoPerm text="این بخش نیازمند tickets.reply یا tickets.manage است" />;
  if (err) return <ErrorState title="بارگذاری تیکت‌ها ناموفق بود" error={err} onRetry={load} />;
  const raw = (list && (list.tickets || list)) || [];
  const items = q.trim()
    ? raw.filter(t => (t.subject || '').includes(q.trim()) || (t.user_name || '').includes(q.trim()))
    : raw;

  return (
    <>
      <PageHeader title="کنسول پشتیبانی" description="صف، گفت‌وگو و کانتکست کاربر بدون ترک صفحه"
        actions={canManage && sel.length > 0 ? <><B kind="acc">{sel.length} انتخاب‌شده</B>
          <button className="btn sm ok" onClick={() => bulk('close')}>✅ بستن گروهی</button>
          <button className="btn sm" onClick={() => bulk('reopen')}>🔓 بازگشایی</button></> : null} />

      <FilterBar>
        <div className="tabs" style={{ flex: 1, marginBottom: 0 }} role="tablist" aria-label="وضعیت تیکت‌ها">
          {[['open', '🟠 باز'], ['answered', '🟡 پاسخ‌داده‌شده'], ['closed', '🟢 بسته'], ['', 'همه']].map(([k, v]) => (
            <button key={k} type="button" role="tab" aria-selected={status === k} className={`tab ${status === k ? 'on' : ''}`} onClick={() => setStatus(k)}>{v}</button>
          ))}
        </div>
        <input className="inp" style={{ width: 220 }} placeholder="🔎 موضوع/نام…"
               value={q} onChange={e => setQ(e.target.value)} />
      </FilterBar>

      <div className="tk-grid">
        {/* ستون ۱ — صف */}
        <div className="panel" style={{ maxHeight: '74vh', overflowY: 'auto' }}>
          {!list && <div className="panel-pad"><Loading /></div>}
          {list && !items.length && <Empty icon="🎫" text="تیکتی در این صف نیست" />}
          {items.map(t => {
            const id = t.id ?? t.tid;
            return (
              <div key={id} className={`tree-row ${cur === id ? 'on' : ''}`} role="button" tabIndex={0}
                   style={{ cursor: 'pointer', borderBottom: '1px solid var(--line)', alignItems: 'flex-start',
                            background: cur === id ? 'var(--panel2)' : '' }}
                   onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(t); } }}
                   onClick={() => open(t)}>
                {canManage && <input type="checkbox" checked={sel.includes(id)} aria-label="انتخاب تیکت"
                       onClick={e => e.stopPropagation()}
                       onChange={() => setSel(x => x.includes(id) ? x.filter(i => i !== id) : [...x, id])} />}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ color: 'var(--txt)', fontSize: 12.5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {t.subject || `تیکت ${id}`}
                  </div>
                  <div className="muted">
                    {t.user_name || ''} · {t.created_at || ''}
                    {t.reply_count ? ` · 💬 ${Number(t.reply_count).toLocaleString('fa')}` : ''}
                  </div>
                </div>
                <B kind={t.status === 'open' ? 'bad' : t.status === 'answered' ? 'warn' : 'ok'}>
                  {t.status === 'open' ? 'باز' : t.status === 'answered' ? 'پاسخ' : 'بسته'}
                </B>
              </div>
            );
          })}
        </div>

        {/* ستون ۲ — گفت‌وگو */}
        <div className="panel" style={{ minHeight: '66vh', display: 'flex', flexDirection: 'column' }}>
          {!cur && <Empty icon="💬" text="یک تیکت را از صف انتخاب کنید" />}
          {cur && !detail && <div className="panel-pad"><Loading /></div>}
          {detail && (
            <>
              <div className="panel-pad row" style={{ borderBottom: '1px solid var(--line)', padding: '10px 14px' }}>
                <b style={{ color: 'var(--txt)', fontSize: 13 }}>{detail.subject || `تیکت ${detail.id}`}</b>
                <span className="muted">#{detail.id} · {detail.created_at}</span>
                <span className="spacer" />
                <B kind={detail.status === 'open' ? 'bad' : detail.status === 'answered' ? 'warn' : 'ok'}>
                  {detail.status === 'open' ? 'باز' : detail.status === 'answered' ? 'پاسخ‌داده‌شده' : 'بسته'}
                </B>
              </div>
              <div className="chat" style={{ flex: 1, overflowY: 'auto', maxHeight: '48vh' }}>
                {detail.message && (
                  <div className="bubble user">
                    {detail.message}
                    <div className="muted" style={{ marginTop: 4 }}>{detail.created_at || ''}</div>
                  </div>
                )}
                {(detail.replies || []).map((m, i) => (
                  <div key={i} className={`bubble ${(m.sender || m.by) === 'support' || (m.sender || m.by) === 'admin' ? 'admin' : 'user'}`}>
                    {m.text || m.message}
                    <div className="muted" style={{ marginTop: 4 }}>
                      {(m.sender || m.by) === 'support' || (m.sender || m.by) === 'admin' ? '🛟 پشتیبانی · ' : ''}{m.at || m.created_at || ''}
                    </div>
                  </div>
                ))}
              </div>
              {detail.status !== 'closed' ? (
                <div className="panel-pad row" style={{ borderTop: '1px solid var(--line)', flexWrap: 'nowrap' }}>
                  {canReply ? <>
                    <textarea className="inp" rows={1} style={{ flex: 1, resize: 'none' }}
                              placeholder="پاسخ پشتیبانی… (Enter برای ارسال)"
                              value={text} onChange={e => setText(e.target.value)}
                              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }} />
                    <button className="btn primary" disabled={busy || !text.trim()} onClick={send}>ارسال ➤</button>
                  </> : <span className="muted">مجوز پاسخ‌گویی ندارید</span>}
                  {canManage && <button className="btn sm" onClick={() => act(api.ticketClose, 'تیکت بسته شد ✅')}>✅ بستن</button>}
                </div>
              ) : (
                <div className="panel-pad row" style={{ borderTop: '1px solid var(--line)' }}>
                  <span className="muted">این تیکت بسته شده است.</span>
                  <span className="spacer" />
                  {canManage && <button className="btn sm" onClick={() => act(api.ticketReopen, 'بازگشایی شد 🔓')}>🔓 بازگشایی</button>}
                </div>
              )}
            </>
          )}
        </div>

        {/* ستون ۳ — کانتکست کاربر */}
        <div className="panel panel-pad tk-ctx">
          {!detail && <Empty icon="👤" text="کانتکست کاربر" />}
          {detail && (
            <>
              <div className="row" style={{ flexWrap: 'nowrap' }}>
                <div className="avatar" style={{ width: 38, height: 38, fontSize: 15 }}>
                  {(detail.user?.name || '?')[0]}
                </div>
                <div style={{ minWidth: 0 }}>
                  <b style={{ color: 'var(--txt)' }}>{detail.user?.name || '—'}</b>
                  <div className="muted code">#{detail.user?.id}</div>
                </div>
              </div>
              <dl className="kv" style={{ gridTemplateColumns: '92px 1fr' }}>
                {Object.entries({
                  'شماره دانشجویی': detail.user?.student_id,
                  'ورودی': detail.user?.intake,
                  'گروه': detail.user?.group,
                }).filter(([, v]) => v).map(([k, v]) => (
                  <React.Fragment key={k}><dt>{k}</dt><dd>{String(v)}</dd></React.Fragment>
                ))}
              </dl>
              {ctx ? (
                <dl className="kv" style={{ gridTemplateColumns: '92px 1fr' }}>
                  <dt>وضعیت حساب</dt>
                  <dd>{ctx.user?.suspended ? '⏸ تعلیق' : ctx.user?.approved ? '✅ فعال' : '🕓 در انتظار'}</dd>
                  <dt>اشتراک</dt>
                  <dd>{ctx.subscription?.status === 'active'
                    ? `💎 ${ctx.subscription.plan} · ${ctx.subscription.days_left ?? '—'} روز` : '—'}</dd>
                  <dt>پاسخ‌ها</dt>
                  <dd>{Number(ctx.user?.total_answers || 0).toLocaleString('fa')}</dd>
                  <dt>تیکت‌ها</dt>
                  <dd>{Number(ctx.counts?.tickets || 0).toLocaleString('fa')}</dd>
                </dl>
              ) : detail && <div className="muted" style={{ fontSize: 11 }}>در حال تکمیل کانتکست…</div>}
              <div className="row" style={{ marginTop: 12 }}>
                <button className="btn sm primary" onClick={() => go && go('/users')}>👤 بازکردن در کاربران</button>
              </div>
            </>
          )}
        </div>
      </div>
    </>
  );
}
