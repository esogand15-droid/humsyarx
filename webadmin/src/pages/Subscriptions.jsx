import React, { useEffect, useState } from 'react';
import { api, errText } from '../api.js';
import {
  DataTable, Loading, ErrorState, Stat, B, PageHeader, Tabs, toast, Confirm, Drawer,
  Empty, NoPerm, Modal, Switch,
} from '../ui.jsx';

const fa = n => Number(n ?? 0).toLocaleString('fa-IR');
const money = n => `${Number(n ?? 0).toLocaleString('fa-IR')} تومان`;
const TABS = [
  ['control', '⚙️ مرکز کنترل'],
  ['payments', '🧾 رسیدها'],
  ['subscribers', '👥 مشترکین'],
  ['discounts', '🎁 تخفیف و کمپین'],
];

export default function Subscriptions({ route = '' }) {
  const requested = new URLSearchParams(route.split('?')[1] || '').get('tab');
  const [tab, setTab] = useState(TABS.some(([k]) => k === requested) ? requested : 'control');
  useEffect(() => { if (TABS.some(([k]) => k === requested)) setTab(requested); }, [requested]);
  const [ov, setOv] = useState(null);
  const [err, setErr] = useState('');
  const [denied, setDenied] = useState(false);

  const loadOverview = async () => {
    setErr('');
    try { setOv(await api.subOverview()); }
    catch (e) { if (e.status === 403) setDenied(true); else setErr(errText(e)); }
  };
  useEffect(() => { loadOverview(); }, []);

  if (denied) return <NoPerm text="مدیریت اشتراک نیازمند مجوز subscription.manage است" />;
  if (err) return <ErrorState title="بارگذاری مرکز اشتراک ناموفق بود" error={err} onRetry={loadOverview} />;
  if (!ov) return <Loading rows={6} />;

  const stats = ov.stats || {};
  return (
    <>
      <PageHeader title="مرکز کنترل اشتراک هامزیار" description="پلن‌ها، رسیدها، مشترکین، اعطای دستی، تخفیف و کمپین با یک منبع داده"
        actions={<><B kind={ov.settings?.subscription_enforced ? 'warn' : 'ok'}>{ov.settings?.subscription_enforced ? '🔒 اشتراک اجباری' : '🔓 دسترسی عمومی'}</B>
          <B kind={ov.settings?.protect_content_enabled ? 'ok' : 'warn'}>{ov.settings?.protect_content_enabled ? '🛡 محافظت محتوا روشن' : '⚠️ محافظت محتوا خاموش'}</B></>} />

      <div className="grid g4" style={{ marginBottom: 14 }}>
        <Stat icon="💎" label="اشتراک فعال" value={fa(stats.active)} tint="var(--teal)" />
        <Stat icon="🧾" label="رسید در انتظار" value={fa(stats.pending)} tint="var(--warn)" />
        <Stat icon="⏳" label="نزدیک پایان (۷ روز)" value={fa(stats.expiring)} tint="var(--acc)" />
        <Stat icon="💰" label="درآمد ماه" value={money(stats.revenue_month)} tint="var(--purple)" />
      </div>

      <Tabs items={TABS} value={tab} onChange={setTab} label="بخش‌های اشتراک" />

      {tab === 'control' && <ControlPanel ov={ov} refresh={loadOverview} />}
      {tab === 'payments' && <PaymentsPanel />}
      {tab === 'subscribers' && <SubscribersPanel ov={ov} refreshOverview={loadOverview} />}
      {tab === 'discounts' && <DiscountsPanel plans={ov.plans || []} refreshOverview={loadOverview} />}
    </>
  );
}

function ControlPanel({ ov, refresh }) {
  const [planEdit, setPlanEdit] = useState(null); // {} = new
  const [deletePlan, setDeletePlan] = useState(null);
  const [busy, setBusy] = useState('');

  const setPolicy = async (key, value) => {
    setBusy(key);
    try { await api.subSettingsUpdate({ [key]: value }); toast('سیاست اشتراک ذخیره شد ✅'); await refresh(); }
    catch (e) { toast(errText(e), 'err'); }
    setBusy('');
  };
  const planToggle = async p => {
    try { await api.subPlanToggle(p.id); toast(p.active ? 'پلن غیرفعال شد' : 'پلن فعال شد ✅'); refresh(); }
    catch (e) { toast(errText(e), 'err'); }
  };
  const planDelete = async p => {
    try { await api.subPlanDelete(p.id); toast('پلن حذف شد'); refresh(); }
    catch (e) { toast(errText(e), 'err'); }
  };

  return (
    <>
      <div className="grid g2">
        <div className="panel panel-pad">
          <b>🔐 سیاست دسترسی</b>
          <div className="grid" style={{ gap: 10, marginTop: 12 }}>
            <div className="row" style={{ alignItems: 'flex-start' }}>
              <Switch on={!!ov.settings?.subscription_enforced} disabled={!!busy}
                onChange={v => setPolicy('subscription_enforced', v)} />
              <div><b>اجباری‌بودن اشتراک هامزیار</b>
                <div className="muted">روشن: منابع مشمول فقط برای مشترک فعال باز می‌شوند؛ خاموش: همه دسترسی دارند.</div></div>
            </div>
            <div className="row" style={{ alignItems: 'flex-start' }}>
              <Switch on={!!ov.settings?.protect_content_enabled} disabled={!!busy}
                onChange={v => setPolicy('protect_content_enabled', v)} />
              <div><b>محافظت کپی‌رایت فایل‌ها</b>
                <div className="muted">ارسال فایل با protect_content؛ فوروارد و ذخیره مستقیم محدود می‌شود.</div></div>
            </div>
          </div>
        </div>
        <CardPanel card={ov.card || {}} refresh={refresh} />
      </div>

      <div className="panel panel-pad" style={{ marginTop: 14 }}>
        <div className="row"><div><b>📦 پلن‌های اشتراک</b>
          <div className="muted">مدت و قیمت هر پلن؛ غیرفعال‌سازی اطلاعات و تاریخچه را حذف نمی‌کند.</div></div>
          <span className="spacer" /><button className="btn primary" onClick={() => setPlanEdit({})}>➕ پلن جدید</button></div>
        <div className="grid g3" style={{ marginTop: 12 }}>
          {(ov.plans || []).map(p => <div key={p.id} className="panel panel-pad" style={{ background: 'var(--bg)' }}>
            <div className="row"><b>{p.name}</b><span className="spacer" />
              <B kind={p.active ? 'ok' : 'bad'}>{p.active ? 'فعال' : 'غیرفعال'}</B></div>
            <div className="row" style={{ marginTop: 10 }}><B>{fa(p.days)} روز</B><B kind="acc">{money(p.price)}</B></div>
            <div className="row" style={{ marginTop: 10, gap: 5 }}>
              <button className="btn sm" onClick={() => setPlanEdit(p)}>✏️ ویرایش</button>
              <button className="btn sm" onClick={() => planToggle(p)}>{p.active ? '⏸ غیرفعال' : '▶ فعال'}</button>
              <button className="btn sm danger" onClick={() => setDeletePlan(p)} aria-label={`حذف پلن ${p.name}`}>🗑</button>
            </div>
          </div>)}
          {!(ov.plans || []).length && <Empty text="هنوز پلنی تعریف نشده" />}
        </div>
      </div>

      {planEdit && <PlanModal plan={planEdit.id ? planEdit : null}
        onClose={() => setPlanEdit(null)} onDone={() => { setPlanEdit(null); refresh(); }} />}
      {deletePlan && <Confirm danger text={`حذف پلن «${deletePlan.name}»؟ تاریخچه خریدها حفظ می‌شود.`}
        onYes={async () => { const p = deletePlan; setDeletePlan(null); await planDelete(p); }}
        onNo={() => setDeletePlan(null)} />}
    </>
  );
}

function CardPanel({ card, refresh }) {
  const [f, setF] = useState({ card_number: card.card_number || '', card_owner: card.card_owner || '' });
  const [busy, setBusy] = useState(false);
  useEffect(() => setF({ card_number: card.card_number || '', card_owner: card.card_owner || '' }), [card.card_number, card.card_owner]);
  const save = async () => {
    setBusy(true);
    try { await api.subCardUpdate(f); toast('اطلاعات کارت ذخیره شد ✅'); refresh(); }
    catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };
  return <div className="panel panel-pad">
    <b>💳 کارت پرداخت</b>
    <div className="grid" style={{ gap: 9, marginTop: 12 }}>
      <label className="fld"><span>شماره کارت</span><input className="inp" dir="ltr" value={f.card_number}
        onChange={e => setF({ ...f, card_number: e.target.value })} /></label>
      <label className="fld"><span>نام صاحب کارت</span><input className="inp" value={f.card_owner}
        onChange={e => setF({ ...f, card_owner: e.target.value })} /></label>
      <button className="btn primary" disabled={busy || f.card_number.trim().length < 4 || f.card_owner.trim().length < 2}
        onClick={save}>{busy ? '⏳ …' : '💾 ذخیره کارت'}</button>
    </div>
  </div>;
}

function PlanModal({ plan, onClose, onDone }) {
  const [f, setF] = useState({ name: plan?.name || '', days: plan?.days || 30, price: plan?.price || 0 });
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try {
      const body = { name: f.name.trim(), days: Number(f.days), price: Number(f.price) };
      if (plan) await api.subPlanUpdate(plan.id, body); else await api.subPlanAdd(body);
      toast(plan ? 'پلن ویرایش شد ✅' : 'پلن ساخته شد ✅'); onDone();
    } catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };
  return <Modal title={plan ? `✏️ ویرایش ${plan.name}` : '➕ پلن اشتراک جدید'} onClose={onClose}>
    <div className="grid" style={{ gap: 10 }}>
      <input className="inp" placeholder="نام پلن" value={f.name} onChange={e => setF({ ...f, name: e.target.value })} />
      <div className="row"><label className="fld" style={{ flex: 1 }}><span>تعداد روز</span>
        <input className="inp" type="number" min="1" max="3650" value={f.days} onChange={e => setF({ ...f, days: e.target.value })} /></label>
        <label className="fld" style={{ flex: 1 }}><span>قیمت (تومان)</span>
        <input className="inp" type="number" min="0" value={f.price} onChange={e => setF({ ...f, price: e.target.value })} /></label></div>
      <div className="row"><button className="btn primary" disabled={busy || f.name.trim().length < 2 || Number(f.days) < 1}
        onClick={save}>{busy ? '⏳ …' : 'ذخیره'}</button><button className="btn" onClick={onClose}>انصراف</button></div>
    </div>
  </Modal>;
}

function PaymentsPanel() {
  const [status, setStatus] = useState('pending');
  const [q, setQ] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [err, setErr] = useState('');
  const [rcpt, setRcpt] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const LIMIT = 25;

  const load = async () => {
    setErr(''); setData(null);
    try { setData(await api.subPayments({ status, search, skip: (page - 1) * LIMIT, limit: LIMIT })); }
    catch (e) { setErr(errText(e)); }
  };
  useEffect(() => { load(); }, [status, search, page]);
  const decide = (pay, approved, note = '') => setConfirm({ pay, approved, note });
  const doDecision = async () => {
    const c = confirm; setConfirm(null);
    try { await api.subPaymentDecision(c.pay.id, c.approved, c.note); toast('تصمیم ثبت شد ✅'); setRcpt(null); load(); }
    catch (e) { toast(errText(e), 'err'); }
  };
  const cols = [
    { k: 'user_name', label: 'دانشجو', render: r => <div><b>{r.user_name}</b><div className="muted">{r.student_id || `#${r.user_id}`}</div></div> },
    { k: 'plan_name', label: 'پلن' },
    { k: 'final_price', label: 'مبلغ', render: r => money(r.final_price) },
    { k: 'discount_code', label: 'تخفیف', render: r => r.discount_code ? <B kind="purple">{r.discount_code} {r.discount_percent ? `· ${fa(r.discount_percent)}٪` : ''}</B> : '—' },
    { k: 'has_receipt', label: 'رسید', render: r => r.has_receipt ? <B kind="acc">🖼 دارد</B> : '—' },
    { k: 'submitted_at', label: 'ثبت' },
    { k: 'status', label: 'وضعیت', render: r => <B kind={r.status === 'pending' ? 'warn' : r.status === 'approved' ? 'ok' : 'bad'}>{r.status}</B> },
    { k: 'ops', label: '', stop: true, render: r => r.status === 'pending' && <div className="row" style={{ gap: 4 }}>
      <button className="btn sm ok" onClick={() => decide(r, true)} aria-label="تأیید رسید پرداخت">✅</button>
      <button className="btn sm danger" onClick={() => decide(r, false)} aria-label="رد رسید پرداخت">❌</button></div> },
  ];
  if (err) return <ErrorState error={err} onRetry={load} />;
  const total = data?.total || 0;
  return <>
    <div className="panel panel-pad row" style={{ marginBottom: 12, flexWrap: 'wrap' }}>
      <div className="tabs" style={{ border: 0, margin: 0 }} role="tablist" aria-label="وضعیت پرداخت‌ها">
        {[['pending', 'در انتظار'], ['approved', 'تأیید'], ['rejected', 'رد'], ['', 'همه']].map(([k, l]) =>
          <button key={k} type="button" role="tab" aria-selected={status === k} className={`tab ${status === k ? 'on' : ''}`} onClick={() => { setStatus(k); setPage(1); }}>{l}</button>)}
      </div>
      <span className="spacer" />
      <input className="inp" style={{ minWidth: 250 }} value={q} onChange={e => setQ(e.target.value)}
        onKeyDown={e => e.key === 'Enter' && (setSearch(q.trim()), setPage(1))} placeholder="نام، آیدی، پلن یا کد تخفیف…" />
      <button className="btn sm" onClick={() => { setSearch(q.trim()); setPage(1); }}>🔎 جست‌وجو</button>
    </div>
    {!data ? <Loading rows={5} /> : <DataTable columns={cols} rows={data.payments || []} rowKey="id" colToggle
      onRow={setRcpt} pager={{ page, pages: Math.max(1, Math.ceil(total / LIMIT)), total, onPage: setPage }} />}
    {rcpt && <ReceiptDrawer pay={rcpt} decide={(ok, note) => decide(rcpt, ok, note)}
      onClose={() => setRcpt(null)} />}
    {confirm && <Confirm danger={!confirm.approved}
      text={confirm.approved ? `تأیید رسید ${confirm.pay.user_name} و فعال‌سازی اشتراک؟` : `رد رسید ${confirm.pay.user_name}؟`}
      onYes={doDecision} onNo={() => setConfirm(null)} />}
  </>;
}

function ReceiptDrawer({ pay: r, decide, onClose }) {
  const [note, setNote] = useState('');
  const [imgErr, setImgErr] = useState(false);
  const sendToMe = async () => {
    try { await api.subSendReceipt(r.id); toast('تصویر رسید در تلگرام برای شما ارسال شد'); }
    catch (e) { toast(errText(e), 'err'); }
  };
  return <Drawer wide title={`🧾 رسید — ${r.user_name || r.user_id}`} onClose={onClose}>
    <div className="rcpt">
      <div><dl className="kv" style={{ marginTop: 0 }}>
        {Object.entries({ 'دانشجو': r.user_name, 'شماره دانشجویی': r.student_id,
          'یوزرنیم': r.username && '@' + r.username, 'پلن': r.plan_name,
          'مبلغ پایه': money(r.price), 'مبلغ نهایی': money(r.final_price),
          'کد تخفیف': r.discount_code, 'درصد تخفیف': r.discount_percent != null ? `${r.discount_percent}٪` : '',
          'ثبت': r.submitted_at, 'یادداشت بررسی': r.review_note,
        }).filter(([, v]) => v).map(([k, v]) => <React.Fragment key={k}><dt>{k}</dt><dd>{String(v)}</dd></React.Fragment>)}</dl>
        <button className="btn sm" onClick={sendToMe}>📨 ارسال تصویر به تلگرام من</button>
        {r.status === 'pending' && <div className="panel panel-pad" style={{ background: 'var(--bg)', marginTop: 10 }}>
          <input className="inp" style={{ width: '100%' }} placeholder="یادداشت بررسی…" value={note} onChange={e => setNote(e.target.value)} />
          <div className="row" style={{ marginTop: 8 }}><button className="btn ok" onClick={() => decide(true, note)}>✅ تأیید</button>
            <button className="btn danger" onClick={() => decide(false, note)}>❌ رد</button></div>
        </div>}
      </div>
      <div className="rcpt-img">{r.has_receipt && !imgErr ? <img src={api.subReceiptSrc(r.id)} alt="تصویر رسید"
        onError={() => setImgErr(true)} /> : <Empty icon="🖼" text="تصویر رسید در دسترس نیست" />}</div>
    </div>
  </Drawer>;
}

function SubscribersPanel({ ov, refreshOverview }) {
  const [status, setStatus] = useState('active');
  const [q, setQ] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [err, setErr] = useState('');
  const [selected, setSelected] = useState(null);
  const [grantOpen, setGrantOpen] = useState(false);
  const [bulkOpen, setBulkOpen] = useState(false);
  const LIMIT = 30;
  const load = async () => {
    setErr(''); setData(null);
    try { setData(await api.subSubscribers({ status, search, skip: (page - 1) * LIMIT, limit: LIMIT })); }
    catch (e) { setErr(errText(e)); }
  };
  useEffect(() => { load(); }, [status, search, page]);
  if (err) return <ErrorState error={err} onRetry={load} />;
  const total = data?.total || 0;
  const cols = [
    { k: 'name', label: 'دانشجو', render: r => <div><b>{r.name}</b><div className="muted">{r.student_id || `#${r.user_id}`}</div></div> },
    { k: 'plan_name', label: 'پلن' },
    { k: 'end_date', label: 'پایان', render: r => <span className="code">{r.end_date || '—'}</span> },
    { k: 'status', label: 'وضعیت', render: r => <B kind={r.status === 'active' ? 'ok' : r.status === 'expired' ? 'warn' : 'bad'}>{r.status}</B> },
    { k: 'ops', label: '', stop: true, render: r => <button className="btn sm" onClick={() => setSelected(r.user_id)}>مدیریت ‹</button> },
  ];
  return <>
    <div className="row" style={{ marginBottom: 12, flexWrap: 'wrap' }}>
      <div className="tabs" style={{ border: 0, margin: 0 }} role="tablist" aria-label="وضعیت اشتراک‌ها">
        {[['active', 'فعال'], ['expired', 'منقضی'], ['revoked', 'لغوشده']].map(([k, l]) =>
          <button key={k} type="button" role="tab" aria-selected={status === k} className={`tab ${status === k ? 'on' : ''}`} onClick={() => { setStatus(k); setPage(1); }}>{l}</button>)}
      </div>
      <input className="inp" style={{ minWidth: 230 }} value={q} onChange={e => setQ(e.target.value)}
        onKeyDown={e => e.key === 'Enter' && (setSearch(q.trim()), setPage(1))} placeholder="دانشجو، پلن یا آیدی…" />
      <button className="btn sm" onClick={() => { setSearch(q.trim()); setPage(1); }} aria-label="جست‌وجوی مشترک‌ها">🔎</button>
      <span className="spacer" />
      <button className="btn" onClick={() => setGrantOpen(true)}>👤 اعطای دستی</button>
      <button className="btn primary" onClick={() => setBulkOpen(true)}>🎁 اعطای دسته‌جمعی</button>
    </div>
    {!data ? <Loading rows={5} /> : <DataTable columns={cols} rows={data.subscribers || []} rowKey="user_id" colToggle
      onRow={r => setSelected(r.user_id)} pager={{ page, pages: Math.max(1, Math.ceil(total / LIMIT)), total, onPage: setPage }} />}
    {selected && <SubscriberDrawer uid={selected} plans={ov.plans || []} onClose={() => setSelected(null)}
      onChanged={() => { load(); refreshOverview(); }} />}
    {grantOpen && <ManualGrantModal plans={ov.plans || []} onClose={() => setGrantOpen(false)}
      onDone={() => { setGrantOpen(false); load(); refreshOverview(); }} />}
    {bulkOpen && <BulkGrantModal roles={ov.roles || []} onClose={() => setBulkOpen(false)}
      onDone={() => { load(); refreshOverview(); }} />}
  </>;
}

function ManualGrantModal({ plans, onClose, onDone }) {
  const [q, setQ] = useState('');
  const [hits, setHits] = useState(null);
  const [user, setUser] = useState(null);
  const [days, setDays] = useState(30);
  const [planName, setPlanName] = useState('اشتراک دستی');
  const [extend, setExtend] = useState(true);
  const [busy, setBusy] = useState(false);
  const search = async () => {
    if (q.trim().length < 2) return;
    try { setHits((await api.subUserSearch(q.trim())).users || []); } catch (e) { toast(errText(e), 'err'); }
  };
  const grant = async () => {
    setBusy(true);
    try { await api.subGrant({ user_id: user.id, days: Number(days), plan_name: planName.trim(), extend }); toast('اشتراک فعال شد ✅'); onDone(); }
    catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };
  return <Modal title="👤 اعطای دستی اشتراک" onClose={onClose}>
    {!user ? <><div className="row"><input className="inp" style={{ flex: 1 }} value={q} onChange={e => setQ(e.target.value)}
      onKeyDown={e => e.key === 'Enter' && search()} placeholder="نام، یوزرنیم، شماره یا آیدی…" /><button className="btn" onClick={search} aria-label="جست‌وجوی کاربر">🔎</button></div>
      <div className="grid" style={{ gap: 6, marginTop: 8 }}>{(hits || []).map(u => <button key={u.id} className="pick" onClick={() => setUser(u)}>
        <b>{u.name}</b><span className="muted">{u.student_id || `#${u.id}`}</span></button>)}</div></> : <div className="grid" style={{ gap: 10 }}>
      <div className="panel panel-pad" style={{ background: 'var(--bg)' }}><b>{user.name}</b> <span className="code">#{user.id}</span></div>
      <div className="row">{[7, 30, 90].map(d => <button key={d} className={`btn sm ${Number(days) === d ? 'primary' : ''}`} onClick={() => setDays(d)}>{fa(d)} روز</button>)}
        <input className="inp" type="number" min="1" max="3650" style={{ width: 100 }} value={days} onChange={e => setDays(e.target.value)} /></div>
      <select className="inp" value={planName} onChange={e => setPlanName(e.target.value)}>
        <option value="اشتراک دستی">اشتراک دستی</option>{plans.map(p => <option key={p.id} value={p.name}>{p.name}</option>)}
      </select>
      <label className="row"><Switch on={extend} onChange={setExtend} /><span>تمدید روی اشتراک فعلی</span></label>
      <div className="row"><button className="btn primary" disabled={busy || Number(days) < 1} onClick={grant}>فعال‌سازی</button>
        <button className="btn" onClick={() => setUser(null)}>تغییر کاربر</button></div>
    </div>}
  </Modal>;
}

function BulkGrantModal({ roles, onClose, onDone }) {
  const [mode, setMode] = useState('list');
  const [ids, setIds] = useState('');
  const [role, setRole] = useState('');
  const [days, setDays] = useState(30);
  const [planName, setPlanName] = useState('اشتراک رایگان');
  const [extend, setExtend] = useState(true);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const run = async () => {
    setBusy(true); setResult(null);
    try {
      const r = await api.subGrantBulk({ mode, role: mode === 'role' ? role : null,
        identifiers: mode === 'list' ? ids.split('\n').map(x => x.trim()).filter(Boolean) : [],
        days: Number(days), plan_name: planName.trim(), extend });
      setResult(r); toast(`${fa(r.granted)} اشتراک فعال شد ✅`); onDone();
    } catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };
  return <Modal title="🎁 اعطای رایگان دسته‌جمعی" onClose={onClose}>
    <div className="tabs" role="tablist" aria-label="روش اعطای دسته‌جمعی"><button type="button" role="tab" aria-selected={mode === 'list'} className={`tab ${mode === 'list' ? 'on' : ''}`} onClick={() => setMode('list')}>فهرست کاربران</button>
      <button type="button" role="tab" aria-selected={mode === 'role'} className={`tab ${mode === 'role' ? 'on' : ''}`} onClick={() => setMode('role')}>براساس نقش</button></div>
    <div className="grid" style={{ gap: 10 }}>
      {mode === 'list' ? <textarea className="inp" rows={7} value={ids} onChange={e => setIds(e.target.value)}
        placeholder={'هر خط: آیدی عددی، @username، شماره دانشجویی یا نام دقیق'} /> :
        <select className="inp" value={role} onChange={e => setRole(e.target.value)}><option value="">انتخاب نقش…</option>
          {roles.filter(r => r.active !== false).map(r => <option key={r.key} value={r.key}>{r.icon} {r.label}</option>)}</select>}
      <div className="row"><input className="inp" type="number" min="1" max="3650" value={days} onChange={e => setDays(e.target.value)} />
        <input className="inp" style={{ flex: 1 }} value={planName} onChange={e => setPlanName(e.target.value)} placeholder="نام پلن" /></div>
      <label className="row"><Switch on={extend} onChange={setExtend} /><span>تمدید اشتراک موجود</span></label>
      <button className="btn primary" disabled={busy || Number(days) < 1 || (mode === 'role' ? !role : !ids.trim())} onClick={run}>
        {busy ? '⏳ در حال پردازش…' : 'اجرای اعطای دسته‌جمعی'}</button>
      {result && <div className="grid" style={{ gap: 6 }}><div className="row"><B kind="ok">موفق: {fa(result.granted)}</B><B kind={result.failed_ids?.length ? 'bad' : ''}>ناموفق: {fa(result.failed_ids?.length)}</B>
        <B kind={result.unresolved?.length ? 'warn' : ''}>پیدانشد: {fa(result.unresolved?.length)}</B></div>
        {!!result.failed_ids?.length && <div className="muted">آیدی‌های ناموفق: {result.failed_ids.slice(0, 30).join('، ')}</div>}
        {!!result.unresolved?.length && <div className="muted">ورودی‌های پیدانشده: {result.unresolved.slice(0, 30).join('، ')}</div>}</div>}
    </div>
  </Modal>;
}

function SubscriberDrawer({ uid, plans, onClose, onChanged }) {
  const [data, setData] = useState(null);
  const [days, setDays] = useState(30);
  const [planName, setPlanName] = useState('اشتراک دستی');
  const [extend, setExtend] = useState(true);
  const [reason, setReason] = useState('');
  const [confirm, setConfirm] = useState(false);
  const load = async () => { try { setData(await api.subSubscriber(uid)); } catch (e) { toast(errText(e), 'err'); } };
  useEffect(() => { load(); }, [uid]);
  const grant = async () => {
    try { await api.subGrant({ user_id: uid, days: Number(days), plan_name: planName, extend }); toast('اشتراک به‌روزرسانی شد ✅'); load(); onChanged(); }
    catch (e) { toast(errText(e), 'err'); }
  };
  const revoke = async () => {
    setConfirm(false);
    try { await api.subRevoke(uid, reason.trim()); toast('اشتراک لغو شد'); load(); onChanged(); }
    catch (e) { toast(errText(e), 'err'); }
  };
  return <Drawer wide title="💎 پرونده اشتراک کاربر" onClose={onClose}>
    {!data ? <Loading rows={5} /> : <>
      <div className="panel panel-pad"><div className="row"><b>{data.user.name}</b><span className="code">#{uid}</span>
        <span className="spacer" />{data.subscription ? <B kind={data.subscription.status === 'active' ? 'ok' : 'warn'}>{data.subscription.status}</B> : <B>بدون اشتراک</B>}</div>
        <dl className="kv">{Object.entries({ 'شماره دانشجویی': data.user.student_id, 'ورودی': data.user.intake, 'گروه': data.user.group,
          'پلن فعلی': data.subscription?.plan_name, 'پایان': data.subscription?.end_date,
          'روز باقی': data.subscription?.days_left,
        }).filter(([, v]) => v !== undefined && v !== null && v !== '').map(([k, v]) => <React.Fragment key={k}><dt>{k}</dt><dd>{String(v)}</dd></React.Fragment>)}</dl></div>
      <div className="panel panel-pad" style={{ marginTop: 12 }}><b>➕ فعال‌سازی / تمدید</b>
        <div className="row" style={{ marginTop: 8 }}>{[7, 30, 90].map(d => <button key={d} className={`btn sm ${Number(days) === d ? 'primary' : ''}`} onClick={() => setDays(d)}>{fa(d)} روز</button>)}
          <input className="inp" type="number" min="1" max="3650" style={{ width: 90 }} value={days} onChange={e => setDays(e.target.value)} />
          <select className="inp" value={planName} onChange={e => setPlanName(e.target.value)}><option>اشتراک دستی</option>{plans.map(p => <option key={p.id}>{p.name}</option>)}</select>
          <label className="row"><Switch on={extend} onChange={setExtend} /> تمدید</label>
          <button className="btn primary" onClick={grant}>ثبت</button></div>
        {data.subscription?.status === 'active' && <div className="row" style={{ marginTop: 10 }}><input className="inp" style={{ flex: 1 }} value={reason}
          onChange={e => setReason(e.target.value)} placeholder="دلیل لغو…" /><button className="btn danger" disabled={reason.trim().length < 2} onClick={() => setConfirm(true)}>لغو اشتراک</button></div>}
      </div>
      <div className="h1" style={{ fontSize: 14, marginTop: 16 }}>📜 تاریخچه پرداخت</div>
      {!(data.payments || []).length ? <Empty text="پرداختی ثبت نشده" /> : <div className="grid" style={{ gap: 6 }}>
        {data.payments.map(p => <div key={p.id} className="panel panel-pad row"><B kind={p.status === 'approved' ? 'ok' : p.status === 'rejected' ? 'bad' : 'warn'}>{p.status}</B>
          <span style={{ flex: 1 }}>{p.plan_name}</span><span>{money(p.final_price)}</span><span className="muted">{p.submitted_at}</span></div>)}</div>}
    </>}
    {confirm && <Confirm danger text={`لغو اشتراک «${data?.user?.name}» با دلیل «${reason}»؟`} onYes={revoke} onNo={() => setConfirm(false)} />}
  </Drawer>;
}

function DiscountsPanel({ plans, refreshOverview }) {
  const [items, setItems] = useState(null);
  const [err, setErr] = useState('');
  const [addOpen, setAddOpen] = useState(false);
  const [detail, setDetail] = useState(null);
  const [del, setDel] = useState(null);
  const load = async () => { setErr(''); try { setItems((await api.discounts()).discounts || []); } catch (e) { setErr(errText(e)); } };
  useEffect(() => { load(); }, []);
  const toggle = async c => { try { await api.discountToggle(c.code); toast('وضعیت کد تغییر کرد'); load(); } catch (e) { toast(errText(e), 'err'); } };
  const remove = async c => { try { await api.discountDelete(c.code); toast('کد حذف شد'); load(); refreshOverview(); } catch (e) { toast(errText(e), 'err'); } };
  const planMap = Object.fromEntries(plans.map(p => [String(p.id), p.name]));
  if (err) return <ErrorState error={err} onRetry={load} />;
  return <>
    <div className="row" style={{ marginBottom: 12 }}><div><b>🎁 کدهای تخفیف و کمپین</b>
      <div className="muted">هدف پلن، ظرفیت، محدودیت هر کاربر، آمار مالی و انتشار هدفمند</div></div><span className="spacer" />
      <button className="btn primary" onClick={() => setAddOpen(true)}>➕ کد جدید</button></div>
    {!items ? <Loading rows={5} /> : <div className="grid g2">{items.map(c => <div key={c.code} className="panel panel-pad">
      <div className="row"><span className="code" style={{ fontSize: 15, fontWeight: 800 }}>{c.code}</span><B kind="purple">{fa(c.percent)}٪</B>
        <span className="spacer" /><B kind={c.active ? 'ok' : 'bad'}>{c.active ? 'فعال' : 'غیرفعال'}</B></div>
      <div className="row" style={{ marginTop: 8, flexWrap: 'wrap' }}><B>مصرف {fa(c.used_count)} / {c.max_uses ? fa(c.max_uses) : '∞'}</B>
        <B>هر کاربر: {c.per_user_limit ? fa(c.per_user_limit) : '∞'}</B><B>{c.expires_at || 'بدون انقضا'}</B></div>
      <div className="muted" style={{ marginTop: 7 }}>پلن‌ها: {(c.target_plan_ids || []).length ? c.target_plan_ids.map(id => planMap[String(id)] || id).join('، ') : 'همه‌ی پلن‌ها'}</div>
      <div className="row" style={{ marginTop: 10 }}><button className="btn sm" onClick={() => setDetail(c)}>📊 آمار و کمپین</button>
        <button className="btn sm" onClick={() => toggle(c)} aria-label={`${c.active ? 'غیرفعال‌کردن' : 'فعال‌کردن'} کد ${c.code}`}>{c.active ? '⏸' : '▶'}</button><button className="btn sm danger" onClick={() => setDel(c)} aria-label={`حذف کد ${c.code}`}>🗑</button></div>
    </div>)}{!items.length && <Empty text="کد تخفیفی نیست" />}</div>}
    {addOpen && <DiscountAddModal plans={plans} onClose={() => setAddOpen(false)} onDone={() => { setAddOpen(false); load(); refreshOverview(); }} />}
    {detail && <DiscountDrawer item={detail} onClose={() => setDetail(null)} />}
    {del && <Confirm danger text={`حذف کد «${del.code}»؟ snapshot پرداخت‌های قبلی حفظ می‌شود.`}
      onYes={async () => { const c = del; setDel(null); await remove(c); }} onNo={() => setDel(null)} />}
  </>;
}

function DiscountAddModal({ plans, onClose, onDone }) {
  const [f, setF] = useState({ code: '', percent: 10, max_uses: 0, per_user_limit: 0, expires_at: '', target_plan_ids: [] });
  const [busy, setBusy] = useState(false);
  const togglePlan = id => setF(x => ({ ...x, target_plan_ids: x.target_plan_ids.includes(id) ? x.target_plan_ids.filter(v => v !== id) : [...x.target_plan_ids, id] }));
  const save = async () => {
    setBusy(true);
    try { await api.discountAdd({ ...f, code: f.code.trim(), percent: Number(f.percent), max_uses: Number(f.max_uses),
      per_user_limit: Number(f.per_user_limit), expires_at: f.expires_at || null }); toast('کد تخفیف ساخته شد ✅'); onDone(); }
    catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };
  return <Modal title="➕ کد تخفیف جدید" onClose={onClose}><div className="grid" style={{ gap: 10 }}>
    <div className="row"><input className="inp" dir="ltr" placeholder="CODE" value={f.code} onChange={e => setF({ ...f, code: e.target.value.toUpperCase() })} />
      <label className="fld"><span>درصد</span><input className="inp" type="number" min="1" max="100" value={f.percent} onChange={e => setF({ ...f, percent: e.target.value })} /></label></div>
    <div className="row"><label className="fld"><span>ظرفیت کل (۰=نامحدود)</span><input className="inp" type="number" min="0" value={f.max_uses} onChange={e => setF({ ...f, max_uses: e.target.value })} /></label>
      <label className="fld"><span>سقف هر کاربر (۰=نامحدود)</span><input className="inp" type="number" min="0" value={f.per_user_limit} onChange={e => setF({ ...f, per_user_limit: e.target.value })} /></label>
      <label className="fld"><span>انقضا</span><input className="inp" type="date" value={f.expires_at} onChange={e => setF({ ...f, expires_at: e.target.value })} /></label></div>
    <div><div className="muted" style={{ marginBottom: 6 }}>پلن‌های هدف — خالی یعنی همه</div><div className="row">{plans.map(p => <label key={p.id} className={`badge ${f.target_plan_ids.includes(p.id) ? 'acc' : ''}`}>
      <input type="checkbox" checked={f.target_plan_ids.includes(p.id)} onChange={() => togglePlan(p.id)} /> {p.name}</label>)}</div></div>
    <div className="row"><button className="btn primary" disabled={busy || f.code.trim().length < 2 || Number(f.percent) < 1} onClick={save}>ساخت کد</button>
      <button className="btn" onClick={onClose}>انصراف</button></div>
  </div></Modal>;
}

function DiscountDrawer({ item, onClose }) {
  const [stats, setStats] = useState(null);
  const [preview, setPreview] = useState(null);
  const [runs, setRuns] = useState(null);
  const [target, setTarget] = useState('all');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [busy, setBusy] = useState(false);
  const load = async () => {
    try { const [s, p, r] = await Promise.all([api.discountStats(item.code), api.discountPreview(item.code), api.discountBroadcasts(item.code)]);
      setStats(s); setPreview(p); setRuns(r.broadcasts || []); }
    catch (e) { toast(errText(e), 'err'); }
  };
  useEffect(() => { load(); }, [item.code]);
  const broadcast = async () => {
    setBusy(true);
    try { const r = await api.discountBroadcast(item.code, { target, title: title.trim() || null, description: description.trim() || null });
      toast(`کمپین برای ${fa(r.total)} نفر شروع شد 📢`); load(); }
    catch (e) { toast(errText(e), 'err'); }
    setBusy(false);
  };
  const cancel = async bid => { try { await api.discountBroadcastCancel(item.code, bid); toast('کمپین متوقف شد'); load(); } catch (e) { toast(errText(e), 'err'); } };
  return <Drawer wide title={`🎁 آمار و کمپین — ${item.code}`} onClose={onClose}>
    {!stats ? <Loading rows={4} /> : <>
      <div className="grid g4"><Stat icon="🎟" label="مصرف" value={fa(stats.used_count)} /><Stat icon="⏳" label="باقی‌مانده" value={stats.remaining_uses == null ? 'نامحدود' : fa(stats.remaining_uses)} />
        <Stat icon="💰" label="درآمد با تخفیف" value={money(stats.payments?.revenue)} /><Stat icon="📉" label="مبلغ تخفیف" value={money(stats.payments?.discount_given)} /></div>
      <div className="panel panel-pad" style={{ marginTop: 12 }}><b>👁 پیش‌نمایش پیام</b>
        <div style={{ whiteSpace: 'pre-wrap', marginTop: 8, color: 'var(--txt2)', maxHeight: 220, overflowY: 'auto' }}>{preview?.text || '—'}</div></div>
      <div className="panel panel-pad" style={{ marginTop: 12 }}><b>📢 انتشار کمپین</b>
        <div className="row" style={{ marginTop: 8 }}><select className="inp" value={target} onChange={e => setTarget(e.target.value)}>
          <option value="all">همه کاربران</option><option value="subscribers">مشترکین</option><option value="no_sub">بدون اشتراک فعال</option></select>
          <input className="inp" style={{ flex: 1 }} value={title} onChange={e => setTitle(e.target.value)} placeholder="عنوان سفارشی (اختیاری)" /></div>
        <textarea className="inp" rows={2} style={{ width: '100%', marginTop: 8 }} value={description} onChange={e => setDescription(e.target.value)} placeholder="توضیح سفارشی (اختیاری)" />
        <button className="btn primary" style={{ marginTop: 8 }} disabled={busy || item.active === false} onClick={broadcast}>{busy ? '⏳ شروع…' : '📢 شروع انتشار'}</button></div>
      <div className="row" style={{ marginTop: 16 }}><div className="h1" style={{ fontSize: 14 }}>تاریخچه انتشار</div>
        <span className="spacer" /><button className="btn sm" onClick={load}>↻ تازه‌سازی وضعیت</button></div>
      {!(runs || []).length ? <Empty text="انتشاری ثبت نشده" /> : <div className="grid" style={{ gap: 6 }}>{runs.map(r => <div key={r.broadcast_id} className="panel panel-pad">
        <div className="row"><B kind={r.status === 'completed' ? 'ok' : r.status === 'sending' ? 'warn' : 'bad'}>{r.status}</B><B>{r.target}</B>
          <span className="spacer" /><span className="muted">{r.created_at}</span>{r.status === 'sending' && <button className="btn sm danger" onClick={() => cancel(r.broadcast_id)}>توقف</button>}</div>
        <div className="row" style={{ marginTop: 6 }}><span>کل {fa(r.total)}</span><span>✅ {fa(r.sent)}</span><span>❌ {fa(r.failed)}</span><span>🚫 {fa(r.blocked)}</span></div>
      </div>)}</div>}
    </>}
  </Drawer>;
}
