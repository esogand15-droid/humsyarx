import React, { useEffect, useMemo, useState } from 'react';
import { api, errText } from '../api.js';
import { B, Confirm, DataTable, Drawer, Empty, ErrorState, FaDateTime, Loading, PageHeader, Tabs, toast } from '../ui.jsx';
import { writeHashQuery } from '../urlState.js';

const fa = n => Number(n ?? 0).toLocaleString('fa-IR');
const TABS = [['work', '📌 کارهای من'], ['alerts', '🔔 هشدارها'], ['quality', '🧬 کیفیت داده']];
const sevKind = value => value === 'critical' ? 'bad' : value === 'warning' ? 'warn' : value === 'high' ? 'bad' : 'acc';

export default function Operations({ route = '', me, go }) {
  const requested = new URLSearchParams(route.split('?')[1] || '').get('tab');
  const allowedTabs = useMemo(() => TABS.filter(([key]) => key !== 'quality' || me?.is_owner || (me?.perms || []).includes('system.manage')), [me]);
  const [tab, setTab] = useState(allowedTabs.some(([key]) => key === requested) ? requested : 'work');
  const changeTab = value => { setTab(value); writeHashQuery('/operations', { tab: value !== 'work' ? value : '' }); };
  useEffect(() => { if (allowedTabs.some(([key]) => key === requested)) setTab(requested); }, [requested, allowedTabs]);
  return <>
    <PageHeader title="مرکز عملیات" description="کارهای تخصیص‌یافته، هشدارهای واقعی و کیفیت داده — بدون task یا anomaly ساختگی" />
    <Tabs items={allowedTabs} value={tab} onChange={changeTab} label="بخش‌های مرکز عملیات" />
    {tab === 'work' && <MyWork go={go} />}
    {tab === 'alerts' && <Alerts go={go} />}
    {tab === 'quality' && <DataQuality />}
  </>;
}

function MyWork({ go }) {
  const [data, setData] = useState(null); const [err, setErr] = useState('');
  const load = () => { setErr(''); setData(null); api.myWork().then(setData).catch(e => setErr(errText(e))); };
  useEffect(load, []);
  if (err) return <ErrorState error={err} onRetry={load} />;
  if (!data) return <Loading rows={5} />;
  const tasks = data.tasks || [];
  if (!tasks.length) return <Empty icon="📌" text="برای مجوزهای فعلی صف کاری تعریف‌شده‌ای وجود ندارد" />;
  return <div className="grid g2 operations-grid">
    {tasks.map(item => <button key={item.key} className="panel panel-pad operation-card" onClick={() => go?.(item.go)}>
      <span className="operation-icon">{item.icon}</span>
      <span className="operation-body"><b>{item.label}</b><span className="muted">{item.oldest_at ? <>قدیمی‌ترین: <FaDateTime value={item.oldest_at} /></> : item.empty ? 'صف خالی است' : 'زمان ثبت موجود نیست'}</span></span>
      <B kind={item.count ? sevKind(item.urgency) : 'ok'}>{fa(item.count)}</B><span aria-hidden="true">‹</span>
    </button>)}
  </div>;
}

function Alerts({ go }) {
  const [data, setData] = useState(null); const [err, setErr] = useState('');
  const load = () => { setErr(''); setData(null); api.operationAlerts().then(setData).catch(e => setErr(errText(e))); };
  useEffect(load, []);
  if (err) return <ErrorState error={err} onRetry={load} />;
  if (!data) return <Loading rows={4} />;
  const alerts = data.alerts || [];
  if (!alerts.length) return <Empty icon="✅" text="هشدار عملیاتی فعالی وجود ندارد" />;
  return <div className="grid">
    {alerts.map(item => <button key={item.key} className={`panel panel-pad operation-card attention-${item.severity || 'warning'}`} onClick={() => go?.(item.go)}>
      <span className="operation-icon">{item.icon}</span><span className="operation-body"><b>{item.label}</b>
        <span className="muted">{item.timestamp ? <FaDateTime value={item.timestamp} /> : 'زمان رویداد در منبع ثبت نشده'}</span></span>
      <B kind={sevKind(item.severity)}>{fa(item.count)}</B><span>‹</span>
    </button>)}
  </div>;
}

// 🌊 WA21 — همان فهرست بک‌اند (`_QUALITY_SAFE_FIXES`). عمداً در دو جا
// تعریف نشده: بک‌اند `fixable` را در پاسخ برمی‌گرداند و UI از همان می‌خواند.
function DataQuality() {
  const [data, setData] = useState(null); const [err, setErr] = useState(''); const [selected, setSelected] = useState(null);
  const load = () => { setErr(''); setData(null); api.dataQuality().then(setData).catch(e => setErr(errText(e))); };
  useEffect(load, []);
  if (err) return <ErrorState title="بررسی کیفیت داده اجرا نشد" error={err} onRetry={load} />;
  if (!data) return <Loading rows={6} />;
  const fixable = new Set(data.fixable || []);
  return <>
    <div className="panel panel-pad data-quality-note"><B kind="warn">inspect + fix محدود</B><span>این مرکز anomalyهای قابل‌اثبات را گزارش می‌کند. فقط رکوردهای یتیم (بدون والدِ معتبر) اصلاح خودکار دارند — گونه‌های هویتی و مالی عمداً دستی می‌مانند.</span></div>
    <div className="grid g2 operations-grid">
      {(data.items || []).map(item => <button key={item.kind} className="panel panel-pad operation-card" disabled={!item.available} onClick={() => setSelected(item)}>
        <span className="operation-icon">{item.severity === 'critical' ? '⛔' : item.severity === 'warning' ? '⚠️' : 'ℹ️'}</span>
        <span className="operation-body"><b>{item.label}</b><span className="muted">{item.suggestion}</span></span>
        <B kind={item.available ? sevKind(item.severity) : ''}>{item.available ? fa(item.count) : 'ناموجود'}</B><span>‹</span>
      </button>)}
    </div>
    {selected && <QualityDrawer item={selected} canFix={fixable.has(selected.kind)}
      onClose={() => setSelected(null)} onFixed={() => { load(); setSelected(null); }} />}
  </>;
}

function QualityDrawer({ item, canFix = false, onClose, onFixed }) {
  const [page, setPage] = useState(1); const [data, setData] = useState(null); const [err, setErr] = useState(''); const limit = 30;
  const [busy, setBusy] = useState(false); const [ask, setAsk] = useState(false);
  const load = () => { setErr(''); setData(null); api.dataQualityItems(item.kind, { skip: (page - 1) * limit, limit }).then(setData).catch(e => setErr(errText(e))); };
  useEffect(load, [page, item.kind]);

  // 🌊 WA21 — Fix فقط برای گونه‌های امن، با تأیید صریح و audit سمت بک‌اند.
  const fix = async () => {
    setBusy(true);
    try {
      const r = await api.dataQualityFix(item.kind);
      toast(`${item.label}: ${fa(r.removed)} رکورد اصلاح شد`, r.removed ? 'ok' : 'warn');
      setAsk(false);
      onFixed?.();
    } catch (e) {
      toast(errText(e), 'bad');
    } finally {
      setBusy(false);
    }
  };
  const cols = [
    { k: 'label', label: 'Object', render: row => <div><b>{row.label}</b><div className="code muted">{row.id}</div></div> },
    { k: 'reason', label: 'دلیل' },
    { k: 'metadata', label: 'متادیتا', render: row => <span className="code text-wrap">{Object.entries(row.metadata || {}).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join('|') : v}`).join(' · ') || '—'}</span> },
    { k: 'suggestion', label: 'اقدام پیشنهادی' },
  ];
  // ⚠️ `Drawer` پروپ `actions` ندارد (فقط title/onClose/children/wide)؛
  // پس اکشن داخل children رندر می‌شود وگرنه بی‌صدا حذف می‌شد.
  return <Drawer wide title={`🧬 ${item.label}`} onClose={onClose}>
    {canFix && !!data?.total && <div className="row" style={{ marginBottom: 10 }}>
      <span className="muted">این رکوردها والدِ معتبر ندارند و هیچ‌جا نمایش داده نمی‌شدند.</span>
      <span className="spacer" />
      <button className="btn sm danger" disabled={busy} onClick={() => setAsk(true)}>
        {busy ? '…' : `🔧 اصلاح ${fa(data.total)} رکورد`}
      </button>
    </div>}
    {err ? <ErrorState error={err} onRetry={load} /> : !data ? <Loading rows={5} /> : <DataTable columns={cols} rows={data.items || []} rowKey="id" colToggle
      pager={{ page, pages: Math.max(1, Math.ceil((data.total || 0) / limit)), total: data.total || 0, onPage: setPage }} />}
    {ask && <Confirm danger onNo={() => setAsk(false)} onYes={fix}
      text={`این عملیات ${fa(data?.total || 0)} رکوردِ «${item.label}» را حذف می‌کند. این رکوردها والدِ معتبر ندارند و هیچ‌جا نمایش داده نمی‌شدند. تغییر در حسابرسی ثبت می‌شود و بازگشت‌پذیر نیست.`} />}
  </Drawer>;
}
