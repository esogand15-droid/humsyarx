import React, { useEffect, useMemo, useState } from 'react';
import { api, errText } from '../api.js';
import { B, DataTable, Drawer, Empty, ErrorState, FaDateTime, Loading, PageHeader, Tabs } from '../ui.jsx';
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

function DataQuality() {
  const [data, setData] = useState(null); const [err, setErr] = useState(''); const [selected, setSelected] = useState(null);
  const load = () => { setErr(''); setData(null); api.dataQuality().then(setData).catch(e => setErr(errText(e))); };
  useEffect(load, []);
  if (err) return <ErrorState title="بررسی کیفیت داده اجرا نشد" error={err} onRetry={load} />;
  if (!data) return <Loading rows={6} />;
  return <>
    <div className="panel panel-pad data-quality-note"><B kind="warn">فقط‌خواندنی</B><span>این مرکز anomalyهای قابل‌اثبات را گزارش می‌کند؛ هیچ auto-fix بدون domain operation و تأیید اجرا نمی‌شود.</span></div>
    <div className="grid g2 operations-grid">
      {(data.items || []).map(item => <button key={item.kind} className="panel panel-pad operation-card" disabled={!item.available} onClick={() => setSelected(item)}>
        <span className="operation-icon">{item.severity === 'critical' ? '⛔' : item.severity === 'warning' ? '⚠️' : 'ℹ️'}</span>
        <span className="operation-body"><b>{item.label}</b><span className="muted">{item.suggestion}</span></span>
        <B kind={item.available ? sevKind(item.severity) : ''}>{item.available ? fa(item.count) : 'ناموجود'}</B><span>‹</span>
      </button>)}
    </div>
    {selected && <QualityDrawer item={selected} onClose={() => setSelected(null)} />}
  </>;
}

function QualityDrawer({ item, onClose }) {
  const [page, setPage] = useState(1); const [data, setData] = useState(null); const [err, setErr] = useState(''); const limit = 30;
  const load = () => { setErr(''); setData(null); api.dataQualityItems(item.kind, { skip: (page - 1) * limit, limit }).then(setData).catch(e => setErr(errText(e))); };
  useEffect(load, [page, item.kind]);
  const cols = [
    { k: 'label', label: 'Object', render: row => <div><b>{row.label}</b><div className="code muted">{row.id}</div></div> },
    { k: 'reason', label: 'دلیل' },
    { k: 'metadata', label: 'متادیتا', render: row => <span className="code text-wrap">{Object.entries(row.metadata || {}).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join('|') : v}`).join(' · ') || '—'}</span> },
    { k: 'suggestion', label: 'اقدام پیشنهادی' },
  ];
  return <Drawer wide title={`🧬 ${item.label}`} onClose={onClose}>
    {err ? <ErrorState error={err} onRetry={load} /> : !data ? <Loading rows={5} /> : <DataTable columns={cols} rows={data.items || []} rowKey="id" colToggle
      pager={{ page, pages: Math.max(1, Math.ceil((data.total || 0) / limit)), total: data.total || 0, onPage: setPage }} />}
  </Drawer>;
}
